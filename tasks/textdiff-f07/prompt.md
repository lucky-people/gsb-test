PR 评审意见 —— textdiff：逻辑调整（textdiff-f07）

结论：先别合。基线在 `python3 -m unittest test_textdiff -v` 下已经红 13/42 条，逐条写在下面。

1. 某一侧一行都没有时起始行号多加了 1，文件开头插入这类补丁号错位
2. 结尾没有行终止符的那一行被整行丢掉，往返时凭空少一行
3. 没有行终止符的最后一行丢了「未结束」标注，往返时差一个结尾

失败的用例：

    ERROR: test_byte_identical_with_difflib_on_unique_lines
    FAIL: test_crlf_mix_does_not_swallow_or_attach_cr
    FAIL: test_empty_file_cases
    FAIL: test_empty_to_text_and_text_to_empty
    FAIL: test_insert_at_head_uses_zero_start_for_old_side
    FAIL: test_join_roundtrip
    FAIL: test_malformed_patch_raises
    ERROR: test_no_newline_marker_on_both_sides
    FAIL: test_no_trailing_newline_keeps_marker_and_order
    FAIL: test_pure_insert_and_pure_delete
    FAIL: test_randomized_roundtrip_and_shortest
    FAIL: test_roundtrip_varied_contexts
    FAIL: test_single_line_no_newline

几点说明：

1. 上面每一条我都在本地单独验过，症状各自独立，改一处不会让另一处跟着好。改动面看着分散在 textdiff/myers.py、textdiff/patch.py。
2. 修的时候别动 `test_textdiff.py` 里的断言——那份测试是验收基线，写的是这个包对外承诺的行为，红了说明实现错了，不是测试写错了。
3. 下面这些约束请一起保持：
   - `apply(a, unified(a, b)) == b`，含 CRLF 混排、无结尾换行、空文件这些边界；
   - 同一输入多次生成的补丁完全一致，与 difflib 在唯一行文本上逐字节一致；
   - 上下文不匹配、行号越界、hunk 计数与正文不符、补丁结构非法一律抛 `PatchError`，带 hunk 序号与期望/实际内容；
   - 近相似大文本仍要在原来的量级完成，首尾公共前后缀归并不要去掉。
4. 每条根因都要补回归测试，别只把现有用例弄绿就算完；README 对应段落（语义说明、边界取舍）要跟实现对齐。
5. 交付范围：`textdiff/patch.py`、`textdiff/merge.py`、`textdiff/myers.py`、`test_textdiff.py`、`README.md`。注释与报错保持中文，公开 API 签名不要改。
