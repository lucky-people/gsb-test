先跟你同步一下 textdiff 这摊事（textdiff-f01），我这边要交出去了。

情况是：textdiff 是文本差异与三方合并引擎（Myers 最短编辑脚本 + unified diff 生成与套用 + diff3 风格合并）。最近在真实输入上出了问题，我查了一半没查完，跑测试是红的：

    python3 -m unittest test_textdiff -v

8/42 条失败：

    FAIL: test_byte_identical_with_difflib_on_unique_lines
    FAIL: test_crlf_mix_does_not_swallow_or_attach_cr
    FAIL: test_join_roundtrip
    FAIL: test_malformed_patch_raises
    FAIL: test_no_newline_marker_on_both_sides
    FAIL: test_no_trailing_newline_keeps_marker_and_order
    FAIL: test_roundtrip_varied_contexts
    FAIL: test_single_line_no_newline

我没查完的点，按我的笔记抄给你：

- 结尾没有行终止符的那一行被整行丢掉，往返时凭空少一行
- hunk 分组的间隔阈值差一，间隔刚好的两处改动被错误合并

我已经排除的因素：跟环境、依赖没关系，纯标准库，装上就能跑；也不是测试写错。我怀疑是好几个地方一起坏了，textdiff/myers.py、textdiff/patch.py 都得看。

拜托你做到：

1. 42 条测试全绿，别去改测试文件里的断言。
2. 这些约束别弄丢：
   - `apply(a, unified(a, b)) == b`，含 CRLF 混排、无结尾换行、空文件这些边界；
   - 同一输入多次生成的补丁完全一致，与 difflib 在唯一行文本上逐字节一致；
   - 上下文不匹配、行号越界、hunk 计数与正文不符、补丁结构非法一律抛 `PatchError`，带 hunk 序号与期望/实际内容；
   - 近相似大文本仍要在原来的量级完成，首尾公共前后缀归并不要去掉。
3. 每一处根因补一条回归测试，顺手把 README 里说得含糊或者跟实现不一致的地方改掉。
4. 交付：`textdiff/patch.py`、`textdiff/merge.py`、`textdiff/myers.py`、`test_textdiff.py`、`README.md`，注释和报错保持中文。

辛苦了。
