"""Cron 表达式词法分析、字段解析与人类可读描述。"""

from .errors import ScheduleSyntaxError
from .fields import (
    CronField,
    DAY_OF_MONTH,
    DAY_OF_WEEK,
    FIELD_NAMES,
    FIELD_RANGES,
    HOUR,
    MINUTE,
    MONTH,
    MONTH_NAMES,
    Schedule,
    WEEKDAY_NAMES,
)


# 短写（@reboot 属于一次性任务而非周期计划，不在支持范围内）。
SHORTCUTS = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 1",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

FIELD_NAME_MAPS = {
    MINUTE: None,
    HOUR: None,
    DAY_OF_MONTH: None,
    MONTH: MONTH_NAMES,
    DAY_OF_WEEK: WEEKDAY_NAMES,
}


def _tokenize(expr):
    """按空格或制表符切词，返回 (片段文本, 在原文中的起始下标) 列表。"""
    tokens = []
    index = 0
    length = len(expr)
    while index < length:
        if expr[index] in " \t":
            index += 1
            continue
        start = index
        while index < length and expr[index] not in " \t":
            index += 1
        tokens.append((expr[start:index], start))
    return tokens


def _resolve_value(token, field_name, name_map, position):
    """把数字或名字（如 JAN、MON）解析为整数，并做范围校验。

    报错时 ``value`` 取该词元原文，``position`` 指向它在原始表达式中的
    起始下标。
    """
    if token.isdigit():
        number = int(token)
    elif name_map is not None and token.isalpha():
        upper_token = token.upper()
        if upper_token not in name_map:
            raise ScheduleSyntaxError(
                field_name,
                token,
                position,
                "%s 字段存在未知名字 %r，支持 %s"
                % (field_name, token, "、".join(name_map.keys())),
            )
        number = name_map[upper_token]
    else:
        raise ScheduleSyntaxError(
            field_name,
            token,
            position,
            "%s 字段包含非法字符 %r，只允许数字、范围 - 、步进 / 、逗号以及"
            "受支持的名字" % (field_name, token),
        )

    low, high = FIELD_RANGES[field_name]
    if number < low or number > high:
        raise ScheduleSyntaxError(
            field_name,
            token,
            position,
            "%s 字段的值 %d 超出允许范围 %d-%d"
            % (field_name, number, low, high),
        )
    if field_name == DAY_OF_WEEK and number == 7:
        # POSIX 约定 0 与 7 都表示周日，内部统一为 0。
        number = 0
    return number


def _parse_fragment(fragment, field_name, name_map, position):
    """解析单个逗号片段，如 ``*``、``1-5``、``30-40/5``。

    ``position`` 是片段在原始表达式中的起始下标。所有报错都遵循定位约定：
    ``value`` 是最小出错片段原文，``position`` 指向它，即恒有
    ``expr[position:position+len(value)] == value``。
    """
    if fragment == "":
        raise ScheduleSyntaxError(
            field_name,
            "",
            position,
            "%s 字段存在空片段，逗号两侧必须都有内容" % field_name,
        )

    slash_parts = fragment.split("/")
    if len(slash_parts) > 2:
        raise ScheduleSyntaxError(
            field_name,
            fragment,
            position,
            "%s 字段的片段 %r 中步进符 / 只能出现一次"
            % (field_name, fragment),
        )

    base = slash_parts[0]
    if len(slash_parts) == 2:
        step_token = slash_parts[1]
        if not step_token.isdigit() or int(step_token) == 0:
            raise ScheduleSyntaxError(
                field_name,
                step_token,
                position + len(base) + 1,
                "%s 字段的步进值 %r 必须是正整数（不允许 0 或负数）"
                % (field_name, step_token),
            )
        step = int(step_token)
    else:
        step = None

    is_star = False
    if base == "*":
        is_star = True
        start_value, end_value = FIELD_RANGES[field_name]
        if field_name == DAY_OF_WEEK:
            # 星期字段内部取值上界为 6（7 已归一化为 0）。
            end_value = 6
    else:
        if base.startswith("*"):
            raise ScheduleSyntaxError(
                field_name,
                base,
                position,
                "%s 字段的片段 %r 非法，星号只能单独作为范围起点"
                % (field_name, base),
            )
        range_parts = base.split("-")
        if len(range_parts) > 2:
            raise ScheduleSyntaxError(
                field_name,
                base,
                position,
                "%s 字段的片段 %r 中范围符 - 只能出现一次"
                % (field_name, base),
            )
        start_value = _resolve_value(
            range_parts[0], field_name, name_map, position
        )
        if len(range_parts) == 2:
            if range_parts[1] == "":
                raise ScheduleSyntaxError(
                    field_name,
                    base,
                    position,
                    "%s 字段的范围 %r 缺少结束值" % (field_name, base),
                )
            end_position = position + base.index("-") + 1
            end_value = _resolve_value(
                range_parts[1],
                field_name,
                name_map,
                end_position,
            )
            if start_value > end_value:
                raise ScheduleSyntaxError(
                    field_name,
                    base,
                    position,
                    "%s 字段范围倒序：%d 大于 %d，范围必须从小到大"
                    % (field_name, start_value, end_value),
                )
        else:
            end_value = start_value
        if step is not None and len(range_parts) == 1:
            raise ScheduleSyntaxError(
                field_name,
                fragment,
                position,
                "%s 字段的片段 %r 非法，步进写法必须是 */n 或 范围/n 形式"
                % (field_name, fragment),
            )

    if step is None:
        step = 1
    return list(range(start_value, end_value + 1, step)), is_star


def _parse_field(field_text, field_name, field_start):
    """解析一整个字段（逗号组合），并保留每个片段在原文中的起始位置。"""
    name_map = FIELD_NAME_MAPS[field_name]
    values = set()
    is_star = False
    offset = 0
    for fragment in field_text.split(","):
        fragment_values, fragment_is_star = _parse_fragment(
            fragment,
            field_name,
            name_map,
            field_start + offset,
        )
        values.update(fragment_values)
        is_star = is_star or fragment_is_star
        offset += len(fragment) + 1
    return CronField(sorted(values), is_star)


def parse(expr):
    """解析标准 5 字段 Cron 表达式或合法短写，返回 :class:`Schedule`。"""
    if not isinstance(expr, str):
        raise ScheduleSyntaxError(
            None,
            "" if expr is None else str(expr),
            0,
            "表达式必须是字符串，实际收到 %s" % type(expr).__name__,
        )

    stripped = expr.strip()
    if stripped == "":
        raise ScheduleSyntaxError(None, stripped, 0, "表达式为空")

    # 表达式级报错的 value 是去除首尾空白后的整个表达式，position 指向
    # 这段文本在原始表达式中的起点，保证 expr[position:position+len(value)]
    # == value 不变量对前导空白同样成立。
    stripped_start = len(expr) - len(expr.lstrip())

    tokens = _tokenize(expr)

    if stripped[0] == "@":
        token_text, token_start = tokens[0]
        if token_text != stripped or len(tokens) != 1:
            raise ScheduleSyntaxError(
                None,
                stripped,
                stripped_start,
                "短写表达式不能再附带其他字段",
            )
        if token_text not in SHORTCUTS:
            raise ScheduleSyntaxError(
                None,
                token_text,
                token_start,
                "未知短写 %r，支持 %s"
                % (token_text, "、".join(sorted(SHORTCUTS))),
            )
        expanded = SHORTCUTS[token_text]
        fields = _parse_fields(_tokenize(expanded))
        return Schedule(raw=expr, **fields)

    if len(tokens) != 5:
        raise ScheduleSyntaxError(
            None,
            stripped,
            stripped_start,
            "表达式必须由 5 个字段（分 时 日 月 周）或一个合法短写组成，"
            "实际切分出 %d 个字段" % len(tokens),
        )

    return Schedule(raw=expr, **_parse_fields(tokens))


def _parse_fields(tokens):
    return {
        field_name: _parse_field(token_text, field_name, token_start)
        for (token_text, token_start), field_name in zip(tokens, FIELD_NAMES)
    }


# ---------------------------------------------------------------------------
# 人类可读描述（确定性输出：相同表达式永远得到相同字符串）
# ---------------------------------------------------------------------------

_WEEKDAY_CN = ("周日", "周一", "周二", "周三", "周四", "周五", "周六")


def _is_consecutive(values):
    return list(values) == list(range(values[0], values[-1] + 1))


def _render_number_list(values, pad=False):
    texts = ["%02d" % value if pad else str(value) for value in values]
    if len(texts) > 2 and _is_consecutive(values):
        return "%s-%s" % (texts[0], texts[-1])
    return "、".join(texts)


def _date_phrase(schedule):
    """返回日期部分短语，可直接与时间短语用空格拼接。"""
    dom = schedule.day_of_month
    dow = schedule.day_of_week
    month_restricted = not schedule.month.is_star
    dom_restricted = not dom.is_star
    dow_restricted = not dow.is_star

    months = _render_number_list(schedule.month.values)
    doms = _render_number_list(dom.values)
    dows = "、".join(_WEEKDAY_CN[value] for value in dow.values)

    if dom_restricted and dow_restricted:
        core = "%s 日或%s" % (doms, dows)
        if month_restricted:
            return "每年 %s 月的 %s" % (months, core)
        return "每月 %s" % core
    if dom_restricted:
        if month_restricted:
            return "每年 %s 月 %s 日" % (months, doms)
        return "每月 %s 日" % doms
    if dow_restricted:
        if month_restricted:
            return "每年 %s 月的%s" % (months, dows)
        return "每%s" % dows
    if month_restricted:
        return "每年 %s 月的每天" % months
    return "每天"


def _time_phrase(schedule, date_phrase):
    """返回 (最终描述, )；负责把分钟/小时组合进日期短语。"""
    minutes = schedule.minute.values
    hours = schedule.hour.values
    every_minute = schedule.minute.is_star and schedule.hour.is_star
    every_hour = schedule.hour.is_star and not every_minute

    if every_minute:
        return "每分钟" if date_phrase == "每天" else date_phrase + "每分钟"

    if every_hour:
        if minutes == (0,):
            clock = "每小时整点"
        else:
            clock = "每小时的 %s 分" % _render_number_list(minutes, pad=True)
        return clock if date_phrase == "每天" else "%s的%s" % (date_phrase, clock)

    if len(minutes) == 1 and len(hours) == 1:
        clock = "%02d:%02d" % (hours[0], minutes[0])
    elif len(minutes) == 1:
        clock = "%s 时 %02d 分" % (
            _render_number_list(hours, pad=True),
            minutes[0],
        )
    else:
        clock = "%s 时的 %s 分" % (
            _render_number_list(hours, pad=True),
            _render_number_list(minutes, pad=True),
        )
    return "%s %s" % (date_phrase, clock)


def describe_schedule(schedule):
    return _time_phrase(schedule, _date_phrase(schedule))


def describe(expr):
    """返回表达式的确定性中文描述。"""
    return describe_schedule(parse(expr))
