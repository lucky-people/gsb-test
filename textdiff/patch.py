"""unified diff 生成与补丁严格套用。"""

import re
from typing import List, Tuple

from .errors import PatchError
from .myers import Edit, Line, diff_lines, join_lines, split_lines

# 形如 @@ -1,3 +1,4 @@ 的 hunk 头
_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _hunk_range(start_index: int, count: int) -> str:
    """按 unified diff 规则输出旧侧/新侧的 "起始行,行数"。

    行号 1 基；起始位置无行时（空文件插入）起始行号取 0；
    行数为 1 时省略 ",1"，行数为 0 时必须显式写 ",0"。
    """
    if count == 0:
        return f"{start_index},0"
    if count == 1:
        return str(start_index)
    return f"{start_index},{count}"


def unified(a: str, b: str, context: int = 3, *,
            a_name: str = "a", b_name: str = "b") -> str:
    """生成标准 unified diff 文本。

    context 为每个 hunk 保留的上下文行数；a、b 完全相同时返回空串。
    末尾缺少换行的行会在对应行之后追加 "\\ No newline at end of file"。
    """
    if context < 0:
        raise ValueError("上下文行数不能为负数")

    old = split_lines(a)
    new = split_lines(b)
    edits = diff_lines(old, new)
    changes = [edit for edit in edits if edit.op != "equal"]
    if not changes:
        return ""

    # 以"上下文间隙是否超过 2*context"决定 hunk 是否合并
    clusters: List[List[Edit]] = []
    for edit in edits:
        if edit.op == "equal":
            continue
        if not clusters:
            clusters.append([edit])
            continue
        last = clusters[-1][-1]
        gap = edit.start_a - last.end_a
        if gap > 2 * context:
            clusters.append([edit])
        else:
            clusters[-1].append(edit)

    pieces = [f"--- {a_name}\n", f"+++ {b_name}\n"]

    for cluster in clusters:
        first = cluster[0]
        last = cluster[-1]

        # hunk 在旧、新两侧覆盖的行下标区间（半开）
        start_a_idx = max(0, first.start_a - context)
        start_b_idx = max(0, first.start_b - context)
        end_a_idx = min(len(old), last.end_a + context)
        end_b_idx = min(len(new), last.end_b + context)

        # 起点之前能拿到多少上下文，两侧必须一致，取较小值再共同回退
        back_a = first.start_a - start_a_idx
        back_b = first.start_b - start_b_idx
        back = min(back_a, back_b)
        start_a_idx = first.start_a - back
        start_b_idx = first.start_b - back

        # 终点之后同理，两侧前进相同步数
        fwd_a = end_a_idx - last.end_a
        fwd_b = end_b_idx - last.end_b
        fwd = min(fwd_a, fwd_b)
        end_a_idx = last.end_a + fwd
        end_b_idx = last.end_b + fwd

        old_start_line = start_a_idx + 1 if end_a_idx > start_a_idx else start_a_idx
        new_start_line = start_b_idx + 1 if end_b_idx > start_b_idx else start_b_idx
        header = (
            "@@ -"
            + _hunk_range(old_start_line, end_a_idx - start_a_idx)
            + " +"
            + _hunk_range(new_start_line, end_b_idx - start_b_idx)
            + " @@\n"
        )

        body: List[str] = []

        def emit(line: Line, prefix: str) -> None:
            # 补丁记录始终以换行结尾；原行本身没有行尾时，用标记行说明
            body.append(prefix + line.content + (line.sep if line.sep else "\n"))
            if line.sep == "":
                body.append("\\ No newline at end of file\n")

        # 按顺序走完整编辑脚本，只输出落在 hunk 区间 [start_a_idx, end_a_idx) 内的部分
        for edit in edits:
            if edit.op == "equal":
                lo = max(start_a_idx, edit.start_a)
                hi = min(end_a_idx, edit.end_a)
                for offset in range(lo, hi):
                    emit(old[offset], " ")
            elif edit.op == "insert":
                # 插入点落在 hunk 覆盖范围内（含两端边界）时输出
                if start_a_idx <= edit.start_a <= end_a_idx:
                    for line in edit.lines_b:
                        emit(line, "+")
            elif edit.op == "delete":
                if edit.start_a < end_a_idx and edit.end_a > start_a_idx:
                    for line in edit.lines_a:
                        emit(line, "-")
            else:  # replace
                if edit.start_a < end_a_idx and edit.end_a > start_a_idx:
                    for line in edit.lines_a:
                        emit(line, "-")
                    for line in edit.lines_b:
                        emit(line, "+")

        pieces.append(header)
        pieces.extend(body)

    return "".join(pieces)


class _Hunk:
    """解析后的单个 hunk。"""

    __slots__ = ("index", "old_start", "old_count", "new_start", "new_count",
                 "body", "used_a", "used_b")

    def __init__(self, index: int, old_start: int, old_count: int,
                 new_start: int, new_count: int, body: List[Tuple[str, Line]]):
        self.index = index
        self.old_start = old_start
        self.old_count = old_count
        self.new_start = new_start
        self.new_count = new_count
        self.body = body
        self.used_a = sum(1 for kind, _ in body if kind in (" ", "-"))
        self.used_b = sum(1 for kind, _ in body if kind in (" ", "+"))


def _parse_patch(patch_text: str) -> List[_Hunk]:
    """把 unified diff 文本解析成 hunk 列表，格式错误一律抛 PatchError。"""
    lines = split_lines(patch_text)
    hunks: List[_Hunk] = []

    pos = 0
    saw_header = False
    while pos < len(lines):
        line = lines[pos]
        if line.content.startswith("--- "):
            if pos + 1 >= len(lines) or not lines[pos + 1].content.startswith("+++ "):
                raise PatchError("补丁文件头缺少对应的 +++ 行")
            saw_header = True
            pos += 2
            continue
        if line.content.startswith("+++ "):
            raise PatchError("出现孤立的 +++ 文件头行")
        if line.content.startswith("@@"):
            match = _HUNK_HEADER_RE.match(line.content)
            if not match:
                raise PatchError(f"第 {len(hunks) + 1} 个 hunk 头格式错误："
                                 f"期望形如 “@@ -a,b +c,d @@”，实际为 {line.content!r}")
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1

            pos += 1
            body: List[Tuple[str, Line]] = []
            while pos < len(lines):
                cur = lines[pos]
                content = cur.content
                if content.startswith("@@") or content.startswith("--- ") or content.startswith("+++ "):
                    break
                if content == "\\ No newline at end of file":
                    # 作用于上一行：把上一行的行尾去掉
                    if not body:
                        raise PatchError(f"第 {len(hunks) + 1} 个 hunk 中出现孤立的"
                                         "“\\ No newline at end of file”标记")
                    prev_kind, prev_line = body[-1]
                    body[-1] = (prev_kind, Line(prev_line.content, ""))
                    pos += 1
                    continue
                if content[:1] not in (" ", "-", "+"):
                    raise PatchError(f"第 {len(hunks) + 1} 个 hunk 的第 {len(body) + 1} 行"
                                     f"必须以空格、- 或 + 开头，实际为 {content!r}")
                body.append((content[0], Line(content[1:], cur.sep)))
                pos += 1

            hunk = _Hunk(len(hunks) + 1, old_start, old_count, new_start,
                         new_count, body)
            if hunk.used_a != old_count:
                raise PatchError(
                    f"第 {hunk.index} 个 hunk 头声明旧侧 {old_count} 行，"
                    f"但上下文与删除行实际有 {hunk.used_a} 行")
            if hunk.used_b != new_count:
                raise PatchError(
                    f"第 {hunk.index} 个 hunk 头声明新侧 {new_count} 行，"
                    f"但上下文与插入行实际有 {hunk.used_b} 行")
            hunks.append(hunk)
            continue
        raise PatchError(f"补丁中存在无法识别的行：{line.content!r}")

    if not hunks:
        if patch_text.strip() == "":
            return []
        if not saw_header:
            raise PatchError("补丁内容为空或不包含任何 hunk")
        raise PatchError("补丁只有文件头、没有任何 hunk")
    return hunks


def apply(text: str, patch: str) -> str:
    """严格套用 unified diff。

    只按 hunk 头声明的行号对位、逐行核对上下文与删除内容；
    任何行号越界、内容不符或补丁格式问题都抛 PatchError，绝不猜测套用。
    """
    hunks = _parse_patch(patch)
    if not hunks:
        return text

    current = split_lines(text)
    delta = 0  # 之前 hunk 造成的累计行数变化

    for hunk in hunks:
        # 声明的行号是 1 基，转成 current 中的 0 基下标
        pos = hunk.old_start - 1 + delta
        if hunk.old_count == 0:
            pos = hunk.old_start + delta
        if pos < 0 or pos + hunk.used_a > len(current):
            raise PatchError(
                f"第 {hunk.index} 个 hunk 行号越界：期望从原文第 {hunk.old_start} 行开始的"
                f" {hunk.used_a} 行，但原文只有 {len(current)} 行")

        expected_old = [line for kind, line in hunk.body if kind in (" ", "-")]
        actual = current[pos : pos + hunk.used_a]
        for offset, (expected, got) in enumerate(zip(expected_old, actual)):
            if expected != got:
                raise PatchError(
                    f"第 {hunk.index} 个 hunk 在原文第 {pos + offset + 1} 行内容不符："
                    f"期望 {expected.content + expected.sep!r}，"
                    f"实际 {got.content + got.sep!r}")

        replacement = [line for kind, line in hunk.body if kind in (" ", "+")]
        current[pos : pos + hunk.used_a] = replacement
        delta += hunk.used_b - hunk.used_a

    return join_lines(current)
