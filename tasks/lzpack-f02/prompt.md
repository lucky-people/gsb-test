PR 评审意见 —— lzpack：逻辑调整（lzpack-f02）

结论：先别合。基线在 `python3 -m unittest test_lzpack -v` 下已经红 15/30 条，逐条写在下面。

1. 哈希链的前驱表下标没按窗口取模，链上取到错位的历史位置
2. 匹配标签里存的长度与格式说明不符，字节级布局对不上

失败的用例：

    ERROR: test_10_config_validation_and_levels
    ERROR: test_2_run_of_same_byte
    FAIL: test_4_repeated_logs_ratio
    FAIL: test_5_compress_not_quadratic
    FAIL: test_6_decompressor_chunked_feeds
    FAIL: test_7_compressor_chunked_equals_oneshot
    FAIL: test_8_random_bytes_roundtrip
    FAIL: test_all_zeros
    FAIL: test_cross_feed_match
    FAIL: test_incompressible_stored_as_literals
    FAIL: test_match_token_bytes
    FAIL: test_max_match_length
    FAIL: test_offset_exactly_window
    FAIL: test_repeat_beyond_window_not_matched
    FAIL: test_window_level_combinations

几点说明：

1. 上面每一条我都在本地单独验过，症状各自独立，改一处不会让另一处跟着好。改动面看着分散在 lzpack/codec.py、lzpack/lz77.py。
2. 修的时候别动 `test_lzpack.py` 里的断言——那份测试是验收基线，写的是这个包对外承诺的行为，红了说明实现错了，不是测试写错了。
3. 下面这些约束请一起保持：
   - `decompress(compress(x)) == x`，一次性与流式（`Compressor` / `Decompressor`）结果逐字节相同；
   - 流的任意一个字节被翻转、在任意长度被截断，都要抛 `FormatError`；
   - 匹配偏移必须落在头部声明的窗口内（允许等于窗口），越窗重复只能退化成字面量；
   - 压缩率与性能不许退化：`bench.py` 三组数据的压缩率不应低于修复前，`test_5_compress_not_quadratic` 要恢复通过。
4. 每条根因都要补回归测试，别只把现有用例弄绿就算完；README 对应段落（语义说明、边界取舍）要跟实现对齐。
5. 交付范围：`lzpack/codec.py`、`lzpack/lz77.py`、`lzpack/varint.py`、`test_lzpack.py`、`README.md`。注释与报错保持中文，公开 API 签名不要改。
