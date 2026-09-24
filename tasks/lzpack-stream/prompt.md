归档服务那边出了个事故，落你手上排查一下。

我们后端把每天的快照文本压成 `.lzpk` 再进对象存储，压缩/解压都用仓库里这个纯标准库实现的 `lzpack`。今天早上下游反馈：有些档解压出来跟原始文件对不上，还有一部分直接抛 `lzpack.errors.FormatError` 炸在半路。影响面不小，昨天的全量归档得重跑。

先复现一下：

    python3 -m unittest test_lzpack -v

现在 30 条里红 12 条，长这样：

    ERROR: test_2_run_of_same_byte / test_4_repeated_logs_ratio / test_5_compress_not_quadratic
    ERROR: test_6_decompressor_chunked_feeds / test_8_random_bytes_roundtrip / test_all_zeros
    ERROR: test_cross_feed_match / test_incompressible_stored_as_literals / test_max_match_length
    ERROR: test_offset_exactly_window / test_window_level_combinations
    FAIL:  test_match_token_bytes

排查时已经确认几件事，供你参考：空输入、单字节这种完全没有匹配的数据一切正常；一旦出现「偏移比匹配长度还小」的重复片段——`b"a" * 1000`、全 0、重复日志行都算——就开始崩，说明重叠回引的展开算错了。另外流式接口按 1 字节、3 字节这种小块喂进去时校验会失败，而一次性接口反而能过，这两条不是同一个原因。格式层面的字节约定也可能被动过，`codec.py` 顶部那段格式说明是权威，改完请对着它复核。

要求：

1. 找出并修掉三处互相独立的根因，让 30 条测试全绿。不许改测试；不许把校验放宽、删掉或者用「先解出来再补」之类的办法蒙混。
2. 这些不变量必须继续成立：`decompress(compress(x)) == x`；`Compressor` / `Decompressor` 分块喂入的结果与一次性接口逐字节相同；流的任意一个字节被翻转、在任意长度被截断，都必须抛 `FormatError`；匹配偏移不得越过头部声明的窗口。
3. 不能靠牺牲性能换正确性：`test_5_compress_not_quadratic` 与 `bench.py` 的量级要保持，10 MB 日志那组的压缩率不应变差。
4. 每处根因补至少一条回归测试，并在 README 的格式说明里把「重叠回引如何展开」和「流式校验值如何累加」写清楚，别只改代码。

交付：`lzpack/codec.py`（必要时连带 `lzpack/varint.py`、`lzpack/lz77.py`）、`test_lzpack.py`、`README.md`。注释和报错保持中文，公开 API 签名不要动。
