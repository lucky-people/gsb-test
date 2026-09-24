【缺陷报告】textdiff：unified 形态与冲突区间同时出错，42 条里挂了 6 条

    FAIL: test_replace_block_renders_all_deletes_before_inserts
    FAIL: test_byte_identical_with_difflib_on_unique_lines
    FAIL: test_crlf_lines_render_delete_before_insert
    FAIL: test_no_trailing_newline_keeps_marker_and_order
    FAIL: test_change_blocks_keep_document_order
    FAIL: test_conflicting_changes_emit_markers_and_conflict_block

复现：

    python3 -m unittest test_textdiff -v

两组症状：

1. 替换块内部把插入行排到了删除行前面（现在是 `+` 先、`-` 后），与 GNU diff / difflib 的规范形态相反；含 CRLF、无结尾换行、多改动块的用例跟着一起红。
2. `merge` 的冲突块区间不再按 README 约定的「1 基半开」给出：替换/删除冲突应当报 `[lo+1, hi+1)`，纯插入冲突保持插入点语义（`lo == hi`，0 表示文件开头、N 表示第 N 行之后），现在整体错位。
   另外要核对 hunk 合并边界：两个改动之间正好有 `2*context` 行公共上下文时必须合并成一个 hunk，现在会拆成两个。

要求：

1. unified 的替换块内部严格「先输出全部删除行，再输出全部插入行」，不同改动块之间仍按文档顺序；与 `difflib.unified_diff`（`fromfile="a"`、`tofile="b"`）在唯一行文本上、context 取 0/1/3/5 时逐字节一致（写一条随机 1000 组的对照测试或脚本）。
2. hunk 合并边界按 GNU 规则：间隔公共行少于 `2*context+1` 时合并，正好等于 `2*context+1` 时拆开；边界两侧都要有断言。
3. 冲突块 `base_start/base_end` 恢复 README 的 1 基半开约定，并满足不变量「用 base 原文按该区间切片，正好是冲突覆盖的行（纯插入冲突为空）」。
4. 原有 42 条测试全部恢复通过，不许改断言；`apply` 往返（含 CRLF、无结尾换行）与 `merge` 的既有语义（单侧改动自动采用、双侧改成相同内容不算冲突、相邻但不重叠的改动自动拼接）保持不变。
5. 补回归测试覆盖两组根因，并在 README 的 unified 与 merge 两节把「删除先于插入」和「1 基半开区间」写清楚。

交付：改 `textdiff/patch.py`、`textdiff/merge.py`、`test_textdiff.py`、`README.md`；中文注释与报错；不动 `diff()`/Myers 最短编辑脚本的语义。
