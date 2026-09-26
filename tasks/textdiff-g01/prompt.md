# 回归批次 textdiff-g01：textdiff 用例执行报告

被测对象：textdiff（文本差异与三方合并引擎（Myers 最短编辑脚本 + unified diff 生成与套用 + diff3 风格合并））
执行方式：仓库根目录 `python3 -m unittest test_textdiff -v`
结果：14/42 失败，判定为**不通过**。

## 失败用例明细

| # | 类型 | 用例 |
|---|---|---|
| 1 | FAIL | test_byte_identical_with_difflib_on_unique_lines |
| 2 | FAIL | test_change_blocks_keep_document_order |
| 3 | FAIL | test_crlf_lines_render_delete_before_insert |
| 4 | FAIL | test_crlf_mix_does_not_swallow_or_attach_cr |
| 5 | FAIL | test_delete_to_empty_old_side |
| 6 | FAIL | test_empty_file_cases |
| 7 | FAIL | test_insert_at_head_uses_zero_start_for_old_side |
| 8 | FAIL | test_join_roundtrip |
| 9 | FAIL | test_malformed_patch_raises |
| 10 | FAIL | test_no_newline_marker_on_both_sides |
| 11 | FAIL | test_no_trailing_newline_keeps_marker_and_order |
| 12 | FAIL | test_replace_block_renders_all_deletes_before_inserts |
| 13 | FAIL | test_roundtrip_varied_contexts |
| 14 | FAIL | test_single_line_no_newline |

## 缺陷归类

| 编号 | 缺陷描述 |
|---|---|
| 1 | 区间长度为 1 时也带上了计数，与 unified 规范不一致 |
| 2 | 结尾没有行终止符的那一行被整行丢掉，往返时凭空少一行 |

归类依据：同一类缺陷在多条用例上重复出现，且分布在不同模块（textdiff/myers.py、textdiff/patch.py），因此判定为多处独立根因，而不是单一 bug 的连带影响。

## 修复要求

1. 让 42 条用例全部通过；测试文件为本批次的判定依据，禁止修改。
2. 修复后需满足下列行为约定：
   - `apply(a, unified(a, b)) == b`，含 CRLF 混排、无结尾换行、空文件这些边界；
   - 同一输入多次生成的补丁完全一致，与 difflib 在唯一行文本上逐字节一致；
   - 上下文不匹配、行号越界、hunk 计数与正文不符、补丁结构非法一律抛 `PatchError`，带 hunk 序号与期望/实际内容；
   - 近相似大文本仍要在原来的量级完成，首尾公共前后缀归并不要去掉。
3. 每一类缺陷补充对应回归用例，并保证新用例同样稳定通过。
4. 交付物：`textdiff/patch.py`、`textdiff/merge.py`、`textdiff/myers.py`、`test_textdiff.py`、`README.md`；注释与报错信息使用中文，公开 API 不得变更。
