【CI 失败】lzpack：解压大面积崩 + 窗口不变量被破坏

仓库里的 lzpack（纯 Python 标准库实现的 LZ77 压缩库）现在是红的，30 条测试里挂了 12 条，分成两组症状：

第一组（11 条 ERROR，解压阶段炸）：

    lzpack.errors.FormatError: 偏移 342: CRC32 校验失败：期望 3B05C147，实际 60F70435
    ERROR: test_2_run_of_same_byte
    ERROR: test_4_repeated_logs_ratio
    ERROR: test_5_compress_not_quadratic
    ERROR: test_6_decompressor_chunked_feeds
    ERROR: test_8_random_bytes_roundtrip
    ERROR: test_all_zeros
    ERROR: test_cross_feed_match
    ERROR: test_incompressible_stored_as_literals
    ERROR: test_max_match_length
    ERROR: test_offset_exactly_window
    ERROR: test_window_level_combinations

第二组（1 条 FAIL，窗口语义被破坏）：

    FAIL: test_repeat_beyond_window_not_matched
    AssertionError: 2200 not less than or equal to 1024

复现：

    python3 -m unittest test_lzpack -v

规律提示：空输入、单字节这类完全没有匹配的数据能过；出现长度 ≥ 3 的重复片段就开始崩。第二组说明「超出窗口的历史不能拿来做匹配」这条约束被破坏了——注意它和第一组是两处独立的原因，修好一处另一处仍会红。

你要做的：

1. 定位并修掉**两处**根因，让 30 条测试全绿。
2. 不许改测试；不许关掉或放宽 CRC、长度、偏移、窗口这些完整性校验来「让它过」。
3. 这些不变量必须保持：`decompress(compress(x)) == x`；一次性与流式（`Compressor`/`Decompressor`）结果逐字节相同；匹配偏移必须落在头里声明的窗口范围内（允许等于窗口，超大窗口边界用 `window=32768` 的现成用例验证）；越窗重复只能退化成字面量；截断或损坏的流仍然抛 `FormatError`。
4. 修复后确认压缩率没有变差：README 里 1 MB 随机 / 1 MB 重复 / 10 MB 日志三组数据的压缩率不应低于修复前。
5. 针对两处根因各补一条回归测试，并在 README 的格式说明里把「偏移字段的取值约定」和「窗口上限如何约束匹配搜索」写清楚。

提示：`lzpack/codec.py` 顶部注释精确描述了两个字段的语义（匹配标签后面那个字段存的是什么、元数据里的窗口位数怎么解释）；`lzpack/lz77.py` 里决定搜索范围的边界条件也要和头部声明的窗口对齐。
