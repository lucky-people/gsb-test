"""unified diff 的生成与精确套用。"""

from __future__ import annotations

import re
from typing import Optional

from .errors import PatchError
from .myers import Edit, Line, diff as _diff, join_lines, split_lines


_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@$")
NO_NEWLINE_MARKER = "\\ No newline at end of file"

# 流式正文条目：(前缀, 行, 旧文件绝对下标或 None, 新文件绝对下标或 None)。
_Op = tuple[str, Line, Optional[int], Optional[int]]


def _range_field(start: int, length: int) -> str:
    """unified 头里的区间字段：长度为 1 时省略计数。"""
    return str(start) if length == 1 else f"{start},{length}"


def _render_body_line(prefix: str, line: Line) -> list[str]:
    """渲染一行 hunk 正文；无行终止符的行补「未结束」标注。"""
    if line.ending:
        return [prefix + line.render()]
    return [prefix + line.text, "\n", NO_NEWLINE_MARKER, "\n"]


def _stream_edit(edit: Edit, a: list[Line], b: list[Line]) -> list[_Op]:
    """按文档顺序输出单个编辑块的带前缀行，并记录绝对行下标。

    replace 块（一段连续的「先删后插」改动）统一先输出全部删除行、
    再输出全部插入行，与 GNU diff / difflib 的渲染形态保持一致；
    不同编辑块之间仍按文档顺序排列。
    """
    if edit.tag == "equal":
        return [(" ", a[idx], idx, edit.b_start + (idx - edit.a_start))
                for idx in range(edit.a_start, edit.a_end)]
    if edit.tag == "delete":
        return [("-", a[idx], idx, None)
                for idx in range(edit.a_start, edit.a_end)]
    if edit.tag == "insert":
        return [("+", b[idx], None, idx)
                for idx in range(edit.b_start, edit.b_end)]

    ops: list[_Op] = [("-", a[idx], idx, None)
                      for idx in range(edit.a_start, edit.a_end)]
    ops.extend(("+", b[idx], None, idx)
               for idx in range(edit.b_start, edit.b_end))
    return ops


def _build_hunks(edits: list[Edit], a: list[Line], b: list[Line],
                 context: int) -> list[dict]:
    """按 GNU unified 规则把编辑块分组为若干 hunk。

    每个非 equal 编辑块（含其内部相等行）整体属于某个 hunk；
    两个非 equal 块之间若放不下 ``2*context`` 行纯上下文则合并；
    hunk 两端各带至多 context 行上下文；起始行号与计数由实际正文统计。
    """
    changed_indexes = [idx for idx, edit in enumerate(edits)
                       if edit.tag != "equal"]
    if not changed_indexes:
        return []

    groups: list[list[int]] = [[changed_indexes[0]]]
    for pos in range(1, len(changed_indexes)):
        edit_idx = changed_indexes[pos]
        prev_change_idx = changed_indexes[pos - 1]
        # 两个相邻改动块之间若有且仅有一个 equal 块，它就是间隔；
        # 若 edit_idx == prev_change_idx + 1，则两改动块直接相邻。
        if edit_idx == prev_change_idx + 1:
            groups[-1].append(edit_idx)
            continue
        gap_edit = edits[prev_change_idx + 1]
        # 中间没有 equal（两个改动块相邻）必然合并；
        # 间隔相等行不足「两端各 context 行 + 至少 1 个公共行」也合并。
        if gap_edit.tag != "equal" or \
                (gap_edit.a_end - gap_edit.a_start) < 2 * context + 1:
            groups[-1].append(edit_idx)
        else:
            groups.append([edit_idx])

    hunks: list[dict] = []
    for group in groups:
        first, last = group[0], group[-1]
        ops: list[_Op] = []

        lead = edits[first - 1] if first > 0 and \
            edits[first - 1].tag == "equal" else None
        if lead is not None:
            keep = min(context, lead.a_end - lead.a_start)
            for idx in range(lead.a_end - keep, lead.a_end):
                ops.append((" ", a[idx], idx,
                            lead.b_start + (idx - lead.a_start)))
        for edit_idx in range(first, last + 1):
            ops.extend(_stream_edit(edits[edit_idx], a, b))
        tail = edits[last + 1] if last < len(edits) - 1 and \
            edits[last + 1].tag == "equal" else None
        if tail is not None:
            keep = min(context, tail.a_end - tail.a_start)
            for idx in range(tail.a_start, tail.a_start + keep):
                ops.append((" ", a[idx], idx,
                            tail.b_start + (idx - tail.a_start)))

        old_count = sum(1 for op, *_ in ops if op != "+")
        new_count = sum(1 for op, *_ in ops if op != "-")
        first_edit = edits[first]
        old_start0 = next(
            (old_idx for op, _, old_idx, _ in ops if old_idx is not None),
            first_edit.a_start)
        new_start0 = next(
            (new_idx for op, _, _, new_idx in ops if new_idx is not None),
            first_edit.b_start)
        old_display = old_start0 + 1
        new_display = new_start0 + 1 if new_count > 0 else new_start0

        header = (f"@@ -{_range_field(old_display, old_count)} "
                  f"+{_range_field(new_display, new_count)} @@\n")
        body: list[str] = []
        for prefix, line, _, _ in ops:
            body.extend(_render_body_line(prefix, line))
        hunks.append({"header": header, "body": body,
                      "old_start": old_display, "old_count": old_count,
                      "new_start": new_display, "new_count": new_count})
    return hunks


def unified(a: str, b: str, context: int = 3) -> str:
    """生成标准 unified diff 文本。

    两份输入完全相同时返回空串。文件头固定为 ``--- a`` / ``+++ b``，
    因为本模块只处理文本内容，不携带真实文件名。
    """
    if context < 0:
        raise ValueError("上下文行数不能为负数")
    edits = _diff(a, b)
    if all(edit.tag == "equal" for edit in edits):
        return ""
    hunks = _build_hunks(edits, split_lines(a), split_lines(b), context)
    parts = ["--- a\n", "+++ b\n"]
    for hunk in hunks:
        parts.append(hunk["header"])
        parts.extend(hunk["body"])
    return "".join(parts)


# ---------------------------------------------------------------------------
# 补丁解析与套用
# ---------------------------------------------------------------------------


class _ParsedHunk:
    """解析后的单个 hunk。"""

    def __init__(self, old_start: int, old_count: int,
                 new_start: int, new_count: int,
                 ops: list[tuple[str, Line]]):
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.ops = ops


def _parse_patch(patch: str) -> list[_ParsedHunk]:
    """把 unified diff 文本解析成结构化 hunk；任何不合法处都抛 PatchError。"""
    physical = split_lines(patch)
    if not physical:
        return []
    if len(physical) < 2 or not physical[0].text.startswith("--- ") \
            or not physical[1].text.startswith("+++ "):
        raise PatchError("补丁缺少合法的 --- / +++ 文件头")

    hunks: list[_ParsedHunk] = []
    index = 2
    total = len(physical)
    while index < total:
        match = _HUNK_HEADER_RE.match(physical[index].text)
        if not match:
            raise PatchError(
                f"第 {len(hunks) + 1} 个 hunk 处遇到无法识别的行："
                f"期望 hunk 头（@@ ... @@），实际为 "
                f"{physical[index].text!r}")
        index += 1
        old_start = int(match.group(1))
        old_count = int(match.group(2)) if match.group(2) is not None else 1
        new_start = int(match.group(3))
        new_count = int(match.group(4)) if match.group(4) is not None else 1
        hunk_no = len(hunks) + 1
        ops: list[tuple[str, Line]] = []
        expect_old = 0
        expect_new = 0

        while index < total and not physical[index].text.startswith("@@"):
            pline = physical[index]
            if pline.text == NO_NEWLINE_MARKER:
                if not ops:
                    raise PatchError(
                        f"第 {hunk_no} 个 hunk 的「未结束」标注前缺少内容行")
                last_op, last_line = ops[-1]
                if last_line.ending == "":
                    raise PatchError(
                        f"第 {hunk_no} 个 hunk 出现连续的「未结束」标注")
                ops[-1] = (last_op, Line(last_line.text, ""))
                index += 1
                continue
            if not pline.ending or pline.text[:1] not in (" ", "-", "+"):
                raise PatchError(
                    f"第 {hunk_no} 个 hunk 的正文行 {pline.text!r} 不合法："
                    "必须以空格、减号或加号开头，且带行终止符"
                    "（无终止符的行须有「未结束」标注）")
            prefix = pline.text[0]
            content = Line(pline.text[1:], pline.ending)
            if prefix == " ":
                ops.append(("context", content))
                expect_old += 1
                expect_new += 1
            elif prefix == "-":
                ops.append(("del", content))
                expect_old += 1
            else:
                ops.append(("ins", content))
                expect_new += 1
            index += 1

        if expect_old != old_count:
            raise PatchError(
                f"第 {hunk_no} 个 hunk 头声明旧侧 {old_count} 行，"
                f"正文实际为 {expect_old} 行")
        if expect_new != new_count:
            raise PatchError(
                f"第 {hunk_no} 个 hunk 头声明新侧 {new_count} 行，"
                f"正文实际为 {expect_new} 行")
        hunks.append(_ParsedHunk(old_start, old_count,
                                 new_start, new_count, ops))
    return hunks


def apply(text: str, patch: str) -> str:
    """精确套用 unified diff。

    任何上下文不匹配、行号越界或行内容不符都抛 :class:`PatchError`，
    绝不静默猜测；空补丁表示不做任何修改。
    """
    target = split_lines(text)
    hunks = _parse_patch(patch)
    if not hunks:
        return text

    output: list[Line] = []
    cursor = 0
    target_len = len(target)

    for hunk_no, hunk in enumerate(hunks, start=1):
        pos = hunk.old_start if hunk.old_count == 0 else hunk.old_start - 1
        if pos < 0 or pos > target_len:
            raise PatchError(
                f"第 {hunk_no} 个 hunk 的起始行号 {hunk.old_start} 越界，"
                f"原文共 {target_len} 行",
                hunk_index=hunk_no, line_no=hunk.old_start)
        if pos < cursor:
            raise PatchError(
                f"第 {hunk_no} 个 hunk 与前一个 hunk 位置重叠",
                hunk_index=hunk_no)

        output.extend(target[cursor:pos])
        scan = pos
        for op_tag, line in hunk.ops:
            if op_tag == "ins":
                output.append(line)
                continue
            if scan >= target_len:
                raise PatchError(
                    f"第 {hunk_no} 个 hunk 行号越界：原文只有 "
                    f"{target_len} 行，但补丁还要求第 {scan + 1} 行",
                    hunk_index=hunk_no, expected=line.render(),
                    actual="<文件已结束>", line_no=scan + 1)
            actual = target[scan]
            if actual != line:
                raise PatchError(
                    f"第 {hunk_no} 个 hunk 第 {scan + 1} 行内容不匹配："
                    f"期望 {line.render()!r}，实际 {actual.render()!r}",
                    hunk_index=hunk_no, expected=line.render(),
                    actual=actual.render(), line_no=scan + 1)
            if op_tag == "context":
                output.append(actual)
            scan += 1
        if scan - pos != hunk.old_count:
            raise PatchError(
                f"第 {hunk_no} 个 hunk 内部行号统计异常",
                hunk_index=hunk_no)
        cursor = scan

    output.extend(target[cursor:])
    return join_lines(output)
