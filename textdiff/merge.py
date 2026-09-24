"""基于两路最短编辑脚本的三方合并（diff3 风格）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .myers import Edit, Line, join_lines, line_diff, split_lines


@dataclass
class Conflict:
    """一个冲突块。

    base_start/base_end 为共同祖先文件中的行号区间（1 基半开）：
    - 替换/删除冲突时为 [lo+1, hi+1)，即被改动的祖先行范围；
    - 纯插入冲突（lo == hi）时记录插入点位置，0 表示文件开头，
      N 表示第 N 行之后；
    - ours_lines / theirs_lines 为两侧各自完整行文本（含行终止符）。
    """

    base_start: int
    base_end: int
    ours_lines: list[str]
    theirs_lines: list[str]
    ours_label: str = "ours"
    theirs_label: str = "theirs"

    @property
    def source(self) -> str:
        return f"{self.ours_label} vs {self.theirs_label}"


@dataclass
class MergeResult:
    """合并结果文本与冲突块列表。"""

    merged: str
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


def _changes(edits: list[Edit]) -> list[Edit]:
    """从编辑脚本中挑出非 equal 块。"""
    return [edit for edit in edits if edit.tag != "equal"]


def _render_region(changes: list[Edit], base_lo: int, base_hi: int,
                   base: list[Line], side: list[Line]) -> list[Line]:
    """渲染某一侧在祖先区间 [base_lo, base_hi) 上的合并结果。"""
    result: list[Line] = []
    cursor = base_lo
    for edit in changes:
        if edit.a_end < base_lo or edit.a_start > base_hi:
            continue
        if cursor < edit.a_start:
            result.extend(base[cursor:edit.a_start])
        if edit.tag in ("insert", "replace"):
            result.extend(side[edit.b_start:edit.b_end])
        cursor = edit.a_end
    if cursor < base_hi:
        result.extend(base[cursor:base_hi])
    return result


def _marker(text: str) -> Line:
    return Line(text, "\n")


def merge(base: str, ours: str, theirs: str,
          ours_label: str = "ours",
          theirs_label: str = "theirs") -> MergeResult:
    """三方合并。

    - 只有一侧改动：自动采用该侧结果；
    - 两侧都改但合并区间渲染结果逐行相同：视为双方一致，不产生冲突；
    - 两侧改动落在同一处（区间相交或插入点相同）且结果不同：
      输出 ``<<<<<<<`` / ``=======`` / ``>>>>>>>`` 冲突标记；
    - 相邻但不重叠的改动自动拼接，互不干扰。
    """
    base_l = split_lines(base)
    ours_l = split_lines(ours)
    theirs_l = split_lines(theirs)
    our_edits = _changes(line_diff(base_l, ours_l))
    their_edits = _changes(line_diff(base_l, theirs_l))

    # 收集两侧全部改动并按祖先坐标排序；区间相交或起点恰好相接
    #（同一插入点 [p, p)）时归为一簇。
    spans: list[tuple[int, int, Edit, str]] = []
    for edit in our_edits:
        spans.append((edit.a_start, edit.a_end, edit, "ours"))
    for edit in their_edits:
        spans.append((edit.a_start, edit.a_end, edit, "theirs"))
    spans.sort(key=lambda item: (item[0], item[1], item[3]))

    clusters: list[dict] = []
    for lo, hi, edit, side_name in spans:
        # 区间严格相交必须合并；同一插入点的两个零长插入 [p,p) 也合并。
        # 普通改动仅在边界相接（如改第 2 行 vs 改第 3 行）不合并。
        prev = clusters[-1] if clusters else None
        zero_point = lo == hi and prev is not None and \
            prev["lo"] == prev["hi"] == lo
        if prev is not None and (lo < prev["hi"] or zero_point):
            clusters[-1]["hi"] = max(clusters[-1]["hi"], hi)
            clusters[-1]["items"].append((lo, hi, edit, side_name))
        else:
            clusters.append({"lo": lo, "hi": hi,
                             "items": [(lo, hi, edit, side_name)]})

    output: list[Line] = []
    conflicts: list[Conflict] = []
    cursor = 0
    total_base = len(base_l)

    def ensure_newline() -> None:
        """冲突标记另起一行：给没有行终止符的末行补换行。"""
        if output and output[-1].ending == "":
            output[-1] = Line(output[-1].text, "\n")

    for cluster in clusters:
        lo, hi = cluster["lo"], cluster["hi"]
        output.extend(base_l[cursor:lo])
        ours_items = [item for item in cluster["items"]
                      if item[3] == "ours"]
        theirs_items = [item for item in cluster["items"]
                        if item[3] == "theirs"]

        if ours_items and not theirs_items:
            output.extend(_render_region(
                [item[2] for item in ours_items], lo, hi,
                base_l, ours_l))
        elif theirs_items and not ours_items:
            output.extend(_render_region(
                [item[2] for item in theirs_items], lo, hi,
                base_l, theirs_l))
        else:
            ours_block = _render_region(
                [item[2] for item in ours_items], lo, hi,
                base_l, ours_l)
            theirs_block = _render_region(
                [item[2] for item in theirs_items], lo, hi,
                base_l, theirs_l)
            if ours_block == theirs_block:
                # 两侧改成完全相同的内容：视为双方一致，不产生冲突。
                output.extend(ours_block)
            else:
                ensure_newline()
                output.append(_marker(f"<<<<<<< {ours_label}"))
                output.extend(ours_block)
                ensure_newline()
                output.append(_marker("======="))
                output.extend(theirs_block)
                ensure_newline()
                output.append(_marker(f">>>>>>> {theirs_label}"))
                # 1 基半开区间：替换/删除 [lo,hi) -> [lo+1, hi+1)；
                # 纯插入 lo == hi 时记录插入点（0=文件开头，N=第 N 行后）。
                base_start = lo
                conflicts.append(Conflict(
                    base_start=base_start,
                    base_end=hi,
                    ours_lines=[line.render() for line in ours_block],
                    theirs_lines=[line.render() for line in theirs_block],
                    ours_label=ours_label,
                    theirs_label=theirs_label))
        cursor = hi

    output.extend(base_l[cursor:total_base])
    return MergeResult(merged=join_lines(output), conflicts=conflicts)
