[CI] lzpack 流水线红灯 · job: unittest-test_lzpack · lzpack-g04

step 1/2  checkout ................................ 成功
step 2/2  python3 -m unittest test_lzpack -v ...... 失败（15/30）

日志尾部：

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
    ERROR: test_varint_roundtrip
    ERROR: test_window_level_combinations

构建机结论：本次改动之后基线不再全绿，需要修复后重新触发流水线。

失败分布提示（本地复跑时确认过，症状互不相关）：

- 哈希链的前驱表下标没按窗口取模，链上取到错位的历史位置
- 偏移比匹配长度小的重复片段（连续同一字节、重复日志行）解压后内容错位
- 变长整数的字节上限被改小，长整数编解码不再往返

受影响文件：lzpack/codec.py、lzpack/lz77.py、lzpack/varint.py

解这个 job 的要求：

1. 让 `python3 -m unittest test_lzpack -v` 在干净检出后全绿；不允许改动测试文件，也不允许用跳过（skip）或放宽断言的方式让流水线变绿。
2. 流水线里其它 job 依赖的行为不能退化：
   - `decompress(compress(x)) == x`，一次性与流式（`Compressor` / `Decompressor`）结果逐字节相同；
   - 流的任意一个字节被翻转、在任意长度被截断，都要抛 `FormatError`；
   - 匹配偏移必须落在头部声明的窗口内（允许等于窗口），越窗重复只能退化成字面量；
   - 压缩率与性能不许退化：`bench.py` 三组数据的压缩率不应低于修复前，`test_5_compress_not_quadratic` 要恢复通过。
3. 每处根因补回归测试；README 的相应章节需要同步更新，否则文档 job 下一轮还会红。
4. 改动范围：`lzpack/codec.py`、`lzpack/lz77.py`、`lzpack/varint.py`、`test_lzpack.py`、`README.md`。中文注释与中文报错。
