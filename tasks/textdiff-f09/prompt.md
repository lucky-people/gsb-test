# 需求单：对齐 textdiff 的对外语义（textdiff-f09）

背景：我们把 textdiff 当成基础设施接进了业务链路（文本差异与三方合并引擎（Myers 最短编辑脚本 + unified diff 生成与套用 + diff3 风格合并））。接入测试发现它的实现与我们按 README 理解的语义不一致，先把不一致的地方列出来。

## 现象清单

| 编号 | 现象 |
|---|---|
| 1 | 区间长度为 1 时也带上了计数，与 unified 规范不一致 |
| 2 | 单独的 CR（经典 Mac 行尾）不再算行终止符，切成了一整行 |
| 3 | 冲突块的祖先起始行号少加了 1，替换/删除冲突定位偏一行 |
| 4 | hunk 分组的间隔阈值差一，间隔刚好的两处改动被错误合并 |

## 复现与失败用例

    python3 -m unittest test_textdiff -v

当前 10/42 条失败：

    FAIL: test_byte_identical_with_difflib_on_unique_lines
    FAIL: test_change_blocks_keep_document_order
    FAIL: test_conflicting_changes_emit_markers_and_conflict_block
    FAIL: test_crlf_lines_render_delete_before_insert
    FAIL: test_crlf_mix_does_not_swallow_or_attach_cr
    FAIL: test_delete_to_empty_old_side
    FAIL: test_empty_file_cases
    FAIL: test_insert_at_head_uses_zero_start_for_old_side
    FAIL: test_no_trailing_newline_keeps_marker_and_order
    FAIL: test_replace_block_renders_all_deletes_before_inserts

## 验收要求

1. 以上现象全部消除，42 条测试全绿；测试文件是验收基线，不允许修改或删除断言。
2. 实现必须满足下列硬性约束：
   - `apply(a, unified(a, b)) == b`，含 CRLF 混排、无结尾换行、空文件这些边界；
   - 同一输入多次生成的补丁完全一致，与 difflib 在唯一行文本上逐字节一致；
   - 上下文不匹配、行号越界、hunk 计数与正文不符、补丁结构非法一律抛 `PatchError`，带 hunk 序号与期望/实际内容；
   - 近相似大文本仍要在原来的量级完成，首尾公共前后缀归并不要去掉。
3. 每条现象对应一处独立根因（预计分布在 textdiff/merge.py、textdiff/myers.py、textdiff/patch.py），请逐一定位；只改一处会有用例继续红。
4. 为每处根因补回归测试；README 里与本需求相关的语义说明要与实现一致。
5. 交付物：`textdiff/patch.py`、`textdiff/merge.py`、`textdiff/myers.py`、`test_textdiff.py`、`README.md`。注释与报错信息使用中文，不得修改公开 API。
