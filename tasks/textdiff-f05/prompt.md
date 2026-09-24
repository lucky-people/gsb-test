“textdiff 这个包你帮我看下，我这边结果不对。”

“什么现象？”

“我列了几个，都是真跑出来的：

- 同一个替换块里先插后删，渲染顺序与 GNU diff 的规范形态相反
- 结尾没有行终止符的那一行被整行丢掉，往返时凭空少一行
- 区间长度为 1 时也带上了计数，与 unified 规范不一致

”

“先跑一遍测试确认下？”

“跑了，仓库根目录 `python3 -m unittest test_textdiff -v`，14/42 条红：

    FAIL: test_byte_identical_with_difflib_on_unique_lines
    FAIL: test_change_blocks_keep_document_order
    FAIL: test_crlf_lines_render_delete_before_insert
    FAIL: test_crlf_mix_does_not_swallow_or_attach_cr
    FAIL: test_delete_to_empty_old_side
    FAIL: test_empty_file_cases
    FAIL: test_insert_at_head_uses_zero_start_for_old_side
    FAIL: test_join_roundtrip
    FAIL: test_malformed_patch_raises
    FAIL: test_no_newline_marker_on_both_sides
    FAIL: test_no_trailing_newline_keeps_marker_and_order
    FAIL: test_replace_block_renders_all_deletes_before_inserts
    FAIL: test_roundtrip_varied_contexts
    FAIL: test_single_line_no_newline

”

“看着不像一处问题。”

“我也这么觉得，textdiff/myers.py、textdiff/patch.py 我都翻过，几个地方都可疑。麻烦你排一下，要求是：

1. 42 条测试全部弄绿，别改测试文件——那是验收基线；
2. 这些行为不能变：
   - `apply(a, unified(a, b)) == b`，含 CRLF 混排、无结尾换行、空文件这些边界；
   - 同一输入多次生成的补丁完全一致，与 difflib 在唯一行文本上逐字节一致；
   - 上下文不匹配、行号越界、hunk 计数与正文不符、补丁结构非法一律抛 `PatchError`，带 hunk 序号与期望/实际内容；
   - 近相似大文本仍要在原来的量级完成，首尾公共前后缀归并不要去掉。
3. 每处根因补一条回归测试，README 里说不清楚的地方一起补；
4. 交付 `textdiff/patch.py`、`textdiff/merge.py`、`textdiff/myers.py`、`test_textdiff.py`、`README.md`，注释和报错用中文。”
