# 事故复盘：lzpack 相关链路异常（lzpack-f01）

事故简述：下游今天反馈，lzpack 在处理真实输入时结果不对，一部分直接抛异常炸在半路。我们内部先按最小复现跑了一遍，确认不是环境问题。

这个包是纯 Python 标准库实现的 LZ77 压缩库（流格式：魔数 + 版本 + 变长原始长度 + 头部校验 + CRC32 + token 序列），目前的问题集中在它的核心逻辑上。

初判的影响面，按严重程度排：

- 偏移比匹配长度小的重复片段（连续同一字节、重复日志行）解压后内容错位
- 变长整数的字节上限被改小，长整数编解码不再往返

复现命令（仓库根目录）：

    python3 -m unittest test_lzpack -v

现在 30 条里红 9 条：

    ERROR: test_2_run_of_same_byte
    FAIL: test_4_repeated_logs_ratio
    FAIL: test_5_compress_not_quadratic
    FAIL: test_6_decompressor_chunked_feeds
    FAIL: test_all_zeros
    FAIL: test_cross_feed_match
    FAIL: test_max_match_length
    ERROR: test_varint_roundtrip
    FAIL: test_window_level_combinations

我看下来这不像一处原因，至少分布在 lzpack/codec.py、lzpack/varint.py 这几个文件里，修一处另一处仍会红。请你：

1. 定位并修掉全部根因，让 30 条测试全绿。不许改测试、删断言，也不许把校验放宽或注释掉来「让它过」。
2. 这些不变量必须继续成立：
   - `decompress(compress(x)) == x`，一次性与流式（`Compressor` / `Decompressor`）结果逐字节相同；
   - 流的任意一个字节被翻转、在任意长度被截断，都要抛 `FormatError`；
   - 匹配偏移必须落在头部声明的窗口内（允许等于窗口），越窗重复只能退化成字面量；
   - 压缩率与性能不许退化：`bench.py` 三组数据的压缩率不应低于修复前，`test_5_compress_not_quadratic` 要恢复通过。
3. 每处根因补至少一条回归测试；README 里与本次改动相关的小节要同步改到与实现一致。
4. 修完请用同一条命令复跑确认，并在 README 里写明本次修复涉及哪几条语义。

交付：`lzpack/codec.py`、`lzpack/lz77.py`、`lzpack/varint.py`、`test_lzpack.py`、`README.md`。注释与报错信息保持中文，公开 API 与已有行为不要动。
