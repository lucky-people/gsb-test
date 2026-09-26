"""lzpack 的完整测试：10 条验收基线 + 全部边界情况。"""

import random
import time
import unittest

import lzpack
from lzpack import codec
from lzpack.errors import ConfigError, FormatError
from lzpack.lz77 import MAX_MATCH, MIN_MATCH, find_tokens
from lzpack.varint import MAX_VARINT_BYTES, encode_varint, read_varint

LOG_LINE = b"2026-09-24 12:00:00 INFO  [worker-3] request handled in 12ms\n"


def shuffled_feed(decompressor, blob, size):
    """按固定块长把 blob 喂给 Decompressor，返回拼起来的输出。"""
    out = []
    for i in range(0, len(blob), size):
        out.append(decompressor.feed(blob[i:i + size]))
    out.append(decompressor.finish())
    return b"".join(out)


class TestAcceptance(unittest.TestCase):
    """验收基线 1~10。"""

    def test_1_empty_stream(self):
        blob = lzpack.compress(b"")
        self.assertIsInstance(blob, bytes)
        self.assertTrue(blob.startswith(codec.MAGIC))
        self.assertEqual(lzpack.decompress(blob), b"")

    def test_2_run_of_same_byte(self):
        data = b"a" * 1000
        blob = lzpack.compress(data)
        self.assertLess(len(blob), 40)
        self.assertEqual(lzpack.decompress(blob), data)

    def test_3_incompressible_tiny(self):
        data = b"abcdefgh"
        blob = lzpack.compress(data)
        self.assertLessEqual(len(blob), len(data) + 16)
        self.assertEqual(lzpack.decompress(blob), data)

    def test_4_repeated_logs_ratio(self):
        data = LOG_LINE * 1000
        blob = lzpack.compress(data)
        self.assertLess(len(blob), len(data) * 0.03)
        self.assertEqual(lzpack.decompress(blob), data)

    def test_5_compress_not_quadratic(self):
        data = LOG_LINE * (10 * 1024 * 1024 // len(LOG_LINE))
        t0 = time.perf_counter()
        blob = lzpack.compress(data)
        t_compress = time.perf_counter() - t0
        d = lzpack.Decompressor()
        t0 = time.perf_counter()
        out = d.feed(blob) + d.finish()
        t_decompress = time.perf_counter() - t0
        self.assertEqual(out, data)
        self.assertLessEqual(t_compress, t_decompress * 20)

    def test_6_decompressor_chunked_feeds(self):
        data = (LOG_LINE * 500) + bytes(range(256)) * 100
        blob = lzpack.compress(data)
        expect = lzpack.decompress(blob)
        for size in (1, 3, 4096):
            got = shuffled_feed(lzpack.Decompressor(), blob, size)
            self.assertEqual(got, expect)

    def test_7_compressor_chunked_equals_oneshot(self):
        data = (LOG_LINE * 300) + b"\x00" * 5000 + LOG_LINE * 300
        expect = lzpack.compress(data)
        for size in (1, 3, 4096):
            c = lzpack.Compressor()
            parts = [c.feed(data[i:i + size]) for i in range(0, len(data), size)]
            parts.append(c.finish())
            self.assertEqual(b"".join(parts), expect)

    def test_8_random_bytes_roundtrip(self):
        data = random.Random(1234).randbytes(1 << 20)
        blob = lzpack.compress(data)
        self.assertEqual(lzpack.decompress(blob), data)
        self.assertLessEqual(len(blob), len(data) * 1.02)

    def test_9_corruption_and_truncation(self):
        data = b"hello world, hello lzpack, hello world!" * 3
        blob = lzpack.compress(data)
        # 任意一个字节被改动（每个位置试 3 种翻转）
        for i in range(len(blob)):
            for bit in (0x01, 0x80, 0xFF):
                mutated = bytearray(blob)
                mutated[i] ^= bit
                with self.assertRaises(FormatError, msg="offset %d" % i):
                    lzpack.decompress(bytes(mutated))
        # 头 4 字节不是魔数
        with self.assertRaises(FormatError):
            lzpack.decompress(b"XXXX" + blob[4:])
        # 任意截断
        for k in range(len(blob)):
            with self.assertRaises(FormatError, msg="truncate at %d" % k):
                lzpack.decompress(blob[:k])
        # FormatError 带 offset 与中文说明
        try:
            lzpack.decompress(b"XXXX")
        except FormatError as e:
            self.assertEqual(e.offset, 0)
            self.assertTrue(e.args[0])

    def test_10_config_validation_and_levels(self):
        for bad in (0, 10, -1, 100):
            with self.assertRaises(ConfigError):
                lzpack.compress(b"x", level=bad)
            with self.assertRaises(ConfigError):
                lzpack.Compressor(level=bad)
        for bad in (0, 512, 1023, 1025, 1536, 3 << 10, 2 << 20, 10 << 20):
            with self.assertRaises(ConfigError):
                lzpack.compress(b"x", window=bad)
        for good in (1 << 10, 1 << 15, 1 << 20):
            lzpack.compress(b"x", window=good)
        # level 越高压缩率不劣于低 level
        data = (LOG_LINE * 200) + (b"abcabcabd" * 3000) + (LOG_LINE * 200)
        sizes = [len(lzpack.compress(data, level=lv)) for lv in range(1, 10)]
        for lv in range(1, 9):
            self.assertLessEqual(sizes[lv], sizes[lv - 1],
                                 "level %d 比 level %d 差" % (lv + 1, lv))


class TestFormatBytes(unittest.TestCase):
    """字节级的流格式测试。"""

    def test_header_layout(self):
        data = b"aaa"
        blob = lzpack.compress(data)  # 默认 level=6, window=32768
        self.assertEqual(blob[0:4], b"LZPK")                 # 魔数
        self.assertEqual(blob[4], 1)                         # 版本
        self.assertEqual(blob[5], ((15 - 10) << 4) | 6)      # 元数据
        self.assertEqual(blob[6], 3)                         # 原始长度 varint
        self.assertEqual(blob[7], codec.crc32(blob[4:7]) & 0xFF)  # 头部校验
        self.assertEqual(int.from_bytes(blob[8:12], "little"),
                         codec.crc32(data))                  # 数据 CRC32
        # 数据块：一个长度为 3 的字面量块
        self.assertEqual(blob[12:], b"\x02aaa")

    def test_match_token_bytes(self):
        blob = lzpack.compress(b"aaaa", level=1, window=1024)
        self.assertEqual(blob[5], 1)  # meta: log2(1024)-10=0, level=1
        # 字面量 'a' + 匹配(偏移1, 长度3)：00 61 80 00
        self.assertEqual(blob[12:], b"\x00a\x80\x00")

    def test_varint_roundtrip(self):
        for v in (0, 1, 127, 128, 300, 16384, 1 << 20, 1 << 40):
            enc = encode_varint(v)
            self.assertEqual(read_varint(enc, 0), (v, len(enc)))
        self.assertEqual(encode_varint(0), b"\x00")
        self.assertEqual(encode_varint(128), b"\x80\x01")

    def test_varint_incomplete_and_overlong(self):
        self.assertIsNone(read_varint(b"\x80", 0))  # 数据不全
        with self.assertRaises(FormatError):
            read_varint(b"\xff" * 9, 0)             # 超过 9 字节


class TestEdgeCases(unittest.TestCase):
    """边界与取舍。"""

    def test_single_byte(self):
        for b in (b"\x00", b"\xff", b"a"):
            self.assertEqual(lzpack.decompress(lzpack.compress(b)), b)

    def test_all_zeros(self):
        data = b"\x00" * 100000
        blob = lzpack.compress(data)
        self.assertLess(len(blob), 200)
        self.assertEqual(lzpack.decompress(blob), data)

    def test_max_match_length(self):
        # 超过 MAX_MATCH 的重复应拆成多个匹配，且每个匹配长度 <= MAX_MATCH
        data = b"q" + b"z" * (MAX_MATCH * 3 + 100)
        tokens = list(find_tokens(data, 6, 32768))
        matches = [t for t in tokens if t[0] == "m"]
        self.assertTrue(matches)
        for _, off, length in matches:
            self.assertLessEqual(length, MAX_MATCH)
        self.assertEqual(lzpack.decompress(lzpack.compress(data)), data)

    def test_offset_within_window(self):
        rng = random.Random(7)
        data = bytes(rng.choices(range(256), k=200)) * 50
        for window in (1024, 32768):
            for token in find_tokens(data, 6, window):
                if token[0] == "m":
                    self.assertLessEqual(token[1], window)
                    self.assertGreaterEqual(token[1], 1)

    def test_offset_exactly_window(self):
        # 构造一个距离正好 32768 的重复，window=32768 时必须能匹配
        rng = random.Random(11)
        block = bytes(rng.choices(range(256), k=200))
        filler = bytes(rng.choices(range(256), k=32768 - 200))
        data = block + filler + block
        blob = lzpack.compress(data, window=32768)
        self.assertEqual(lzpack.decompress(blob), data)
        # 第二个 block 被编码为偏移正好 32768 的匹配
        pos = 0
        found = False
        for token in find_tokens(data, 6, 32768):
            if token[0] == "l":
                pos += len(token[1])
            else:
                if pos == 32768:
                    self.assertEqual(token[1:], (32768, 200))
                    found = True
                pos += token[2]
        self.assertTrue(found, "距离正好等于 window 的重复没有被匹配")

    def test_repeat_beyond_window_not_matched(self):
        rng = random.Random(13)
        block = bytes(rng.choices(range(256), k=200))
        filler = bytes(rng.choices(range(256), k=2000))
        data = block + filler + block  # 距离 2200 > window=1024
        tokens = list(find_tokens(data, 9, 1024))
        for token in tokens:
            if token[0] == "m":
                self.assertLessEqual(token[1], 1024)
        # 第二个 block 无法整体匹配，输出以字面量为主
        self.assertGreater(len(lzpack.compress(data, window=1024)), len(data) - 50)

    def test_cross_feed_match(self):
        # 匹配跨越两个 feed 边界：流式输出必须与一次性逐字节相同
        head = b"prefix-" * 100
        tail = head[:600]
        oneshot = lzpack.compress(head + tail)
        c = lzpack.Compressor()
        got = c.feed(head) + c.feed(tail) + c.finish()
        self.assertEqual(got, oneshot)
        self.assertEqual(lzpack.decompress(got), head + tail)

    def test_crc_all_zero_and_all_ff(self):
        blob = bytearray(lzpack.compress(b"some payload" * 10))
        # CRC 字段紧跟在头部校验字节之后
        p = 6
        while blob[p] & 0x80:
            p += 1
        crc_at = p + 2  # 长度字段结束 + 1 字节头部校验
        for bad in (b"\x00" * 4, b"\xff" * 4):
            mutated = blob[:]
            mutated[crc_at:crc_at + 4] = bad
            with self.assertRaises(FormatError):
                lzpack.decompress(bytes(mutated))

    def test_finish_twice_returns_empty(self):
        c = lzpack.Compressor()
        c.feed(b"abc")
        self.assertTrue(c.finish())
        self.assertEqual(c.finish(), b"")
        d = lzpack.Decompressor()
        d.feed(lzpack.compress(b"abc"))
        d.finish()
        self.assertEqual(d.finish(), b"")

    def test_feed_after_finish_raises(self):
        c = lzpack.Compressor()
        c.finish()
        with self.assertRaises(ValueError):
            c.feed(b"x")
        d = lzpack.Decompressor()
        d.feed(lzpack.compress(b""))
        d.finish()
        with self.assertRaises(ValueError):
            d.feed(b"x")

    def test_length_field_mismatch(self):
        data = b"hello" * 20
        blob = lzpack.compress(data)
        # 重新构造一个长度字段 +1 / -1 的头部（头部校验字节同步重算）
        for fake_len in (len(data) - 1, len(data) + 1, len(data) * 2):
            meta = blob[4:6]
            len_field = encode_varint(fake_len)
            check = codec.crc32(meta + len_field) & 0xFF
            rest = blob[7:]  # 跳过旧的 1 字节长度字段
            fake = blob[:4] + meta + len_field + bytes([check]) + rest
            with self.assertRaises(FormatError):
                lzpack.decompress(fake)

    def test_incompressible_stored_as_literals(self):
        # 不可压缩数据的策略：原样存储字面量块，开销约 0.8%
        data = random.Random(99).randbytes(100000)
        blob = lzpack.compress(data)
        self.assertLessEqual(len(blob), len(data) * 1.02)
        self.assertEqual(lzpack.decompress(blob), data)

    def test_trailing_garbage(self):
        blob = lzpack.compress(b"abc")
        with self.assertRaises(FormatError):
            lzpack.decompress(blob + b"\x05junk!")

    def test_empty_via_chunked_decompressor(self):
        blob = lzpack.compress(b"")
        for size in (1, 3, 4096):
            self.assertEqual(shuffled_feed(lzpack.Decompressor(), blob, size), b"")

    def test_type_errors(self):
        with self.assertRaises(TypeError):
            lzpack.compress("not bytes")
        with self.assertRaises(TypeError):
            lzpack.decompress(123)
        with self.assertRaises(TypeError):
            lzpack.Compressor().feed("x")
        with self.assertRaises(TypeError):
            lzpack.Decompressor().feed(None)

    def test_window_level_combinations(self):
        data = (LOG_LINE * 50) + bytes(range(256)) * 20
        for level in (1, 5, 9):
            for window in (1024, 32768, 1 << 20):
                blob = lzpack.compress(data, level=level, window=window)
                self.assertEqual(lzpack.decompress(blob), data)


class TestRegressions(unittest.TestCase):
    """lzpack-f06 三处根因的回归测试。"""

    def test_regression_varint_allows_nine_bytes(self):
        # 根因：MAX_VARINT_BYTES 被误改为 5，长整数编码后无法读回
        self.assertEqual(MAX_VARINT_BYTES, 9)
        for v in (1 << 35, 1 << 40, (1 << 63) - 1):
            enc = encode_varint(v)
            self.assertEqual(read_varint(enc, 0), (v, len(enc)))
        self.assertEqual(len(encode_varint((1 << 63) - 1)), 9)

    def test_regression_literal_tag_is_length_minus_one(self):
        # 根因：字面量块标签发的是长度本身，解码端按“标签 + 1”整块多吃一字节
        for n in (1, 2, 127, 128, 129, 300):
            data = random.Random(n).randbytes(n)
            self.assertEqual(lzpack.decompress(lzpack.compress(data)), data)
        # 单个 128 字节字面量块：标签必须是 127（长度 - 1），内容原样跟随
        data = random.Random(5).randbytes(128)
        blob = lzpack.compress(data)
        self.assertEqual(blob[-129], 127)
        self.assertEqual(blob[-128:], data)

    def test_regression_overlap_match_copy(self):
        # 根因：解码端用静态切片拷贝匹配，偏移 < 长度（重叠回引）时内容错位
        for data in (b"a" * 1000, b"ab" * 500, LOG_LINE * 200):
            self.assertEqual(lzpack.decompress(lzpack.compress(data)), data)
        # 手工构造流：字面量 'ab' + 匹配(偏移 2, 长度 8)，应展开为 b"ab" * 5
        body = b"\x01ab" + bytes([0x80 | (8 - 3), 2 - 1])
        head = codec.build_header(10, codec.crc32(b"ab" * 5), 6, 32768)
        self.assertEqual(lzpack.decompress(head + body), b"ab" * 5)


if __name__ == "__main__":
    unittest.main()
