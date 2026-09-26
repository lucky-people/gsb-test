"""触发时间搜索引擎。

搜索按字段推进：先跳到可能的月份，再在月内定位可能的日，再跳到时、分，
绝不逐分钟线性扫描。历法换算使用纯整数算术（Howard Hinnant 的 civil date
算法），内部 ``(年, 月, 日, 时, 分)`` 五元组不依赖 :class:`datetime.date`，
因此即使取触发时刻的数量超过 ``datetime`` 的 9999 年上限，内部搜索仍可进行。
"""

from datetime import datetime

from .errors import NoMatchingTimeError


# 搜索窗口上限（年）。公历星期每 400 年重复，闰年周期最长 8 年，
# 任何可行表达式都必然能在 400 年内命中，这里再留出余量。
SEARCH_LIMIT_YEARS = 400


def is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_in_month(year, month):
    if month == 2:
        return 29 if is_leap(year) else 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def _days_from_civil(year, month, day):
    """Howard Hinnant 公历日期 -> 自 1970-01-01 起的天数（支持任意整年）。"""
    y = year - (1 if month <= 2 else 0)
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(days):
    """``_days_from_civil`` 的逆运算。"""
    shifted = days + 719468
    era = shifted // 146097
    doe = shifted - era * 146097  # 该 400 年周期内的第几天（0 基）
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    year = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + 3 if mp < 10 else mp - 9
    if month <= 2:
        year += 1
    return year, month, day


def weekday_of(year, month, day):
    """返回 0（周日）到 6（周六）。"""
    return (_days_from_civil(year, month, day) + 4) % 7


def first_weekday_on_or_after(year, month, day, wanted, limit_day):
    """在同月 [day, limit_day] 内寻找下一个指定星期几，找不到返回 None。"""
    if day > limit_day:
        return None
    current = weekday_of(year, month, day)
    delta = (wanted - current) % 7
    candidate = day + delta
    return candidate if candidate <= limit_day else None


def _candidate_day(schedule, year, month, min_day):
    """在同月 >= min_day 的范围找下一个满足 DOM/DOW 规则的日，找不到返回 None。"""
    limit_day = days_in_month(year, month)
    if min_day > limit_day:
        return None

    dom_restricted = not schedule.day_of_month.is_star
    dow_restricted = not schedule.day_of_week.is_star
    candidates = []

    if dom_restricted:
        dom_day = schedule.day_of_month.next_value_at_or_above(min_day)
        if dom_day is not None and dom_day <= limit_day:
            candidates.append(dom_day)

    if dow_restricted:
        # 周一在周五之前时，必须逐个星期值试探；集合最多 7 个值，开销恒定。
        for wanted in schedule.day_of_week.values:
            dow_day = first_weekday_on_or_after(
                year, month, min_day, wanted, limit_day
            )
            if dow_day is not None:
                candidates.append(dow_day)

    if not dom_restricted and not dow_restricted:
        return min_day
    return min(candidates) if candidates else None


def _candidate_time(schedule, hour, minute, same_day):
    """在给定小时或其后寻找 (时, 分)；跨天返回 None。

    same_day 为 True 时只允许在 >= (hour, minute) 的当天时刻中寻找。
    """
    if same_day:
        next_hour = schedule.hour.next_value_at_or_above(hour)
        if next_hour is None:
            return None
        if next_hour == hour:
            next_minute = schedule.minute.next_value_at_or_above(minute)
            if next_minute is None:
                next_hour = schedule.hour.next_value_at_or_above(hour + 1)
                if next_hour is None:
                    return None
                return next_hour, schedule.minute.minimum
            return next_hour, next_minute
        return next_hour, schedule.minute.minimum
    return schedule.hour.minimum, schedule.minute.minimum


def next_tuple(schedule, year, month, day, hour, minute):
    """核心搜索：返回严格晚于给定时刻的下一个 (年, 月, 日, 时, 分)。"""
    first_allowed = schedule.month.next_value_at_or_above(month)
    if first_allowed is None:
        cursor_year, cursor_month = year + 1, schedule.month.minimum
        in_start_month = False
    else:
        cursor_year, cursor_month = year, first_allowed
        in_start_month = cursor_month == month

    while cursor_year - year <= SEARCH_LIMIT_YEARS:
        cursor_day = day if in_start_month else 1

        while True:
            candidate_day = _candidate_day(
                schedule, cursor_year, cursor_month, cursor_day
            )
            if candidate_day is None:
                break

            day_same = in_start_month and candidate_day == day
            if day_same:
                time_result = _candidate_time(schedule, hour, minute, True)
                # 整分时刻不晚于同分钟内的任何输入时刻，统一跳过同一分钟。
            else:
                time_result = _candidate_time(schedule, 0, 0, False)

            if time_result is not None:
                candidate_hour, candidate_minute = time_result
                return (
                    cursor_year,
                    cursor_month,
                    candidate_day,
                    candidate_hour,
                    candidate_minute,
                )

            # 当天没有可用时刻，推进到下一个候选日。
            if candidate_day == days_in_month(cursor_year, cursor_month):
                break
            cursor_day = candidate_day + 1

        # 本月耗尽，跳到下一个允许的月份，必要时跨年。
        next_month_value = schedule.month.next_value_at_or_above(
            cursor_month + 1
        )
        if next_month_value is None:
            cursor_year += 1
            cursor_month = schedule.month.minimum
        else:
            cursor_month = next_month_value
        in_start_month = False

    raise NoMatchingTimeError(
        "在 %d 年的搜索窗口内没有任何触发时刻，可能该日期组合不存在（"
        "如 2 月 30 日）" % SEARCH_LIMIT_YEARS
    )


def _check_feasible(schedule):
    """表达式级可行性预检：快速识别必然无解的日期组合。"""
    dom_restricted = not schedule.day_of_month.is_star
    dow_restricted = not schedule.day_of_week.is_star
    if dow_restricted:
        # 只要有星期限定，任意非空月份集合内总会出现该星期。
        return
    if not dom_restricted:
        return
    for value in schedule.day_of_month.values:
        for month_value in schedule.month.values:
            if _dom_possible(value, month_value):
                return
    raise NoMatchingTimeError(
        "该表达式指定的日/月组合在公历中不存在（例如 2 月 30 日）"
    )


def _dom_possible(day_value, month_value):
    if month_value == 2:
        # 2 月 29 日在闰年存在；引擎会在真实闰年命中。
        return day_value <= 29
    if month_value in (4, 6, 9, 11):
        return day_value <= 30
    return day_value <= 31


def _ensure_naive(dt):
    if not isinstance(dt, datetime):
        raise TypeError(
            "参数必须是 datetime.datetime，实际收到 %s" % type(dt).__name__
        )
    if dt.tzinfo is not None:
        raise TypeError("只接受朴素 datetime（tzinfo 必须为 None）")


def matches(schedule, dt):
    """判断某个时刻是否命中。秒或微秒不为 0 一律返回 False。"""
    _ensure_naive(dt)
    if dt.second != 0 or dt.microsecond != 0:
        return False
    if not schedule.minute.contains(dt.minute):
        return False
    if not schedule.hour.contains(dt.hour):
        return False
    if not schedule.month.contains(dt.month):
        return False
    cron_weekday = (dt.isoweekday()) % 7
    return schedule.day_matches(dt.year, dt.month, dt.day, cron_weekday)


def next_after(schedule, dt):
    """返回严格晚于 dt 的下一个触发时刻（朴素 datetime）。"""
    _ensure_naive(dt)
    _check_feasible(schedule)
    tuple_result = next_tuple(
        schedule,
        dt.year,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
    )
    try:
        return datetime(*tuple_result)
    except ValueError as error:
        raise NoMatchingTimeError(
            "下一个触发时刻超出 datetime 支持范围（年份必须在 1-9999 之间）"
        ) from error


def next_n(schedule, dt, n):
    """返回从 dt 之后开始的 n 个触发时刻，严格升序、不重复。"""
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("n 必须是 int")
    if n <= 0:
        raise ValueError("n 必须为正整数")
    _ensure_naive(dt)
    _check_feasible(schedule)

    result = []
    year, month, day, hour, minute = (
        dt.year,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
    )
    for _ in range(n):
        year, month, day, hour, minute = next_tuple(
            schedule, year, month, day, hour, minute
        )
        try:
            result.append(datetime(year, month, day, hour, minute))
        except ValueError:
            raise NoMatchingTimeError(
                "触发时刻超出 datetime 支持范围（年份必须在 1-9999 之间）"
            )
    return result
