"""根因回归测试（对应两处历史 bug，不改动 test_lzpack.py 的既有用例）。

1. codec._decode_tokens 曾把偏移字段直接当作偏移使用，
   但格式约定该字段存的是「偏移 - 1」，导致所有含匹配的流解码错位；
2. lz77.find_tokens 曾用 i - MAX_MATCH 作为搜索下限，
   正确的边界是 i - window，否则会发出超过头部声明窗口的偏移。
"""

import random
import unittest

import lzpack
from lzpack import codec
from lzpack.lz77 import find_tokens


class TestOffsetFieldConvention(unittest.TestCase):
    """回归：匹配标签后的变长整数是「偏移 - 1」，解码端必须 +1。"""

    def test_offset_field_stores_offset_minus_one(self):
        # 手工构造流：字面量 "abc" + 匹配(长度 3, 偏移字段 = 2)，
        # 字段 2 表示实际偏移 3，正确解码应为 b"abcabc"。
        data = b"abcabc"
        blob = codec.build_header(len(data), codec.crc32(data), 1, 1024)
        blob += b"\x02abc"      # 字面量块：长度 3
        blob += b"\x80\x02"     # 匹配：长度 3，偏移字段 2（即偏移 3）
        self.assertEqual(lzpack.decompress(blob), data)

    def test_offset_field_zero_means_offset_one(self):
        # 偏移字段 0 表示偏移 1（重叠重复），不是非法值。
        data = b"aaaa"
        blob = codec.build_header(len(data), codec.crc32(data), 1, 1024)
        blob += b"\x00a"        # 字面量 'a'
        blob += b"\x80\x00"     # 匹配：长度 3，偏移字段 0（即偏移 1）
        self.assertEqual(lzpack.decompress(blob), data)


class TestWindowBoundsSearch(unittest.TestCase):
    """回归：匹配搜索的下界必须是 i - window，与头部声明的窗口对齐。"""

    def test_repeat_at_window_plus_one_not_matched(self):
        # 重复距离正好 window + 1：该窗口下不能匹配，只能退化为字面量；
        # 窗口放大一倍后同一重复必须能匹配。
        rng = random.Random(20260924)
        block = bytes(rng.choices(range(256), k=200))
        filler = bytes(rng.choices(range(256), k=1025 - 200))
        data = block + filler + block  # 重复距离 = 1025

        tokens = list(find_tokens(data, 9, 1024))
        for token in tokens:
            if token[0] == "m":
                self.assertLessEqual(token[1], 1024)
        # 第二个 block 在 window=1024 下不可匹配，输出以字面量收尾
        self.assertEqual(tokens[-1][0], "l")

        offsets = [t[1] for t in find_tokens(data, 9, 2048) if t[0] == "m"]
        self.assertIn(1025, offsets)  # window=2048 时同一重复成为合法匹配

        for window in (1024, 2048):
            blob = lzpack.compress(data, level=9, window=window)
            self.assertEqual(lzpack.decompress(blob), data)


if __name__ == "__main__":
    unittest.main()
