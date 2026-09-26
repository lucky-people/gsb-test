# 事故复盘：textdiff 相关链路异常（textdiff-g04）

事故简述：下游今天反馈，textdiff 在处理真实输入时结果不对，一部分直接抛异常炸在半路。我们内部先按最小复现跑了一遍，确认不是环境问题。

这个包是文本差异与三方合并引擎（Myers 最短编辑脚本 + unified diff 生成与套用 + diff3 风格合并），目前的问题集中在它的核心逻辑上。

初判的影响面，按严重程度排：

- 没有行终止符的最后一行丢了「未结束」标注，往返时差一个结尾
- 单独的 CR（经典 Mac 行尾）不再算行终止符，切成了一整行
- 旧侧计数为 0 的 hunk 定位方式被统一成减一，插入点整体前移

复现命令（仓库根目录）：

    python3 -m unittest test_textdiff -v

现在 42 条里红 8 条：

    FAIL: test_byte_identical_with_difflib_on_unique_lines
    FAIL: test_crlf_mix_does_not_swallow_or_attach_cr
    ERROR: test_empty_file_cases
    ERROR: test_empty_to_text_and_text_to_empty
    FAIL: test_no_newline_marker_on_both_sides
    FAIL: test_no_trailing_newline_keeps_marker_and_order
    FAIL: test_randomized_roundtrip_and_shortest
    ERROR: test_roundtrip_varied_contexts

我看下来这不像一处原因，至少分布在 textdiff/myers.py、textdiff/patch.py 这几个文件里，修一处另一处仍会红。请你：

1. 定位并修掉全部根因，让 42 条测试全绿。不许改测试、删断言，也不许把校验放宽或注释掉来「让它过」。
2. 这些不变量必须继续成立：
   - `apply(a, unified(a, b)) == b`，含 CRLF 混排、无结尾换行、空文件这些边界；
   - 同一输入多次生成的补丁完全一致，与 difflib 在唯一行文本上逐字节一致；
   - 上下文不匹配、行号越界、hunk 计数与正文不符、补丁结构非法一律抛 `PatchError`，带 hunk 序号与期望/实际内容；
   - 近相似大文本仍要在原来的量级完成，首尾公共前后缀归并不要去掉。
3. 每处根因补至少一条回归测试；README 里与本次改动相关的小节要同步改到与实现一致。
4. 修完请用同一条命令复跑确认，并在 README 里写明本次修复涉及哪几条语义。

交付：`textdiff/patch.py`、`textdiff/merge.py`、`textdiff/myers.py`、`test_textdiff.py`、`README.md`。注释与报错信息保持中文，公开 API 与已有行为不要动。
