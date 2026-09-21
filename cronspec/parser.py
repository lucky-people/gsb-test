"""cron 表达式的词法切分与字段解析。

语法（标准 5 字段：分 时 日 月 周）：
    字段   := 片段 ("," 片段)*
    片段   := "*" | "*/n" | 值 | 值"-"值 | 值"-"值"/"n
    值     := 数字 | 名字（仅月/周字段）
字段之间允许一个或多个空格或制表符，首尾空白忽略。
另外支持 @yearly/@annually/@monthly/@weekly/@daily/@midnight/@hourly 短写。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .errors import ScheduleSyntaxError
from .fields import CronField

# 字段名（用于 ScheduleSyntaxError.field 与报错信息）
FIELD_MINUTE = "minute"
FIELD_HOUR = "hour"
FIELD_DOM = "dom"
FIELD_MONTH = "month"
FIELD_DOW = "dow"

FIELD_ORDER = (FIELD_MINUTE, FIELD_HOUR, FIELD_DOM, FIELD_MONTH, FIELD_DOW)

_FIELD_CN = {
    FIELD_MINUTE: "分钟",
    FIELD_HOUR: "小时",
    FIELD_DOM: "日",
    FIELD_MONTH: "月",
    FIELD_DOW: "星期",
}

# 每个字段的 (最小值, 最大值, 名字表)；名字统一按大写匹配
_FIELD_SPEC: Dict[str, Tuple[int, int, Optional[Dict[str, int]]]] = {
    FIELD_MINUTE: (0, 59, None),
    FIELD_HOUR: (0, 23, None),
    FIELD_DOM: (1, 31, None),
    FIELD_MONTH: (
        1,
        12,
        {
            "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
            "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
        },
    ),
    FIELD_DOW: (
        0,
        7,
        {
            "SUN": 0, "MON": 1, "TUE": 2, "WED": 3,
            "THU": 4, "FRI": 5, "SAT": 6,
        },
    ),
}

# 短写 -> 等价的 5 字段表达式
_SHORTCUTS: Dict[str, str] = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

# 片段内允许出现的字符：数字、字母、*、-、/
_PIECE_CHARS = re.compile(r"^[0-9A-Za-z*/-]+$")

# 一个“值”：纯数字或纯字母（字母仅允许出现在月/周字段）
_ATOM = re.compile(r"[0-9]+|[A-Za-z]+")


def _err(
    message: str,
    field: Optional[str],
    value: str,
    position: int,
) -> ScheduleSyntaxError:
    return ScheduleSyntaxError(message, field=field, value=value, position=position)


def _tokenize(expr: str) -> List[Tuple[str, int]]:
    """按空格/制表符切分，返回 (片段, 起始下标) 列表。"""
    return [(m.group(0), m.start()) for m in re.finditer(r"[^ \t]+", expr)]


def parse_fields(expr: str) -> Tuple[CronField, CronField, CronField, CronField, CronField]:
    """把表达式解析为 (分, 时, 日, 月, 周) 五个 CronField。"""
    if not isinstance(expr, str):
        raise TypeError("cron 表达式必须是字符串")

    tokens = _tokenize(expr)
    if not tokens:
        raise _err("表达式为空：需要 5 个字段（分 时 日 月 周）或一个 @ 短写", None, expr, 0)

    if tokens[0][0].startswith("@"):
        text, pos = tokens[0]
        lowered = text.lower()
        if lowered not in _SHORTCUTS:
            raise _err(
                f"未知短写 {text!r}：仅支持 @yearly/@annually/@monthly/"
                f"@weekly/@daily/@midnight/@hourly",
                None,
                text,
                pos,
            )
        if len(tokens) != 1:
            raise _err(
                f"短写 {text!r} 之后不允许再出现其他字段",
                None,
                expr,
                0,
            )
        tokens = _tokenize(_SHORTCUTS[lowered])

    if len(tokens) != 5:
        raise _err(
            f"字段数错误：期望 5 个字段（分 时 日 月 周），实际为 {len(tokens)} 个",
            None,
            expr,
            0,
        )

    parsed = []
    for name, (text, pos) in zip(FIELD_ORDER, tokens):
        parsed.append(_parse_field(name, text, pos))
    return tuple(parsed)  # type: ignore[return-value]


def _parse_field(name: str, text: str, base: int) -> CronField:
    lo, hi, names = _FIELD_SPEC[name]
    values: List[int] = []
    is_star = False

    cursor = 0  # 当前片段在字段文本内的偏移
    while True:
        comma = text.find(",", cursor)
        if comma == -1:
            piece, piece_pos = text[cursor:], base + cursor
        else:
            piece, piece_pos = text[cursor:comma], base + cursor

        if piece == "":
            raise _err(
                f"{_FIELD_CN[name]}字段出现空片段（连续的逗号或首尾逗号）",
                name,
                "",
                piece_pos,
            )

        piece_star, piece_values = _parse_piece(name, piece, piece_pos, lo, hi, names)
        if piece_star:
            is_star = True
        values.extend(piece_values)

        if comma == -1:
            break
        cursor = comma + 1

    # 星期字段：7 与 0 都表示周日。归一化必须在范围展开之后进行，
    # 否则 0-7 展开会多出 7、* 展开会变成 0..7。
    if name == FIELD_DOW:
        values = [0 if v == 7 else v for v in values]
    return CronField(values, is_star)


def _parse_piece(
    name: str,
    piece: str,
    pos: int,
    lo: int,
    hi: int,
    names: Optional[Dict[str, int]],
) -> Tuple[bool, List[int]]:
    """解析单个逗号片段，返回 (是否以 * 开头, 取值列表)。"""
    if not _PIECE_CHARS.match(piece):
        raise _err(
            f"{_FIELD_CN[name]}字段片段 {piece!r} 含有非法字符",
            name,
            piece,
            pos,
        )

    if piece.count("/") > 1:
        raise _err(
            f"{_FIELD_CN[name]}字段片段 {piece!r} 含有多个 '/'",
            name,
            piece,
            pos,
        )

    if "/" in piece:
        range_part, step_part = piece.split("/", 1)
        if step_part == "":
            raise _err(
                f"{_FIELD_CN[name]}字段片段 {piece!r} 缺少步进值",
                name,
                piece,
                pos,
            )
        if not step_part.isdigit():
            raise _err(
                f"{_FIELD_CN[name]}字段步进 {step_part!r} 必须是正整数",
                name,
                piece,
                pos,
            )
        step = int(step_part)
        if step <= 0:
            raise _err(
                f"{_FIELD_CN[name]}字段步进必须为正整数，不能是 {step}",
                name,
                piece,
                pos,
            )
    else:
        range_part, step = piece, None

    if range_part == "":
        raise _err(
            f"{_FIELD_CN[name]}字段片段 {piece!r} 在 '/' 前缺少范围",
            name,
            piece,
            pos,
        )

    if range_part == "*":
        start, end = lo, hi
        # Vixie 语义：凡是以 * 开头（含 */n）都设置星号位（DOM_STAR/DOW_STAR），
        # 即并集规则中视为“通配”；取值集合本身仍按步进受限于枚举结果。
        star = True
    elif "*" in range_part:
        raise _err(
            f"{_FIELD_CN[name]}字段片段 {piece!r} 中 '*' 只能单独使用或用于 '*/n'",
            name,
            piece,
            pos,
        )
    elif range_part.count("-") > 1:
        raise _err(
            f"{_FIELD_CN[name]}字段片段 {piece!r} 含有多个 '-'",
            name,
            piece,
            pos,
        )
    elif "-" in range_part:
        star = False
        left, right = range_part.split("-", 1)
        start = _parse_atom(name, left, piece, pos, lo, hi, names)
        end = _parse_atom(name, right, piece, pos, lo, hi, names)
        if start > end:
            raise _err(
                f"{_FIELD_CN[name]}字段范围 {range_part!r} 倒序：起点不能大于终点",
                name,
                piece,
                pos,
            )
    else:
        if step is not None:
            raise _err(
                f"{_FIELD_CN[name]}字段片段 {piece!r} 不支持 '值/步进' 写法，"
                f"请使用 '*/n' 或 'a-b/n'",
                name,
                piece,
                pos,
            )
        value = _parse_atom(name, range_part, piece, pos, lo, hi, names)
        return False, [value]

    if step is None:
        return star, list(range(start, end + 1))
    return star, list(range(start, end + 1, step))


def _parse_atom(
    name: str,
    atom: str,
    piece: str,
    pos: int,
    lo: int,
    hi: int,
    names: Optional[Dict[str, int]],
) -> int:
    """解析范围端点或单值：纯数字或（月/周字段的）名字。"""
    if atom == "":
        raise _err(
            f"{_FIELD_CN[name]}字段片段 {piece!r} 中 '-' 两侧缺少数值",
            name,
            piece,
            pos,
        )
    if not _ATOM.fullmatch(atom):
        raise _err(
            f"{_FIELD_CN[name]}字段片段 {piece!r} 中的 {atom!r} 不是合法的数值或名字",
            name,
            piece,
            pos,
        )
    if atom.isdigit():
        value = int(atom)
    else:
        upper = atom.upper()
        if names is None or upper not in names:
            raise _err(
                f"{_FIELD_CN[name]}字段不认识的名字 {atom!r}",
                name,
                piece,
                pos,
            )
        value = names[upper]

    if value < lo or value > hi:
        raise _err(
            f"{_FIELD_CN[name]}字段数值 {value} 超出允许范围 {lo}-{hi}",
            name,
            piece,
            pos,
        )
    return value
