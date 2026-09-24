# 回归批次 lzpack-f08：lzpack 用例执行报告

被测对象：lzpack（纯 Python 标准库实现的 LZ77 压缩库（流格式：魔数 + 版本 + 变长原始长度 + 头部校验 + CRC32 + token 序列））
执行方式：仓库根目录 `python3 -m unittest test_lzpack -v`
结果：17/30 失败，判定为**不通过**。

## 失败用例明细

| # | 类型 | 用例 |
|---|---|---|
| 1 | ERROR | test_2_run_of_same_byte |
| 2 | FAIL | test_3_incompressible_tiny |
| 3 | FAIL | test_4_repeated_logs_ratio |
| 4 | FAIL | test_5_compress_not_quadratic |
| 5 | FAIL | test_6_decompressor_chunked_feeds |
| 6 | FAIL | test_8_random_bytes_roundtrip |
| 7 | FAIL | test_all_zeros |
| 8 | FAIL | test_cross_feed_match |
| 9 | FAIL | test_finish_twice_returns_empty |
| 10 | FAIL | test_header_layout |
| 11 | FAIL | test_incompressible_stored_as_literals |
| 12 | FAIL | test_match_token_bytes |
| 13 | FAIL | test_max_match_length |
| 14 | FAIL | test_offset_exactly_window |
| 15 | FAIL | test_single_byte |
| 16 | ERROR | test_varint_roundtrip |
| 17 | FAIL | test_window_level_combinations |

## 缺陷归类

| 编号 | 缺陷描述 |
|---|---|
| 1 | 字面量块的长度标签差一，解码时整块多吃一个字节 |
| 2 | 变长整数的字节上限被改小，长整数编解码不再往返 |
| 3 | 字面量块的块长换算多算了一个字节 |
| 4 | 变长整数的位移步长写错，多字节数值拼回来是错的 |

归类依据：同一类缺陷在多条用例上重复出现，且分布在不同模块（lzpack/codec.py、lzpack/varint.py），因此判定为多处独立根因，而不是单一 bug 的连带影响。

## 修复要求

1. 让 30 条用例全部通过；测试文件为本批次的判定依据，禁止修改。
2. 修复后需满足下列行为约定：
   - `decompress(compress(x)) == x`，一次性与流式（`Compressor` / `Decompressor`）结果逐字节相同；
   - 流的任意一个字节被翻转、在任意长度被截断，都要抛 `FormatError`；
   - 匹配偏移必须落在头部声明的窗口内（允许等于窗口），越窗重复只能退化成字面量；
   - 压缩率与性能不许退化：`bench.py` 三组数据的压缩率不应低于修复前，`test_5_compress_not_quadratic` 要恢复通过。
3. 每一类缺陷补充对应回归用例，并保证新用例同样稳定通过。
4. 交付物：`lzpack/codec.py`、`lzpack/lz77.py`、`lzpack/varint.py`、`test_lzpack.py`、`README.md`；注释与报错信息使用中文，公开 API 不得变更。
