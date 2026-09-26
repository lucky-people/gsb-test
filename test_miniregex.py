"""miniregex 测试套件：覆盖规格中的每条语义、全部报错位置、
反向引用、懒惰/贪婪对比与 ReDoS 用例。"""

import unittest

from miniregex import Match, Regex, compile_pattern
from miniregex.errors import MatchLimitError, PatternError


class TestInterface(unittest.TestCase):
    """对外接口形态。"""

    def test_compile_returns_regex(self):
        self.assertIsInstance(compile_pattern("a"), Regex)

    def test_match_returns_match_or_none(self):
        r = compile_pattern("a+")
        self.assertIsInstance(r.match("aaa"), Match)
        self.assertIsNone(r.match("bbb"))

    def test_match_pos(self):
        r = compile_pattern("a")
        self.assertIsNone(r.match("ba"))
        self.assertEqual(r.match("ba", 1).span(), (1, 2))

    def test_fullmatch(self):
        r = compile_pattern("a+")
        self.assertIsNotNone(r.fullmatch("aaa"))
        self.assertIsNone(r.fullmatch("aab"))
        # fullmatch 允许通过回溯找到覆盖整串的匹配
        self.assertIsNotNone(compile_pattern("a*ab").fullmatch("aab"))

    def test_search_pos(self):
        r = compile_pattern("a")
        self.assertEqual(r.search("baaa").span(), (1, 2))
        self.assertEqual(r.search("baaa", 2).span(), (2, 3))
        self.assertIsNone(r.search("bbb"))

    def test_finditer(self):
        r = compile_pattern(r"\d+")
        spans = [m.span() for m in r.finditer("a1b22c333")]
        self.assertEqual(spans, [(1, 2), (3, 5), (6, 9)])

    def test_finditer_empty_match(self):
        # 空匹配每次前进一位，不会死循环
        spans = [m.span() for m in compile_pattern("a*").finditer("aab")]
        self.assertEqual(spans, [(0, 2), (2, 2), (3, 3)])

    def test_findall(self):
        self.assertEqual(compile_pattern(r"\d+").findall("a1b22"), ["1", "22"])
        # 即使有捕获组，findall 也只返回整体匹配
        self.assertEqual(compile_pattern(r"(\d)(\d)").findall("12 34"),
                         ["12", "34"])

    def test_match_accessors(self):
        m = compile_pattern(r"(\w+)-(\d+)").search("id: abc-123")
        self.assertEqual(m.group(0), "abc-123")
        self.assertEqual(m.group(1), "abc")
        self.assertEqual(m.group(2), "123")
        self.assertEqual(m.groups(), ("abc", "123"))
        self.assertEqual((m.start(), m.end()), (4, 11))
        self.assertEqual(m.start(2), 8)
        self.assertEqual(m.end(2), 11)
        self.assertEqual(m.text, "id: abc-123")
        self.assertEqual(m.matched, "abc-123")

    def test_group_index_out_of_range(self):
        m = compile_pattern("(a)").match("a")
        with self.assertRaises(IndexError):
            m.group(2)
        with self.assertRaises(IndexError):
            m.start(-1)


class TestCharClass(unittest.TestCase):
    """语义 1：字符类的边界规则。"""

    def test_dash_at_edges_is_literal(self):
        self.assertEqual(compile_pattern("[-a]+").match("-a-").group(0), "-a-")
        self.assertEqual(compile_pattern("[a-]+").match("a-a").group(0), "a-a")

    def test_rbracket_first_is_literal(self):
        self.assertEqual(compile_pattern("[]a]+").match("]a]").group(0), "]a]")
        # 取反后 ']' 与 'a' 都被排除
        self.assertEqual(compile_pattern("[^]a]+").match("b]a").group(0), "b")

    def test_escape_in_class(self):
        self.assertEqual(compile_pattern(r"[\]]+").match("]]").group(0), "]]")
        self.assertEqual(compile_pattern(r"[\d.]+").match("3.14").group(0), "3.14")
        self.assertEqual(compile_pattern(r"[\-a]+").match("-a-").group(0), "-a-")

    def test_range(self):
        r = compile_pattern("[a-c]+")
        self.assertEqual(r.match("abcab").group(0), "abcab")
        self.assertIsNone(r.match("z"))

    def test_negated(self):
        self.assertEqual(compile_pattern("[^a]+").match("bcd").group(0), "bcd")
        self.assertIsNone(compile_pattern("[^a]+").match("ab"))

    def test_illegal_range_raises(self):
        with self.assertRaises(PatternError) as ctx:
            compile_pattern("[z-a]")
        self.assertEqual(ctx.exception.position, 3)

    def test_class_escape_as_range_endpoint_raises(self):
        with self.assertRaises(PatternError):
            compile_pattern(r"[\d-z]")
        with self.assertRaises(PatternError):
            compile_pattern(r"[a-\d]")

    def test_predefined_classes(self):
        self.assertEqual(compile_pattern(r"\d+").match("123").group(0), "123")
        self.assertEqual(compile_pattern(r"\D+").match("ab!").group(0), "ab!")
        self.assertEqual(compile_pattern(r"\w+").match("a_1").group(0), "a_1")
        self.assertEqual(compile_pattern(r"\W+").match(" !").group(0), " !")
        self.assertEqual(compile_pattern(r"\s+").match(" \t\n").group(0), " \t\n")
        self.assertEqual(compile_pattern(r"\S+").match("ab").group(0), "ab")


class TestDotAndAnchors(unittest.TestCase):
    """语义 2、3：通配符与锚点。"""

    def test_dot_excludes_newline_by_default(self):
        self.assertIsNone(compile_pattern("a.c").match("a\nc"))

    def test_dot_all(self):
        m = compile_pattern("a.c", dot_all=True).match("a\nc")
        self.assertEqual(m.group(0), "a\nc")

    def test_anchors_default_whole_string(self):
        self.assertIsNone(compile_pattern("^b").search("a\nb"))
        self.assertIsNone(compile_pattern("a$").search("a\nb"))
        self.assertIsNotNone(compile_pattern("^a").match("a\nb"))
        self.assertIsNotNone(compile_pattern("b$").search("a\nb"))

    def test_anchors_multiline(self):
        r = compile_pattern("^b$", multiline=True)
        m = r.search("a\nb\nc")
        self.assertEqual(m.span(), (2, 3))
        self.assertEqual(
            compile_pattern("^.", multiline=True).findall("ab\ncd"), ["a", "c"])
        self.assertEqual(
            compile_pattern(".$", multiline=True).findall("ab\ncd"), ["b", "d"])


class TestQuantifiers(unittest.TestCase):
    """语义 4：贪婪与懒惰。"""

    def test_greedy_by_default(self):
        self.assertEqual(compile_pattern("a*").match("aaa").group(0), "aaa")
        self.assertEqual(compile_pattern("a+").match("aaa").group(0), "aaa")
        self.assertEqual(compile_pattern("a{1,3}").match("aaaa").group(0), "aaa")

    def test_lazy(self):
        self.assertEqual(compile_pattern("a*?").match("aaa").group(0), "")
        self.assertEqual(compile_pattern("a+?").match("aaa").group(0), "a")
        self.assertEqual(compile_pattern("a??").match("a").group(0), "")
        self.assertEqual(compile_pattern("a{1,3}?").match("aaa").group(0), "a")

    def test_lazy_vs_greedy_search(self):
        text = "<a><b>"
        self.assertEqual(compile_pattern("<.*>").search(text).group(0), "<a><b>")
        self.assertEqual(compile_pattern("<.*?>").search(text).group(0), "<a>")

    def test_brace_forms(self):
        self.assertEqual(compile_pattern("a{3}").match("aaaa").group(0), "aaa")
        self.assertIsNone(compile_pattern("a{3}").match("aa"))
        self.assertEqual(compile_pattern("a{2,}").match("aaaa").group(0), "aaaa")
        self.assertEqual(compile_pattern("a{0}").match("aaa").group(0), "")

    def test_optional_nullable_no_infinite_loop(self):
        # 可空子表达式的星号必须终止
        self.assertEqual(compile_pattern("(a*)*").match("aaa").group(0), "aaa")
        self.assertEqual(compile_pattern("(a*)+").match("b").group(0), "")
        self.assertEqual(compile_pattern("(a?)*b").match("aab").group(0), "aab")


class TestAlternationAndGroups(unittest.TestCase):
    """语义 5、6：分支顺序、分组编号、反向引用。"""

    def test_alternation_left_to_right(self):
        self.assertEqual(compile_pattern("ab|a").match("ab").group(0), "ab")
        self.assertEqual(compile_pattern("a|ab").match("ab").group(0), "a")
        self.assertEqual(compile_pattern("a|b|c").match("c").group(0), "c")

    def test_empty_branch(self):
        self.assertEqual(compile_pattern("a|").match("b").group(0), "")

    def test_group_numbering(self):
        r = compile_pattern("(a)(?:b)(c)")
        self.assertEqual(r.groups, 2)
        m = r.match("abc")
        self.assertEqual(m.groups(), ("a", "c"))

    def test_nested_group_numbering(self):
        m = compile_pattern("((a)(b))").match("ab")
        self.assertEqual(m.group(1), "ab")
        self.assertEqual(m.group(2), "a")
        self.assertEqual(m.group(3), "b")

    def test_nonparticipating_group(self):
        m = compile_pattern("(a)|(b)").match("a")
        self.assertEqual(m.groups(), ("a", None))
        self.assertEqual(m.start(2), -1)
        self.assertEqual(m.end(2), -1)

    def test_backref(self):
        self.assertIsNotNone(compile_pattern(r"(\w+) \1").match("hello hello"))
        self.assertIsNone(compile_pattern(r"(\w+) \1").match("hello world"))
        m = compile_pattern(r"(ab|cd)\1").match("cdcd")
        self.assertEqual(m.group(0), "cdcd")

    def test_backref_repeats_last_capture(self):
        # 反向引用引用的是该组最后一次捕获的实际内容
        m = compile_pattern(r"(a|b)+c\1").match("abcb")
        self.assertEqual(m.group(0), "abcb")

    def test_backref_to_unmatched_group_fails(self):
        self.assertIsNone(compile_pattern(r"(a)?b\1").match("b"))
        self.assertIsNotNone(compile_pattern(r"(a)?b\1").match("aba"))

    def test_backref_missing_group_raises(self):
        with self.assertRaises(PatternError) as ctx:
            compile_pattern(r"(a)\2")
        self.assertEqual(ctx.exception.position, 3)
        with self.assertRaises(PatternError):
            compile_pattern(r"\1")

    def test_backref_case_insensitive(self):
        m = compile_pattern(r"(ab)\1", case_sensitive=False).match("aBAb")
        self.assertEqual(m.group(0), "aBAb")


class TestCaseInsensitive(unittest.TestCase):
    """语义 7：casefold 比较，捕获保留原文。"""

    def test_literal(self):
        m = compile_pattern("abc", case_sensitive=False).match("AbC")
        self.assertEqual(m.group(0), "AbC")

    def test_class(self):
        r = compile_pattern("[a-c]+", case_sensitive=False)
        self.assertEqual(r.match("AbC").group(0), "AbC")

    def test_case_sensitive_default(self):
        self.assertIsNone(compile_pattern("abc").match("ABC"))

    def test_capture_keeps_original_text(self):
        m = compile_pattern(r"(hello)", case_sensitive=False).search("say HELLO")
        self.assertEqual(m.group(1), "HELLO")


class TestPatternErrors(unittest.TestCase):
    """语义 8：语法错误与精确位置。"""

    def assert_error(self, pattern, position):
        with self.assertRaises(PatternError) as ctx:
            compile_pattern(pattern)
        err = ctx.exception
        self.assertEqual(err.position, position,
                         "%r 报错位置应为 %d，实际 %d" % (pattern, position, err.position))
        self.assertEqual(err.pattern, pattern)
        self.assertTrue(err.message)  # 中文说明非空

    def test_quantifier_without_atom(self):
        self.assert_error("*a", 0)
        self.assert_error("+a", 0)
        self.assert_error("?a", 0)
        self.assert_error("a**", 2)
        self.assert_error("a|*", 2)

    def test_bad_brace(self):
        self.assert_error("a{,}", 1)
        self.assert_error("a{x}", 1)
        self.assert_error("a{1,x}", 1)
        self.assert_error("a{1", 1)

    def test_reversed_brace(self):
        self.assert_error("a{3,2}", 1)

    def test_unclosed_group(self):
        self.assert_error("(ab", 0)
        self.assert_error("a(b(c)", 1)

    def test_unclosed_class(self):
        self.assert_error("[ab", 0)
        self.assert_error("x[^a", 1)

    def test_trailing_backslash(self):
        self.assert_error("ab\\", 2)
        self.assert_error("\\", 0)

    def test_unmatched_rparen(self):
        self.assert_error("a)", 1)

    def test_unknown_escape(self):
        self.assert_error("\\q", 0)

    def test_zero_backref(self):
        self.assert_error("\\0", 0)

    def test_unsupported_group_syntax(self):
        self.assert_error("(?=a)", 0)

    def test_oversized_repeat(self):
        self.assert_error("a{10001}", 1)


class TestReDoS(unittest.TestCase):
    """算法安全：灾难性回溯被步数上限拦截。"""

    def test_evil_pattern_raises_limit(self):
        r = compile_pattern("(a+)+b")
        with self.assertRaises(MatchLimitError):
            r.match("a" * 30 + "c")

    def test_limit_is_per_start_position(self):
        # 正常文本上的 search 不应误触发上限
        r = compile_pattern(r"\d{3}-\d{4}")
        text = "x" * 100000 + "555-1234"
        self.assertEqual(r.search(text).group(0), "555-1234")

    def test_limit_adjustable(self):
        r = compile_pattern("(a+)+b")
        r.match_limit = 100
        with self.assertRaises(MatchLimitError) as ctx:
            r.match("a" * 20 + "c")
        self.assertEqual(ctx.exception.limit, 100)

    def test_evil_pattern_still_matches_good_input(self):
        r = compile_pattern("(a+)+b")
        self.assertEqual(r.match("a" * 30 + "b").group(0), "a" * 30 + "b")


class TestMisc(unittest.TestCase):
    def test_literal_brace_and_rbracket(self):
        # 未跟在原子后的 '{' 按字面量
        self.assertEqual(compile_pattern("{2}a").match("{2}a").group(0), "{2}a")
        self.assertEqual(compile_pattern("}a]").match("}a]").group(0), "}a]")

    def test_escaped_punctuation(self):
        self.assertEqual(compile_pattern(r"\.\*\\").match(".*\\").group(0), ".*\\")

    def test_empty_pattern(self):
        m = compile_pattern("").match("abc")
        self.assertEqual(m.span(), (0, 0))

    def test_match_text_property(self):
        m = compile_pattern("b").search("abc")
        self.assertEqual(m.text, "abc")

    def test_repr(self):
        self.assertIn("a+", repr(compile_pattern("a+")))
        m = compile_pattern("a+").match("aa")
        self.assertIn("aa", repr(m))


if __name__ == "__main__":
    unittest.main()
