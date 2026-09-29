"""灰度对照回归用例：miniregex-g02 切换前暴露的三处语义差异。

对照基准 test_miniregex.py 保持原样，本文件为每处差异各补一条
回归用例，并在 docstring 中记录「为什么这么判定」，判定理由同时
收录于 README 的「灰度对照确认的关键判定」一节。
"""

import unittest

from miniregex import compile_pattern
from miniregex.errors import PatternError


class TestQuantifierWithoutAtomRegression(unittest.TestCase):
    """差异 1：量词前面没有原子时必须抛 PatternError，不能当字面量吃掉。

    判定理由：孤立的量词几乎一定是模式拼写错误，静默按字面量处理会
    让错误模式"碰巧能跑"而产出错误结果；旧实现与 README 语义表均约定
    报错，且位置必须精确到该量词字符本身。
    """

    def test_lone_quantifier_raises_at_exact_position(self):
        for pattern, position in (("*a", 0), ("+", 0), ("a|?", 2), ("(a)*b**", 6)):
            with self.assertRaises(PatternError) as ctx:
                compile_pattern(pattern)
            self.assertEqual(ctx.exception.position, position,
                             "%r 应在位置 %d 报错" % (pattern, position))
            self.assertEqual(ctx.exception.pattern, pattern)


class TestMultilineBolRegression(unittest.TestCase):
    """差异 2：multiline=True 时 ^ 必须匹配每行行首，而非只认整段开头。

    判定理由：README 语义表承诺 multiline 下 ^/$ 以 '\\n' 为界匹配每行
    行首/行尾，二者行为对称；只认整段开头会让 ^ 在 multiline 下退化成
    与默认模式几乎无差别，失去该开关的意义。
    """

    def test_bol_matches_every_line_start(self):
        r = compile_pattern("^b", multiline=True)
        self.assertEqual(r.search("a\nb\nc").span(), (2, 3))
        self.assertEqual(
            compile_pattern("^.", multiline=True).findall("ab\ncd"), ["a", "c"])
        # 默认（非 multiline）行为不受影响：^ 仍只认整段开头
        self.assertIsNone(compile_pattern("^b").search("a\nb"))


class TestBackrefUnmatchedGroupRegression(unittest.TestCase):
    """差异 3：反向引用指向未参与匹配的组时匹配失败，而非按空串比较。

    判定理由：与标准库 re 及旧实现一致——未捕获的组没有"内容"可引用，
    按空串处理会让 (a)?b\\1 在 "b" 上错误匹配成功，静默改变匹配语义；
    且组已捕获时反向引用必须引用该组最后一次捕获的实际文本。
    """

    def test_backref_to_unmatched_group_fails(self):
        self.assertIsNone(compile_pattern(r"(a)?b\1").match("b"))
        self.assertIsNotNone(compile_pattern(r"(a)?b\1").match("aba"))
        # 组参与匹配时引用的是最后一次捕获的实际内容
        m = compile_pattern(r"(a|b)+c\1").match("abcb")
        self.assertEqual(m.group(0), "abcb")


if __name__ == "__main__":
    unittest.main()
