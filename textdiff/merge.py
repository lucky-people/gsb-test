"""基于两侧最短编辑脚本的三方合并（diff3 风格）。"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .myers import Edit, Line, diff_lines, join_lines, split_lines


@dataclass(frozen=True)
class ConflictBlock:
    """一个冲突块在原文（base）中的位置与两侧内容。

    base_start / base_end 为 0 基半开区间：
    - 替换冲突：被冲突覆盖的 base 行区间；
    - 纯插入冲突：base_start == base_end，指向插入位置（在该行之前）。
    """

    base_start: int
    base_end: int
    ours_lines: Tuple[Line, ...]
    theirs_lines: Tuple[Line, ...]

    @property
    def ours_text(self) -> str:
        return join_lines(self.ours_lines)

    @property
    def theirs_text(self) -> str:
        return join_lines(self.theirs_lines)


@dataclass(frozen=True)
class MergeResult:
    """合并结果：text 是最终文本；conflicts 为空时表示干净合并。"""

    text: str
    conflicts: Tuple[ConflictBlock, ...]

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


@dataclass(frozen=True)
class _Change:
    """一侧相对 base 的一段改动（相邻的非 equal 编辑已合并）。"""

    lo: int  # base 区间起点（含），插入时等于 hi
    hi: int  # base 区间终点（不含）
    lines: Tuple[Line, ...]  # 该侧的新内容


def _changes_from_edits(edits: Sequence[Edit]) -> List[_Change]:
    """把编辑脚本归并成"改动区间"序列，相邻的删除/插入/替换连成一块。"""
    changes: List[_Change] = []
    for edit in edits:
        if edit.op == "equal":
            continue
        if changes and changes[-1].hi == edit.start_a:
            prev = changes[-1]
            changes[-1] = _Change(prev.lo, edit.end_a, prev.lines + edit.lines_b)
        else:
            changes.append(_Change(edit.start_a, edit.end_a, edit.lines_b))
    return changes


def _overlap(c1: _Change, c2: _Change) -> bool:
    """两段改动是否触碰同一处 base 区域。

    - 两侧都是纯插入时，只有插入点完全相同才算同一处；
      不同插入点的插入互不冲突，应各自落地；
    - 一侧插入、另一侧替换/删除时，插入点落在对方区域的闭区间内即算触碰，
      避免相邻改动因 diff 选路不同而漏报冲突；
    - 两侧都替换/删除时，按半开区间是否相交判断。
    """
    if c1.lo == c1.hi and c2.lo == c2.hi:
        return c1.lo == c2.lo
    if c1.lo == c1.hi:
        return c2.lo <= c1.lo <= c2.hi
    if c2.lo == c2.hi:
        return c1.lo <= c2.lo <= c1.hi
    return not (c1.hi <= c2.lo or c2.hi <= c1.lo)


def merge(base: str, ours: str, theirs: str) -> MergeResult:
    """三方合并。

    - 某侧未改动：采用另一侧；
    - 两侧改动区间互不相交：各自落地；
    - 两侧改动落在同一区域且结果内容完全相同：只采用一份，不算冲突；
    - 两侧改动落在同一区域但内容不同：插入 <<<<<<< / ======= / >>>>>>>
      冲突标记，并在 conflicts 中给出可定位回 base 的行号区间。
    """
    base_lines = split_lines(base)
    ours_lines = split_lines(ours)
    theirs_text_lines = split_lines(theirs)

    # 常见快路：一侧与 base 完全相同
    if ours_lines == base_lines:
        return MergeResult(theirs, ())
    if theirs_text_lines == base_lines:
        return MergeResult(ours, ())

    our_changes = _changes_from_edits(diff_lines(base_lines, ours_lines))
    their_changes = _changes_from_edits(diff_lines(base_lines, theirs_text_lines))

    # 并查集：把相互触碰的两侧改动归入同一冲突组
    all_changes = [("ours", c) for c in our_changes] + [("theirs", c) for c in their_changes]
    parent = list(range(len(all_changes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        root_x, root_y = find(x), find(y)
        if root_x != root_y:
            parent[root_y] = root_x

    for i in range(len(all_changes)):
        for j in range(i + 1, len(all_changes)):
            if _overlap(all_changes[i][1], all_changes[j][1]):
                union(i, j)

    # 必须等所有 union 完成后再按最终根分组，否则中途的根会失效
    groups = {}
    for idx, item in enumerate(all_changes):
        groups.setdefault(find(idx), []).append(item)

    def _side_view(changes: List[_Change], lo: int, hi: int) -> Tuple[Line, ...]:
        """按 base 的 [lo, hi) 区间重建某一侧的完整内容（含未改动的中间行）。"""
        view: List[Line] = []
        pos = lo
        for change in sorted(changes, key=lambda c: c.lo):
            view.extend(base_lines[pos:change.lo])
            view.extend(change.lines)
            pos = change.hi
        view.extend(base_lines[pos:hi])
        return tuple(view)

    @dataclass
    class _Piece:
        lo: int
        hi: int
        lines: Tuple[Line, ...]
        conflict: Optional[ConflictBlock]

    pieces: List[_Piece] = []
    for group in groups.values():
        lo = min(change.lo for _, change in group)
        hi = max(change.hi for _, change in group)
        ours_group = [change for side, change in group if side == "ours"]
        theirs_group = [change for side, change in group if side == "theirs"]
        ours_content = _side_view(ours_group, lo, hi)
        theirs_content = _side_view(theirs_group, lo, hi)

        if not ours_group or not theirs_group:
            # 只有一侧改动：直接采用
            pieces.append(_Piece(lo, hi, group[0][1].lines, None))
        elif ours_content == theirs_content:
            # 两侧改成完全相同：采用一份，不冲突
            pieces.append(_Piece(lo, hi, ours_content, None))
        else:
            block = ConflictBlock(lo, hi, ours_content, theirs_content)
            pieces.append(_Piece(lo, hi, ours_content, block))

    # 按 base 位置排序；同一位置（lo==hi 的插入）不会出现在不同 piece 之间，
    # 因为同插入点的改动已被上面的并查集合到一组
    pieces.sort(key=lambda p: p.lo)

    output: List[Line] = []
    conflicts: List[ConflictBlock] = []
    cursor = 0

    def emit_marker(text: str) -> None:
        # 冲突标记使用 LF；标记行本身一定带换行，除非位于文件最末尾
        output.append(Line(text, "\n"))

    for piece in pieces:
        output.extend(base_lines[cursor:piece.lo])
        if piece.conflict is None:
            output.extend(piece.lines)
        else:
            conflicts.append(piece.conflict)
            emit_marker("<<<<<<< ours")
            output.extend(piece.conflict.ours_lines)
            emit_marker("=======")
            output.extend(piece.conflict.theirs_lines)
            emit_marker(">>>>>>> theirs")
        cursor = piece.hi

    output.extend(base_lines[cursor:])

    # 若冲突标记恰好落在文件末尾，最后一个标记行不补换行，保持"无结尾换行"的确定性
    if output and output[-1] == Line(">>>>>>> theirs", "\n"):
        output[-1] = Line(">>>>>>> theirs", "")

    return MergeResult(join_lines(output), tuple(conflicts))
