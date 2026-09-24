我下午请假，textdiff 这摊先交给你，抱歉扔得急。

情况是这样：我们内部有个「把两个版本的文本合成 patch 再套回去」的小工具，底层就是这个仓库里的 `textdiff`。昨天做压测定点排查时发现生成的 unified diff 有几处跟 GNU diff / difflib 对不齐，套回原文也会出错。我没来得及定位到底有几处原因，你跑一下就知道了：

    python3 -m unittest test_textdiff -v

现在 42 条里红 13 条，大致分三类：

    ERROR: test_roundtrip_varied_contexts / test_empty_to_text_and_text_to_empty / test_randomized_roundtrip_and_shortest
    FAIL:  test_insert_at_head_uses_zero_start_for_old_side / test_delete_to_empty_old_side / test_empty_file_cases
    FAIL:  test_no_newline_marker_on_both_sides / test_no_trailing_newline_keeps_marker_and_order
    FAIL:  test_byte_identical_with_difflib_on_unique_lines / test_pure_insert_and_pure_delete
    FAIL:  test_change_blocks_keep_document_order / test_crlf_lines_render_delete_before_insert
    FAIL:  test_replace_block_renders_all_deletes_before_inserts

我能确定的两条线索：一是「空区间」的行号，unified 头里某一侧一行都没有时，那一侧的起始行号有它自己的写法，现在疑似多加了 1，所以在文件开头插入、或把文件删空这两种情形下头是错的，套用时按行号定位就跑到别处去了。二是没有行终止符的最后一行，漏了那个 `\ No newline at end of file` 标注之后，`apply` 解析回来的内容跟原文差一个结尾，往返就不成立了。

第三条线索弱一些：头部里区间长度为 1 时，unified 的写法是省略计数（`-3` 而不是 `-3,1`）。现在这一类也被带上了计数，于是跟 difflib 逐字节对比过不去，第三方工具按规范解析也容易出岔子。这三条我怀疑都是各自独立的原因，别只改一处就交差。

要求：

1. 三处根因都修掉，42 条测试全绿。测试文件是验收基线，一条都不许改。
2. 这些不变量要保住：`apply(a, unified(a, b)) == b`（含 CRLF 混排、无结尾换行、空文件与全空输入）；同一个输入多次生成的结果完全一致；编辑块的渲染顺序是「同一个替换块内先全部删除、再全部插入，不同块之间按文档顺序」；与 difflib 在唯一行文本上逐字节一致。
3. 错误处理不能放宽：上下文不匹配、行号越界、hunk 头声明的计数与正文不符、补丁结构非法，都必须抛 `PatchError`，带 hunk 序号与出问题那行的期望/实际内容，绝不静默猜测。
4. 性能不退化：`bench.py` 里「10 万行、几十处改动」的近相似文本仍要在原来的量级完成，首尾公共前后缀归并不要去掉。
5. 三处根因各补一条回归测试，README 里补一节说明「unified 头部行号的两种写法」和「无结尾换行的标注规则」。

交付：`textdiff/patch.py`（必要时连带 `textdiff/myers.py`）、`test_textdiff.py`、`README.md`。注释与报错保持中文，`unified` / `apply` / `merge` 的签名不要动。
