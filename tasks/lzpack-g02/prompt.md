对账对不上，想请你帮忙定位一下 lzpack（lzpack-g02）

我们把 lzpack（纯 Python 标准库实现的 LZ77 压缩库（流格式：魔数 + 版本 + 变长原始长度 + 头部校验 + CRC32 + token 序列））接进了批处理流程，上线前拿一批样本跟参考实现逐条比。抽了三轮，结论不一致的比例明显超出预期，人工核对之后归成下面几类：

- window 必须是 2 的幂这条校验没了，非 2 的幂参数被静默接受
- 哈希链的前驱表下标没按窗口取模，链上取到错位的历史位置

在仓库根目录可以直接复现：

    python3 -m unittest test_lzpack -v

现在是 12/30 条红：

    FAIL: test_10_config_validation_and_levels
    ERROR: test_4_repeated_logs_ratio
    ERROR: test_5_compress_not_quadratic
    ERROR: test_6_decompressor_chunked_feeds
    ERROR: test_7_compressor_chunked_equals_oneshot
    ERROR: test_8_random_bytes_roundtrip
    ERROR: test_all_zeros
    ERROR: test_incompressible_stored_as_literals
    ERROR: test_max_match_length
    ERROR: test_offset_exactly_window
    ERROR: test_repeat_beyond_window_not_matched
    ERROR: test_window_level_combinations

我的判断是这几类来自不同地方——lzpack/codec.py、lzpack/lz77.py 里都有嫌疑，请分别定位。要求：

1. 30 条测试全部恢复通过。测试文件不动。
2. 修复过程中这些约束不能破：
   - `decompress(compress(x)) == x`，一次性与流式（`Compressor` / `Decompressor`）结果逐字节相同；
   - 流的任意一个字节被翻转、在任意长度被截断，都要抛 `FormatError`；
   - 匹配偏移必须落在头部声明的窗口内（允许等于窗口），越窗重复只能退化成字面量；
   - 压缩率与性能不许退化：`bench.py` 三组数据的压缩率不应低于修复前，`test_5_compress_not_quadratic` 要恢复通过。
3. 每类问题补一条针对性的回归测试（最好能直接复现对账时的那种输入），并在 README 里把判定口径写清楚。
4. 交付：`lzpack/codec.py`、`lzpack/lz77.py`、`lzpack/varint.py`、`test_lzpack.py`、`README.md`。中文注释与中文报错，公开 API 不变。
