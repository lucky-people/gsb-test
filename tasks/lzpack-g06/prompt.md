迁移验收单：把批处理链路从旧实现切到 lzpack（lzpack-g06）

我们准备用 lzpack（纯 Python 标准库实现的 LZ77 压缩库（流格式：魔数 + 版本 + 变长原始长度 + 头部校验 + CRC32 + token 序列））替换现在的旧实现。灰度阶段按老实现的结果做对照，验收用例跑出 12/30 条不一致，切换因此卡在这里。

对照中暴露的差异：

- 分块喂入时校验值没有按块累加，一次性接口却能过
- 头部元数据里 1 MB 窗口被当成非法值拒掉
- 哈希链的前驱表下标没按窗口取模，链上取到错位的历史位置

验收命令（仓库根目录）：

    python3 -m unittest test_lzpack -v

不一致的用例：

    ERROR: test_10_config_validation_and_levels
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

判断：差异跨了 lzpack/codec.py、lzpack/lz77.py，不是一处适配问题，需要逐个对齐语义后重新验收。

切换前必须满足：

1. 30 条验收用例全部通过，测试文件作为对照基准不得修改。
2. 切换后这些既有承诺不能被破坏（旧实现里也是这么做的）：
   - `decompress(compress(x)) == x`，一次性与流式（`Compressor` / `Decompressor`）结果逐字节相同；
   - 流的任意一个字节被翻转、在任意长度被截断，都要抛 `FormatError`；
   - 匹配偏移必须落在头部声明的窗口内（允许等于窗口），越窗重复只能退化成字面量；
   - 压缩率与性能不许退化：`bench.py` 三组数据的压缩率不应低于修复前，`test_5_compress_not_quadratic` 要恢复通过。
3. 每处差异补一条回归用例，把「为什么这么判定」写进 README，避免下次切换再对不上。
4. 交付：`lzpack/codec.py`、`lzpack/lz77.py`、`lzpack/varint.py`、`test_lzpack.py`、`README.md`；注释与报错保持中文，对外接口签名不变。
