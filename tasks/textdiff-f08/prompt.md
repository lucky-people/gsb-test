您好，反馈一个 textdiff 的问题（工单 textdiff-f08）

我们把这个包接进了生产的处理链路，最近运维那边报了几类异常，麻烦帮忙看下。我们不是专业审代码的，只能把现象描述清楚：

- 单独的 CR（经典 Mac 行尾）不再算行终止符，切成了一整行
- 冲突块的祖先起始行号少加了 1，替换/删除冲突定位偏一行
- 结尾没有行终止符的那一行被整行丢掉，往返时凭空少一行
- 某一侧一行都没有时起始行号多加了 1，文件开头插入这类补丁号错位

我们自己复现的方式就是在仓库根目录跑：

    python3 -m unittest test_textdiff -v

现在 42 条里红 14 条，红的名字如下：

    ERROR: test_byte_identical_with_difflib_on_unique_lines
    FAIL: test_conflicting_changes_emit_markers_and_conflict_block
    FAIL: test_crlf_mix_does_not_swallow_or_attach_cr
    FAIL: test_empty_file_cases
    FAIL: test_empty_to_text_and_text_to_empty
    FAIL: test_insert_at_head_uses_zero_start_for_old_side
    FAIL: test_join_roundtrip
    FAIL: test_malformed_patch_raises
    FAIL: test_no_newline_marker_on_both_sides
    FAIL: test_no_trailing_newline_keeps_marker_and_order
    FAIL: test_pure_insert_and_pure_delete
    FAIL: test_randomized_roundtrip_and_shortest
    FAIL: test_roundtrip_varied_contexts
    FAIL: test_single_line_no_newline

期望的行为其实都写在 README 里了，我们照着 README 用的。麻烦：

1. 把上面这些现象逐条修掉，让 42 条测试全部通过。测试文件请不要改动，那是我们和你们约定的验收依据。
2. 修的过程中请守住这些约束：
   - `apply(a, unified(a, b)) == b`，含 CRLF 混排、无结尾换行、空文件这些边界；
   - 同一输入多次生成的补丁完全一致，与 difflib 在唯一行文本上逐字节一致；
   - 上下文不匹配、行号越界、hunk 计数与正文不符、补丁结构非法一律抛 `PatchError`，带 hunk 序号与期望/实际内容；
   - 近相似大文本仍要在原来的量级完成，首尾公共前后缀归并不要去掉。
3. 每个问题点都补一条回归测试，避免下次又回归；README 里描述不一致的地方也请一并改掉。
4. 需要交付的内容：`textdiff/patch.py`、`textdiff/merge.py`、`textdiff/myers.py`、`test_textdiff.py`、`README.md`。注释、报错信息请保持中文。
