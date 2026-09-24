"""pathglob 的单元测试（unittest）。"""

import time
import unittest

from pathglob import Matcher, Pattern, compile_pattern, normalize_path
from pathglob.errors import PathError, PatternError


class TestStarAndDoubleStar(unittest.TestCase):
    """`*` 不跨 `/`，`**` 跨目录。"""

    def test_star_does_not_cross_slash(self):
        p = compile_pattern("a/*/b")
        self.assertTrue(p.matches("a/x/b"))
        self.assertFalse(p.matches("a/x/y/b"))

    def test_double_star_crosses_directories(self):
        p = compile_pattern("a/**/b")
        self.assertTrue(p.matches("a/x/y/b"))
        self.assertTrue(p.matches("a/x/b"))
        self.assertTrue(p.matches("a/b"))  # ** 可匹配零层目录

    def test_trailing_double_star_matches_self(self):
        # 明确约定：`a/**` 匹配 `a` 自身及其下所有内容
        p = compile_pattern("a/**")
        self.assertTrue(p.matches("a"))
        self.assertTrue(p.matches("a/x"))
        self.assertTrue(p.matches("a/x/y"))
        self.assertFalse(p.matches("ab"))

    def test_star_matches_within_segment(self):
        p = compile_pattern("*.txt")
        self.assertTrue(p.matches("a.txt"))
        self.assertTrue(p.matches("dir/b.txt"))  # 非锚定，按 basename
        self.assertFalse(p.matches("a.txt/b"))

    def test_question_mark_single_non_separator(self):
        p = compile_pattern("a?c")
        self.assertTrue(p.matches("abc"))
        self.assertFalse(p.matches("ac"))
        self.assertFalse(p.matches("a/c"))

    def test_double_star_alone_matches_everything(self):
        p = compile_pattern("**")
        self.assertTrue(p.matches("a"))
        self.assertTrue(p.matches("a/b/c"))

    def test_consecutive_double_star_collapses(self):
        p = compile_pattern("a/**/**/b")
        self.assertTrue(p.matches("a/b"))
        self.assertTrue(p.matches("a/x/y/b"))


class TestAnchoring(unittest.TestCase):
    def test_leading_slash_anchors_to_root(self):
        p = compile_pattern("/foo")
        self.assertTrue(p.anchored)
        self.assertTrue(p.matches("foo"))
        self.assertFalse(p.matches("a/foo"))

    def test_middle_slash_anchors_to_root(self):
        p = compile_pattern("doc/*.md")
        self.assertTrue(p.anchored)
        self.assertTrue(p.matches("doc/a.md"))
        self.assertFalse(p.matches("x/doc/a.md"))

    def test_unanchored_matches_any_depth(self):
        p = compile_pattern("foo")
        self.assertFalse(p.anchored)
        self.assertTrue(p.matches("foo"))
        self.assertTrue(p.matches("a/b/foo"))


class TestDirectoryRules(unittest.TestCase):
    def test_trailing_slash_is_directory_only(self):
        p = compile_pattern("build/")
        self.assertTrue(p.directory_only)
        self.assertTrue(p.matches("build", is_dir=True))
        self.assertFalse(p.matches("build", is_dir=False))

    def test_directory_rule_matches_contents(self):
        p = compile_pattern("build/")
        self.assertTrue(p.matches("build/out.o"))
        self.assertTrue(p.matches("build/out.o", is_dir=True))
        self.assertTrue(p.matches("src/build/out.o"))  # 非锚定

    def test_anchored_directory_rule(self):
        p = compile_pattern("/build/")
        self.assertTrue(p.matches("build/out.o"))
        self.assertFalse(p.matches("src/build/out.o"))

    def test_directory_rule_requires_dir_flag_for_exact_match(self):
        p = compile_pattern("build/")
        self.assertFalse(p.matches("build"))  # 默认 is_dir=False
        self.assertTrue(p.matches("build", is_dir=True))


class TestCharClass(unittest.TestCase):
    def test_simple_class(self):
        p = compile_pattern("[abc].txt", case_sensitive=True)
        self.assertTrue(p.matches("a.txt"))
        self.assertTrue(p.matches("c.txt"))
        self.assertFalse(p.matches("d.txt"))

    def test_range_class(self):
        p = compile_pattern("[a-z]", case_sensitive=True)
        self.assertTrue(p.matches("b"))
        self.assertFalse(p.matches("A"))
        self.assertFalse(p.matches("0"))

    def test_negated_class_both_forms(self):
        for pat in ("[!a-z]", "[^a-z]"):
            p = compile_pattern(pat, case_sensitive=True)
            self.assertTrue(p.matches("A"))
            self.assertFalse(p.matches("b"))

    def test_negated_class_never_matches_slash(self):
        p = compile_pattern("a[!b]c", case_sensitive=True)
        self.assertTrue(p.matches("axc"))
        self.assertFalse(p.matches("a/c"))

    def test_bracket_as_first_char_is_literal(self):
        p = compile_pattern("[]a]", case_sensitive=True)
        self.assertTrue(p.matches("]"))
        self.assertTrue(p.matches("a"))
        self.assertFalse(p.matches("b"))

    def test_unclosed_class_raises(self):
        with self.assertRaises(PatternError) as ctx:
            compile_pattern("ab[cd")
        self.assertEqual(ctx.exception.pattern, "ab[cd")
        self.assertIsInstance(ctx.exception.position, int)


class TestEscape(unittest.TestCase):
    def test_escaped_star_is_literal(self):
        p = compile_pattern(r"\*")
        self.assertTrue(p.matches("*"))
        self.assertFalse(p.matches("x"))

    def test_escaped_backslash_compiles(self):
        # `\\` 表示字面反斜杠；规范化路径中不会出现反斜杠，故永不命中
        p = compile_pattern("a\\\\b")
        self.assertFalse(p.matches("a/b"))
        self.assertFalse(p.matches("ab"))

    def test_trailing_backslash_raises(self):
        with self.assertRaises(PatternError) as ctx:
            compile_pattern("abc\\")
        self.assertIn("反斜杠", str(ctx.exception))

    def test_escaped_leading_bang_is_literal(self):
        p = compile_pattern("\\!important")
        self.assertFalse(p.negated)
        self.assertTrue(p.matches("!important"))


class TestMatcherEscapeConsistency(unittest.TestCase):
    """含转义的规则在 Pattern 与 Matcher 两个入口下结论必须一致。

    回归背景：转义规则曾被当作纯字面量分桶，但桶键误用未去转义的
    原始文本，导致 Matcher 查字典永远落空、静默漏配。
    """

    def test_repro_four_escaped_rules(self):
        # 缺陷报告中的四条复现：ignores 为 True 且 match 非 None
        cases = [
            (r"a\*b", "a*b"),
            (r"a\ b", "a b"),
            (r"a\?b", "a?b"),
            (r"a\[b\]c", "a[b]c"),
        ]
        for pat, path in cases:
            with self.subTest(pat=pat, path=path):
                m = Matcher([pat])
                self.assertTrue(m.ignores(path))
                self.assertIsNotNone(m.match(path))

    def test_entry_points_agree_invariant(self):
        # 不变量：同一规则同一路径，三个入口的结论必须互相一致
        cases = [
            (r"a\*b", "a*b", False),
            (r"a\*b", "aXb", False),
            (r"a\ b", "a b", False),
            (r"a\?b", "a?b", False),
            (r"a\?b", "axb", False),
            (r"a\[b\]c", "a[b]c", False),
            (r"a\[b\]c", "abc", False),
            (r"\*lead", "*lead", False),
            (r"trail\*", "trail*", False),
            (r"\!important", "!important", False),
            (r"\#hash", "#hash", False),
            (r"my\ dir/", "my dir/x", False),
            (r"my\ dir/", "my dir", True),
            (r"my\ dir/", "my dir", False),
            (r"/a\*b", "a*b", False),
            (r"/a\*b", "x/a*b", False),
            (r"/a\ b/", "a b/c", False),
            (r"/a\ b/", "x/a b/c", False),
            ("*.log", "x.log", False),
            ("build/", "build/out.o", False),
            ("**/node_modules/**", "a/node_modules/b", False),
        ]
        for pat, path, is_dir in cases:
            with self.subTest(pat=pat, path=path, is_dir=is_dir):
                expected = compile_pattern(pat).matches(path, is_dir=is_dir)
                m = Matcher([pat])
                self.assertEqual(m.ignores(path, is_dir=is_dir), expected)
                self.assertEqual(m.match(path, is_dir=is_dir) is not None, expected)

    def test_escape_at_start_middle_end(self):
        for pat, path in [(r"\*abc", "*abc"), (r"a\*b", "a*b"), (r"abc\*", "abc*")]:
            with self.subTest(pat=pat):
                self.assertTrue(Matcher([pat]).ignores(path))

    def test_escaped_bang_and_hash_prefixes(self):
        # \! 与 \# 前缀的既有特例行为不得回退：按字面、不算取反
        m = Matcher([r"\!important", r"\#hash"])
        self.assertTrue(m.ignores("!important"))
        self.assertTrue(m.ignores("#hash"))
        self.assertFalse(m.match("!important").negated)
        self.assertFalse(m.match("#hash").negated)
        self.assertFalse(m.ignores("important"))

    def test_escape_in_directory_rule(self):
        m = Matcher([r"my\ dir/"])
        self.assertTrue(m.ignores("my dir/out.o"))
        self.assertTrue(m.ignores("my dir", is_dir=True))
        self.assertFalse(m.ignores("my dir", is_dir=False))
        self.assertFalse(m.ignores("mydir/out.o"))

    def test_escape_in_anchored_rule(self):
        m = Matcher([r"/a\*b"])
        self.assertTrue(m.ignores("a*b"))
        self.assertFalse(m.ignores("x/a*b"))
        m_dir = Matcher([r"/a\ b/"])
        self.assertTrue(m_dir.ignores("a b/c"))
        self.assertFalse(m_dir.ignores("x/a b/c"))

    def test_escaped_literal_case_insensitive_bucket(self):
        # 默认大小写不敏感：去转义后的桶键同样按 casefold 归一
        m = Matcher([r"A\*B"])
        self.assertTrue(m.ignores("a*b"))
        m_cs = Matcher([compile_pattern(r"A\*B", case_sensitive=True)])
        self.assertFalse(m_cs.ignores("a*b"))
        self.assertTrue(m_cs.ignores("A*B"))

    def test_escaped_literal_last_match_wins(self):
        # 转义字面量规则与通配符规则混排时仍按“最后命中”求值
        m = Matcher([r"a\*b", "!a*b"])
        self.assertFalse(m.ignores("a*b"))
        m2 = Matcher(["!a*b", r"a\*b"])
        self.assertTrue(m2.ignores("a*b"))


class TestNegationAndOrder(unittest.TestCase):
    def test_negation_reincludes(self):
        m = Matcher(["*.txt", "!keep.txt"])
        self.assertTrue(m.ignores("a.txt"))
        self.assertFalse(m.ignores("keep.txt"))

    def test_last_match_wins(self):
        m = Matcher(["*.txt", "!*.txt", "a.txt"])
        self.assertTrue(m.ignores("a.txt"))
        self.assertFalse(m.ignores("b.txt"))

    def test_negation_without_prior_rule(self):
        # `!` 规则没有前置规则时：命中但结果为“不忽略”
        m = Matcher(["!foo.txt"])
        self.assertFalse(m.ignores("foo.txt"))
        matched = m.match("foo.txt")
        self.assertIsNotNone(matched)
        self.assertTrue(matched.negated)

    def test_match_returns_none_when_no_hit(self):
        m = Matcher(["*.txt"])
        self.assertIsNone(m.match("a.py"))
        self.assertFalse(m.ignores("a.py"))

    def test_matcher_accepts_patterns_and_strings(self):
        m = Matcher([compile_pattern("*.o"), "build/"])
        self.assertTrue(m.ignores("x.o"))
        self.assertTrue(m.ignores("build/x.o"))


class TestNormalizePath(unittest.TestCase):
    def test_backslash_becomes_slash(self):
        self.assertEqual(normalize_path("a\\b\\c"), "a/b/c")

    def test_collapses_repeated_slashes_and_dot(self):
        self.assertEqual(normalize_path("./a//b/./c"), "a/b/c")

    def test_strips_trailing_slash(self):
        self.assertEqual(normalize_path("a/b/"), "a/b")

    def test_windows_style_input_matches(self):
        p = compile_pattern("src/*.py")
        self.assertTrue(p.matches("src\\main.py"))

    def test_absolute_path_raises(self):
        with self.assertRaises(PathError):
            normalize_path("/etc/passwd")

    def test_drive_path_raises(self):
        with self.assertRaises(PathError):
            normalize_path("C:/Users/x")

    def test_dotdot_raises(self):
        for bad in ("../a", "a/../b", ".."):
            with self.assertRaises(PathError):
                normalize_path(bad)

    def test_empty_raises(self):
        with self.assertRaises(PathError):
            normalize_path("")

    def test_error_carries_context(self):
        try:
            normalize_path("/abs")
        except PathError as exc:
            self.assertEqual(exc.path, "/abs")
            self.assertIn("绝对路径", str(exc))
        else:
            self.fail("应当抛出 PathError")


class TestCaseSensitivity(unittest.TestCase):
    def test_default_case_insensitive(self):
        p = compile_pattern("README")
        self.assertFalse(p.case_sensitive)
        self.assertTrue(p.matches("readme"))
        self.assertTrue(p.matches("ReadMe"))

    def test_explicit_case_sensitive(self):
        p = compile_pattern("README", case_sensitive=True)
        self.assertTrue(p.matches("README"))
        self.assertFalse(p.matches("readme"))

    def test_matcher_mixed_case_rules(self):
        m = Matcher([
            compile_pattern("*.LOG", case_sensitive=True),
            "*.tmp",
        ])
        self.assertTrue(m.ignores("a.LOG"))
        self.assertFalse(m.ignores("a.log"))
        self.assertTrue(m.ignores("a.TMP"))


class TestUnicodeAndSpaces(unittest.TestCase):
    def test_non_ascii(self):
        p = compile_pattern("文档/*.txt")
        self.assertTrue(p.matches("文档/报告.txt"))
        self.assertFalse(p.matches("文档/报告.md"))

    def test_casefold_non_ascii(self):
        # casefold 对非 ASCII 同样生效（如德语 ß）
        p = compile_pattern("STRASSE/*")
        self.assertTrue(p.matches("straße/x"))

    def test_spaces_in_names(self):
        p = compile_pattern("my file?.txt")
        self.assertTrue(p.matches("my file1.txt"))
        self.assertTrue(p.matches("my file .txt"))
        literal = compile_pattern("my file.txt")
        self.assertTrue(literal.matches("my file.txt"))


class TestLongPath(unittest.TestCase):
    def test_4096_char_path(self):
        path = "/".join(["d"] * 2047 + ["end.txt"])  # 4096+ 字符
        self.assertGreaterEqual(len(path), 4096)
        p = compile_pattern("**/end.txt")
        self.assertTrue(p.matches(path))
        self.assertTrue(Matcher(["d/**/end.txt"]).ignores(path))
        self.assertFalse(compile_pattern("**/other.txt").matches(path))


class TestPatternErrors(unittest.TestCase):
    def test_empty_pattern(self):
        with self.assertRaises(PatternError):
            compile_pattern("")

    def test_bang_only(self):
        with self.assertRaises(PatternError) as ctx:
            compile_pattern("!")
        self.assertEqual(ctx.exception.pattern, "!")

    def test_slash_only(self):
        with self.assertRaises(PatternError):
            compile_pattern("/")

    def test_attributes_on_pattern(self):
        p = compile_pattern("!/build/", case_sensitive=True)
        self.assertEqual(p.original, "!/build/")
        self.assertTrue(p.negated)
        self.assertTrue(p.directory_only)
        self.assertTrue(p.anchored)
        self.assertTrue(p.case_sensitive)


class TestPerformance(unittest.TestCase):
    """500 路径 × 50 规则的批量判定应在很短时间内完成。"""

    def test_batch_500x50(self):
        rules = (
            [f"vendor/pkg{i}/" for i in range(20)]
            + [f"*.{i}.tmp" for i in range(20)]
            + ["node_modules/", "build/", "*.o", "*.log", "docs/**",
               "!docs/keep.md", "src/**/test_*.py", "*.py[cod]",
               "__pycache__/", ".git/"]
        )
        self.assertEqual(len(rules), 50)
        paths = []
        for i in range(500):
            if i % 5 == 0:
                paths.append(f"node_modules/pkg{i}/index.js")
            elif i % 5 == 1:
                paths.append(f"src/mod{i}/main.py")
            elif i % 5 == 2:
                paths.append(f"build/out{i}.o")
            elif i % 5 == 3:
                paths.append(f"docs/guide{i}.md")
            else:
                paths.append(f"src/mod{i}/util{i}.py")
        matcher = Matcher(rules)
        start = time.perf_counter()
        hits = sum(matcher.ignores(p) for p in paths)
        elapsed = time.perf_counter() - start
        # node_modules(100) + build(100) + docs(100) = 300 命中
        self.assertEqual(hits, 300)
        self.assertLess(elapsed, 10.0, f"批量判定过慢：{elapsed:.3f}s")


if __name__ == "__main__":
    unittest.main()
