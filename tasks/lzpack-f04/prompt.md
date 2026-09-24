# 需求单：对齐 lzpack 的对外语义（lzpack-f04）

背景：我们把 lzpack 当成基础设施接进了业务链路（纯 Python 标准库实现的 LZ77 压缩库（流格式：魔数 + 版本 + 变长原始长度 + 头部校验 + CRC32 + token 序列））。接入测试发现它的实现与我们按 README 理解的语义不一致，先把不一致的地方列出来。

## 现象清单

| 编号 | 现象 |
|---|---|
| 1 | 哈希链的前驱表下标没按窗口取模，链上取到错位的历史位置 |
| 2 | 字面量块的块长换算多算了一个字节 |
| 3 | 变长整数的字节上限被改小，长整数编解码不再往返 |

## 复现与失败用例

    python3 -m unittest test_lzpack -v

当前 18/30 条失败：

    ERROR: test_10_config_validation_and_levels
    ERROR: test_2_run_of_same_byte
    FAIL: test_3_incompressible_tiny
    FAIL: test_4_repeated_logs_ratio
    FAIL: test_5_compress_not_quadratic
    FAIL: test_6_decompressor_chunked_feeds
    FAIL: test_7_compressor_chunked_equals_oneshot
    FAIL: test_8_random_bytes_roundtrip
    FAIL: test_all_zeros
    FAIL: test_cross_feed_match
    FAIL: test_finish_twice_returns_empty
    FAIL: test_incompressible_stored_as_literals
    FAIL: test_max_match_length
    FAIL: test_offset_exactly_window
    FAIL: test_repeat_beyond_window_not_matched
    FAIL: test_single_byte
    ERROR: test_varint_roundtrip
    FAIL: test_window_level_combinations

## 验收要求

1. 以上现象全部消除，30 条测试全绿；测试文件是验收基线，不允许修改或删除断言。
2. 实现必须满足下列硬性约束：
   - `decompress(compress(x)) == x`，一次性与流式（`Compressor` / `Decompressor`）结果逐字节相同；
   - 流的任意一个字节被翻转、在任意长度被截断，都要抛 `FormatError`；
   - 匹配偏移必须落在头部声明的窗口内（允许等于窗口），越窗重复只能退化成字面量；
   - 压缩率与性能不许退化：`bench.py` 三组数据的压缩率不应低于修复前，`test_5_compress_not_quadratic` 要恢复通过。
3. 每条现象对应一处独立根因（预计分布在 lzpack/codec.py、lzpack/lz77.py、lzpack/varint.py），请逐一定位；只改一处会有用例继续红。
4. 为每处根因补回归测试；README 里与本需求相关的语义说明要与实现一致。
5. 交付物：`lzpack/codec.py`、`lzpack/lz77.py`、`lzpack/varint.py`、`test_lzpack.py`、`README.md`。注释与报错信息使用中文，不得修改公开 API。
