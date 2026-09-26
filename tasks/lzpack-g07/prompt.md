“lzpack 这个包你帮我看下，我这边结果不对。”

“什么现象？”

“我列了几个，都是真跑出来的：

- 偏移比匹配长度小的重复片段（连续同一字节、重复日志行）解压后内容错位
- 变长整数的位移步长写错，多字节数值拼回来是错的
- 哈希链的前驱表下标没按窗口取模，链上取到错位的历史位置
- 头部元数据里 1 MB 窗口被当成非法值拒掉

”

“先跑一遍测试确认下？”

“跑了，仓库根目录 `python3 -m unittest test_lzpack -v`，15/30 条红：

    ERROR: test_10_config_validation_and_levels
    ERROR: test_2_run_of_same_byte
    ERROR: test_4_repeated_logs_ratio
    ERROR: test_5_compress_not_quadratic
    ERROR: test_6_decompressor_chunked_feeds
    ERROR: test_7_compressor_chunked_equals_oneshot
    ERROR: test_8_random_bytes_roundtrip
    ERROR: test_all_zeros
    ERROR: test_cross_feed_match
    ERROR: test_incompressible_stored_as_literals
    ERROR: test_max_match_length
    ERROR: test_offset_exactly_window
    ERROR: test_repeat_beyond_window_not_matched
    FAIL: test_varint_roundtrip
    ERROR: test_window_level_combinations

”

“看着不像一处问题。”

“我也这么觉得，lzpack/codec.py、lzpack/lz77.py、lzpack/varint.py 我都翻过，几个地方都可疑。麻烦你排一下，要求是：

1. 30 条测试全部弄绿，别改测试文件——那是验收基线；
2. 这些行为不能变：
   - `decompress(compress(x)) == x`，一次性与流式（`Compressor` / `Decompressor`）结果逐字节相同；
   - 流的任意一个字节被翻转、在任意长度被截断，都要抛 `FormatError`；
   - 匹配偏移必须落在头部声明的窗口内（允许等于窗口），越窗重复只能退化成字面量；
   - 压缩率与性能不许退化：`bench.py` 三组数据的压缩率不应低于修复前，`test_5_compress_not_quadratic` 要恢复通过。
3. 每处根因补一条回归测试，README 里说不清楚的地方一起补；
4. 交付 `lzpack/codec.py`、`lzpack/lz77.py`、`lzpack/varint.py`、`test_lzpack.py`、`README.md`，注释和报错用中文。”
