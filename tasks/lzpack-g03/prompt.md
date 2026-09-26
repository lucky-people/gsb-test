先跟你同步一下 lzpack 这摊事（lzpack-g03），我这边要交出去了。

情况是：lzpack 是纯 Python 标准库实现的 LZ77 压缩库（流格式：魔数 + 版本 + 变长原始长度 + 头部校验 + CRC32 + token 序列）。最近在真实输入上出了问题，我查了一半没查完，跑测试是红的：

    python3 -m unittest test_lzpack -v

17/30 条失败：

    ERROR: test_2_run_of_same_byte
    ERROR: test_3_incompressible_tiny
    ERROR: test_4_repeated_logs_ratio
    ERROR: test_5_compress_not_quadratic
    ERROR: test_6_decompressor_chunked_feeds
    ERROR: test_8_random_bytes_roundtrip
    ERROR: test_all_zeros
    ERROR: test_cross_feed_match
    ERROR: test_finish_twice_returns_empty
    FAIL: test_header_layout
    ERROR: test_incompressible_stored_as_literals
    FAIL: test_match_token_bytes
    ERROR: test_max_match_length
    ERROR: test_offset_exactly_window
    ERROR: test_single_byte
    FAIL: test_varint_roundtrip
    ERROR: test_window_level_combinations

我没查完的点，按我的笔记抄给你：

- 变长整数的字节上限被改小，长整数编解码不再往返
- 变长整数的位移步长写错，多字节数值拼回来是错的
- 字面量块的长度标签差一，解码时整块多吃一个字节

我已经排除的因素：跟环境、依赖没关系，纯标准库，装上就能跑；也不是测试写错。我怀疑是好几个地方一起坏了，lzpack/codec.py、lzpack/varint.py 都得看。

拜托你做到：

1. 30 条测试全绿，别去改测试文件里的断言。
2. 这些约束别弄丢：
   - `decompress(compress(x)) == x`，一次性与流式（`Compressor` / `Decompressor`）结果逐字节相同；
   - 流的任意一个字节被翻转、在任意长度被截断，都要抛 `FormatError`；
   - 匹配偏移必须落在头部声明的窗口内（允许等于窗口），越窗重复只能退化成字面量；
   - 压缩率与性能不许退化：`bench.py` 三组数据的压缩率不应低于修复前，`test_5_compress_not_quadratic` 要恢复通过。
3. 每一处根因补一条回归测试，顺手把 README 里说得含糊或者跟实现不一致的地方改掉。
4. 交付：`lzpack/codec.py`、`lzpack/lz77.py`、`lzpack/varint.py`、`test_lzpack.py`、`README.md`，注释和报错保持中文。

辛苦了。
