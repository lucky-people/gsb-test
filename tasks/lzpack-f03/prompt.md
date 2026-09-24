您好，反馈一个 lzpack 的问题（工单 lzpack-f03）

我们把这个包接进了生产的处理链路，最近运维那边报了几类异常，麻烦帮忙看下。我们不是专业审代码的，只能把现象描述清楚：

- 变长整数的字节上限被改小，长整数编解码不再往返
- 变长整数的位移步长写错，多字节数值拼回来是错的
- 偏移比匹配长度小的重复片段（连续同一字节、重复日志行）解压后内容错位

我们自己复现的方式就是在仓库根目录跑：

    python3 -m unittest test_lzpack -v

现在 30 条里红 12 条，红的名字如下：

    ERROR: test_2_run_of_same_byte
    FAIL: test_4_repeated_logs_ratio
    FAIL: test_5_compress_not_quadratic
    FAIL: test_6_decompressor_chunked_feeds
    FAIL: test_8_random_bytes_roundtrip
    FAIL: test_all_zeros
    FAIL: test_cross_feed_match
    FAIL: test_incompressible_stored_as_literals
    FAIL: test_max_match_length
    FAIL: test_offset_exactly_window
    ERROR: test_varint_roundtrip
    FAIL: test_window_level_combinations

期望的行为其实都写在 README 里了，我们照着 README 用的。麻烦：

1. 把上面这些现象逐条修掉，让 30 条测试全部通过。测试文件请不要改动，那是我们和你们约定的验收依据。
2. 修的过程中请守住这些约束：
   - `decompress(compress(x)) == x`，一次性与流式（`Compressor` / `Decompressor`）结果逐字节相同；
   - 流的任意一个字节被翻转、在任意长度被截断，都要抛 `FormatError`；
   - 匹配偏移必须落在头部声明的窗口内（允许等于窗口），越窗重复只能退化成字面量；
   - 压缩率与性能不许退化：`bench.py` 三组数据的压缩率不应低于修复前，`test_5_compress_not_quadratic` 要恢复通过。
3. 每个问题点都补一条回归测试，避免下次又回归；README 里描述不一致的地方也请一并改掉。
4. 需要交付的内容：`lzpack/codec.py`、`lzpack/lz77.py`、`lzpack/varint.py`、`test_lzpack.py`、`README.md`。注释、报错信息请保持中文。
