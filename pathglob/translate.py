"""把 gitignore 风格的通配模式主体翻译成锚定正则。

只负责“模式主体 -> 正则源码”的纯转换，不处理 `!` 取反、
前导 `/`、结尾 `/` 这些外层语义（由 pattern.py 负责）。

支持语法：
    *       匹配任意个非 `/` 字符
    ?       匹配单个非 `/` 字符
    **      作为完整路径段时跨目录匹配；连续 `**` 段折叠为一个
    [abc]   字符类，支持 [a-z] 区间、[!a-z] / [^a-z] 取反、
            `]` 作为首字符时按字面处理
    \\x      反斜杠转义下一个字符（如 \\* 表示字面星号）
"""

import re

from .errors import PatternError


def _translate_class(content):
    """翻译字符类内容（不含外层方括号），返回正则片段。"""
    negated = content[:1] in ("!", "^")
    if negated:
        content = content[1:]
    items = []
    i = 0
    n = len(content)
    # `]` 作为首字符按字面处理
    if n and content[0] == "]":
        items.append("\\]")
        i = 1
    while i < n:
        c = content[i]
        if c == "\\" and i + 1 < n:
            items.append(re.escape(content[i + 1]))
            i += 2
            continue
        if c in ("\\", "]"):
            items.append("\\" + c)
        else:
            # `-` 原样保留以支持 a-z 区间
            items.append(c)
        i += 1
    inner = "".join(items)
    if negated:
        # 取反字符类同样不能匹配路径分隔符
        return "[^" + inner + "]"
    return "[" + inner + "]"


def _translate_segment(seg, original, base):
    """翻译单个路径段（不含 `/`）。

    返回 (正则片段, 字面文本)。字面文本是反转义后的真实文本；
    段内含任何通配结构（`*`、`?`、字符类）时为 None。
    """
    out = []
    lit = []
    i = 0
    n = len(seg)
    while i < n:
        c = seg[i]
        if c == "*":
            # 段内的连续星号（如 a**b）退化为单个 `*` 的语义
            while i < n and seg[i] == "*":
                i += 1
            out.append("[^/]*")
            lit = None
        elif c == "?":
            out.append("[^/]")
            lit = None
            i += 1
        elif c == "[":
            j = i + 1
            if j < n and seg[j] in ("!", "^"):
                j += 1
            if j < n and seg[j] == "]":
                j += 1
            k = j
            while k < n:
                if seg[k] == "\\":
                    k += 2
                    continue
                if seg[k] == "]":
                    break
                k += 1
            if k >= n:
                raise PatternError(original, base + i, '字符类 "[" 未闭合')
            out.append(_translate_class(seg[i + 1:k]))
            lit = None
            i = k + 1
        elif c == "\\":
            if i + 1 >= n:
                raise PatternError(
                    original, base + i, "反斜杠位于模式末尾，没有可转义的字符"
                )
            out.append(re.escape(seg[i + 1]))
            if lit is not None:
                # 转义序列贡献的是被转义的那个字符本身
                lit.append(seg[i + 1])
            i += 2
        else:
            out.append(re.escape(c))
            if lit is not None:
                lit.append(c)
            i += 1
    return "".join(out), (None if lit is None else "".join(lit))


def translate(body, anchored, directory_only, original, offset):
    """把模式主体翻译成完整正则源码。

    参数：
        body: 去掉 `!`、前导 `/`、结尾 `/` 之后的模式主体。
        anchored: 是否锚定到根（不再加任意深度前缀）。
        directory_only: 是否只匹配目录（会追加“自身或下级”后缀）。
        original / offset: 原始模式与主体在其中的偏移，用于报错定位。

    返回：
        (正则源码, 字面文本)。模式不含任何通配结构时，字面文本是
        反转义后的完整主体文本（供 Matcher 做字典分桶）；否则为 None。
    """
    raw_segments = body.split("/")
    segments = []
    pos = 0
    for seg in raw_segments:
        if seg == "":
            # 折叠重复斜杠（pattern.py 已处理，这里双保险）
            pos += 1
            continue
        if segments and segments[-1][0] == "**" and seg == "**":
            # 连续的 `**` 段折叠为一个
            pos += len(seg) + 1
            continue
        segments.append((seg, pos))
        pos += len(seg) + 1
    if not segments:
        raise PatternError(original, offset, "模式主体为空")

    parts = []
    lit_parts = []
    need_slash = False
    count = len(segments)
    for idx, (seg, segpos) in enumerate(segments):
        if seg == "**":
            lit_parts = None
            if count == 1:
                parts.append(".*")
            elif idx == count - 1:
                # 结尾 `/**`：匹配自身及下级所有内容
                parts.append("(?:/.*)?" if need_slash else ".*")
            else:
                # 中间 `/**/`：匹配零层或多层目录
                parts.append("/.*/" if need_slash else ".*/")
                need_slash = False
            continue
        seg_re, seg_lit = _translate_segment(seg, original, offset + segpos)
        if seg_lit is None:
            lit_parts = None
        elif lit_parts is not None:
            lit_parts.append(seg_lit)
        if need_slash:
            parts.append("/")
        parts.append(seg_re)
        need_slash = True

    body_re = "".join(parts)
    prefix = "" if anchored else "(?:.*/)?"
    if directory_only:
        # 目录规则：匹配目录自身（inside 不参与）或其下任意内容
        regex = "^" + prefix + body_re + "(?:/(?P<inside>.*))?$"
    else:
        regex = "^" + prefix + body_re + "$"
    literal = None if lit_parts is None else "/".join(lit_parts)
    return regex, literal
