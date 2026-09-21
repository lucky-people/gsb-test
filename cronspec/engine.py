"""触发时间计算引擎与 Schedule 类型。

搜索按字段推进（年 -> 月 -> 日 -> 时 -> 分），每一轮迭代至少有一个
字段向前跳动，绝不逐分钟线性扫描，因此稀疏表达式（如每年一次、
闰日一次）也能在常数级迭代次数内定位。

核心实现基于 (year, month, day, hour, minute) 整数元组，与 datetime
无关，因此内部迭代器可以算到年份 9999 以外（供基准测试使用）；
公开的 datetime API 受 datetime 本身范围限制，可搜索年份为 1..9999。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterator, List, Optional, Tuple

from .errors import NoMatchingTimeError
from .fields import CronField
from .parser import parse_fields

MAX_YEAR = 9999  # datetime 可表示的最大年份

_DAYS_IN_MONTH_COMMON = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

_WEEKDAY_CN = ("周日", "周一", "周二", "周三", "周四", "周五", "周六")
_MONTH_CN = (
    "1月", "2月", "3月", "4月", "5月", "6月",
    "7月", "8月", "9月", "10月", "11月", "12月",
)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_month(year: int, month: int) -> int:
    if month == 2 and _is_leap(year):
        return 29
    return _DAYS_IN_MONTH_COMMON[month - 1]


def _day_of_week(year: int, month: int, day: int) -> int:
    """返回 cron 语义的星期值：0=周日 .. 6=周六（格里高利历，支持任意年份）。"""
    y = year - 1
    ordinal = 365 * y + y // 4 - y // 100 + y // 400
    ordinal += sum(_DAYS_IN_MONTH_COMMON[: month - 1])
    if month > 2 and _is_leap(year):
        ordinal += 1
    ordinal += day
    # 公元 1 年 1 月 1 日为周一，故星期序号 = ordinal % 7（周一=1 ... 周六=6，周日=0）
    return ordinal % 7


def _roll_day(year: int, month: int, day: int) -> Tuple[int, int, int]:
    """日期向后推一天（day 必须是当月合法日期）。"""
    if day < _days_in_month(year, month):
        return year, month, day + 1
    if month < 12:
        return year, month + 1, 1
    return year + 1, 1, 1


class Schedule:
    """一个解析完成的 cron 调度。"""

    __slots__ = ("minute", "hour", "dom", "month", "dow")

    def __init__(
        self,
        minute: CronField,
        hour: CronField,
        dom: CronField,
        month: CronField,
        dow: CronField,
    ) -> None:
        self.minute = minute
        self.hour = hour
        self.dom = dom
        self.month = month
        self.dow = dow

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def matches(self, dt: datetime) -> bool:
        """判断 dt 是否命中。秒必须整 0；带 tzinfo 抛 TypeError。"""
        _check_naive(dt)
        if dt.second != 0:
            return False
        if dt.minute not in self.minute or dt.hour not in self.hour:
            return False
        if dt.month not in self.month:
            return False
        return self._day_matches(dt.year, dt.month, dt.day)

    def next_after(self, dt: datetime) -> datetime:
        """返回严格晚于 dt 的下一个触发时刻（不修改入参）。"""
        _check_naive(dt)
        base = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        result = _tuple_next_after(
            self, (base.year, base.month, base.day, base.hour, base.minute),
            max_year=MAX_YEAR,
        )
        if result is None:
            raise NoMatchingTimeError(
                f"在年份 1..{MAX_YEAR} 范围内找不到任何触发时刻"
            )
        return datetime(*result)

    def next_n(self, dt: datetime, n: int) -> List[datetime]:
        """返回 dt 之后接下来的 n 个触发时刻（严格升序、不重复）。"""
        _check_naive(dt)
        if not isinstance(n, int) or isinstance(n, bool):
            raise TypeError("n 必须是整数")
        if n <= 0:
            raise ValueError("n 必须是正整数")
        results: List[datetime] = []
        cursor = dt
        for _ in range(n):
            cursor = self.next_after(cursor)
            results.append(cursor)
        return results

    # ------------------------------------------------------------------
    # 内部：匹配与搜索
    # ------------------------------------------------------------------

    def _day_matches(self, year: int, month: int, day: int) -> bool:
        """POSIX/Vixie 规则：DOM 与 DOW 都被限定时取并集。"""
        dom_ok = day in self.dom
        dow_ok = _day_of_week(year, month, day) in self.dow
        if not self.dom.is_star and not self.dow.is_star:
            return dom_ok or dow_ok
        if not self.dom.is_star:
            return dom_ok
        if not self.dow.is_star:
            return dow_ok
        return True

    def _next_day_in_month(
        self, year: int, month: int, day: int
    ) -> Optional[int]:
        """当月内 >= day 的最近一个可触发日；不存在返回 None。"""
        last_day = _days_in_month(year, month)
        dom_restricted = not self.dom.is_star
        dow_restricted = not self.dow.is_star

        if dom_restricted and dow_restricted:
            best: Optional[int] = None
            dom_hit = self.dom.next_ge(day)
            if dom_hit is not None and dom_hit <= last_day:
                best = dom_hit
            dow_hit = self._next_dow_day(year, month, day)
            if dow_hit is not None and (best is None or dow_hit < best):
                best = dow_hit
            return best
        if dom_restricted:
            dom_hit = self.dom.next_ge(day)
            if dom_hit is not None and dom_hit <= last_day:
                return dom_hit
            return None
        if dow_restricted:
            return self._next_dow_day(year, month, day)
        return day if day <= last_day else None

    def _next_dow_day(self, year: int, month: int, day: int) -> Optional[int]:
        """当月内 >= day 且星期匹配的第一个日期。"""
        last_day = _days_in_month(year, month)
        if day > last_day:
            return None
        dow = _day_of_week(year, month, day)
        best_delta: Optional[int] = None
        for target in self.dow.values:
            delta = (target - dow) % 7
            if best_delta is None or delta < best_delta:
                best_delta = delta
        candidate = day + best_delta  # type: ignore[operator]
        if candidate > last_day:
            return None
        return candidate

    def _iter_tuples(
        self,
        start: Tuple[int, int, int, int, int],
        max_year: int = 1_000_000,
    ) -> Iterator[Tuple[int, int, int, int, int]]:
        """从 (年,月,日,时,分) 元组之后开始，无限产生触发时刻元组。

        供基准测试使用，可越过 datetime 的年份上限。
        """
        current = _tuple_next_after(self, start, max_year=max_year)
        while current is not None:
            yield current
            current = _tuple_next_after(self, _bump_minute(current), max_year=max_year)


def _check_naive(dt: datetime) -> None:
    if not isinstance(dt, datetime):
        raise TypeError("参数必须是 datetime 实例")
    if dt.tzinfo is not None and dt.utcoffset() is not None:
        raise TypeError("只接受朴素 datetime（不带 tzinfo）")


def _bump_minute(t: Tuple[int, int, int, int, int]) -> Tuple[int, int, int, int, int]:
    year, month, day, hour, minute = t
    minute += 1
    if minute == 60:
        minute = 0
        hour += 1
        if hour == 24:
            hour = 0
            year, month, day = _roll_day(year, month, day)
    return year, month, day, hour, minute


def _tuple_next_after(
    schedule: Schedule,
    start: Tuple[int, int, int, int, int],
    max_year: int = MAX_YEAR,
) -> Optional[Tuple[int, int, int, int, int]]:
    """返回 >= start 的第一个触发时刻元组；理论上不会为 None（年份无限）。"""
    year, month, day, hour, minute = start
    while True:
        if year > max_year:
            return None
        # 月：跳到下一个允许月份，月份变化则日期归零
        if month not in schedule.month:
            nxt = schedule.month.next_ge(month)
            if nxt is None:
                year += 1
                month = schedule.month.minimum
            else:
                month = nxt
            day, hour, minute = 1, 0, 0
            continue

        # 日：当月内找最近可触发日，找不到则进入下一允许月份
        hit_day = schedule._next_day_in_month(year, month, day)
        if hit_day is None:
            nxt = schedule.month.next_gt(month)
            if nxt is None:
                year += 1
                month = schedule.month.minimum
            else:
                month = nxt
            day, hour, minute = 1, 0, 0
            continue
        if hit_day != day:
            day, hour, minute = hit_day, 0, 0

        # 时
        if hour not in schedule.hour:
            nxt = schedule.hour.next_ge(hour)
            if nxt is None:
                year, month, day = _roll_day(year, month, day)
                hour, minute = 0, 0
                continue
            hour, minute = nxt, 0
            continue

        # 分
        if minute not in schedule.minute:
            nxt = schedule.minute.next_ge(minute)
            if nxt is None:
                hour += 1
                minute = 0
                if hour == 24:
                    hour = 0
                    year, month, day = _roll_day(year, month, day)
                continue
            minute = nxt
            continue

        return year, month, day, hour, minute


# ----------------------------------------------------------------------
# 人类可读描述
# ----------------------------------------------------------------------

def describe_schedule(schedule: Schedule) -> str:
    """根据取值集合生成确定的中文描述。"""
    minute, hour = schedule.minute, schedule.hour
    dom, month, dow = schedule.dom, schedule.month, schedule.dow

    # 描述时“通配”指取值覆盖整个合法范围（裸 * 或 */1）；*/n 算受限集合
    minute_star = _covers_all(minute, 0, 59)
    hour_star = _covers_all(hour, 0, 23)
    dom_star = _covers_all(dom, 1, 31)
    month_star = _covers_all(month, 1, 12)
    dow_star = _covers_all(dow, 0, 6)

    # 每分钟
    if minute_star and hour_star and dom_star and month_star and dow_star:
        return "每分钟"

    # 时间部分
    if minute_star and hour_star:
        time_part = "每分钟"
    elif hour_star and len(minute.values) == 1 and minute.values[0] == 0:
        time_part = "每小时整点"
    elif hour_star:
        if len(minute.values) == 1:
            time_part = f"每小时第 {minute.values[0]} 分"
        else:
            time_part = "每小时的 " + _format_minutes(minute.values)
    else:
        time_part = _format_clock(hour.values, minute)

    # 日期限定部分
    day_part = _describe_day_part(schedule)

    # 月份限定部分
    month_part = ""
    if not month_star:
        month_part = "、".join(_MONTH_CN[m - 1] for m in month.values)
        if day_part.startswith("每月"):
            day_part = day_part[2:]

    if day_part and month_part:
        return f"{month_part}的{day_part} {time_part}"
    if day_part:
        return f"{day_part} {time_part}"
    if month_part:
        return f"{month_part}每天 {time_part}"
    if time_part in ("每分钟", "每小时整点") or hour_star:
        return time_part
    return f"每天 {time_part}"


def _describe_day_part(schedule: Schedule) -> str:
    dom, dow = schedule.dom, schedule.dow
    dom_star, dow_star = _covers_all(dom, 1, 31), _covers_all(dow, 0, 6)
    if dom_star and dow_star:
        return ""
    if not dom_star and dow_star:
        days = "、".join(f"{d}日" for d in dom.values)
        return f"每月{days}"
    if dom_star and not dow_star:
        return "每" + "、".join(_WEEKDAY_CN[d] for d in sorted(dow.values))
    # 并集语义
    dom_text = "、".join(f"{d}日" for d in dom.values)
    dow_text = "、".join(_WEEKDAY_CN[d] for d in sorted(dow.values))
    return f"每月{dom_text}以及每{dow_text}"


def _covers_all(field: CronField, lo: int, hi: int) -> bool:
    """取值是否覆盖完整合法范围（区分裸 */*/1 与 */n 步进集合）。"""
    return field.values == tuple(range(lo, hi + 1))


def _format_clock(hours: Tuple[int, ...], minute: CronField) -> str:
    """小时被限定时的时刻描述。"""
    if len(minute.values) == 1:
        minute_text = f"{minute.values[0]:02d}"
        return "、".join(f"{h:02d}:{minute_text}" for h in hours)
    if minute.is_star:
        if len(hours) == 1:
            return f"{hours[0]:02d} 点内每分钟"
        return "、".join(f"{h:02d} 点" for h in hours) + "内每分钟"
    minutes_text = _format_minutes(minute.values)
    if len(hours) == 1:
        return f"{hours[0]:02d} 点的 {minutes_text}"
    return "、".join(f"{h:02d} 点" for h in hours) + f"的 {minutes_text}"


def _format_minutes(values: Tuple[int, ...]) -> str:
    if len(values) <= 6:
        return "、".join(f"第 {v} 分" for v in values)
    return f"第 {values[0]}-{values[-1]} 分等 {len(values)} 个分钟"
