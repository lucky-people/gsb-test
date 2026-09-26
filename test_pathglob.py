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


class TestCharClassRegression(unittest.TestCase):
    """回归：字符类逐字符正确转义，`-` 在中间时是区间连接符。

    回归背景：字符类曾给每个字符无脑加 `\\` 前缀，导致
    `[abc]` 被翻译成 `[\\a\\b\\c]`（响铃/退格/c），`[a-z]` 的
    区间 `-` 被转义成字面字符，区间退化成 a、-、z 三个字面量。
    """

    def assert_consistent(self, pattern, path, **kwargs):
        """同一规则、同一路径，三个入口结论必须一致。"""
        expected = compile_pattern(pattern, **kwargs).matches(path)
        matcher = Matcher([compile_pattern(pattern, **kwargs)])
        self.assertEqual(matcher.match(path) is not None, expected)
        self.assertEqual(matcher.ignores(path), expected)

    def test_class_matches_listed_chars_not_control_chars(self):
        # [abc] 曾被翻译成 [\a\b\c]：响铃、退格、c
        p = compile_pattern("[abc]", case_sensitive=True)
        self.assertTrue(p.matches("a"))
        self.assertTrue(p.matches("b"))
        self.assertFalse(p.matches("\a"))   # 响铃不应命中
        self.assertFalse(p.matches("\b"))   # 退格不应命中
        self.assert_consistent("[abc]", "a", case_sensitive=True)
        self.assert_consistent("[abc]", "\a", case_sensitive=True)

    def test_range_dash_is_not_literal(self):
        # [a-z] 的 `-` 是区间连接符，不是字面的 `-`
        p = compile_pattern("[a-z]", case_sensitive=True)
        self.assertTrue(p.matches("m"))
        self.assertFalse(p.matches("-"))
        self.assert_consistent("[a-z]", "-", case_sensitive=True)

    def test_dash_at_edges_is_literal(self):
        # 开头或结尾的 `-` 没有区间语义，按字面处理
        for pat in ("[-a]", "[a-]"):
            with self.subTest(pattern=pat):
                p = compile_pattern(pat, case_sensitive=True)
                self.assertTrue(p.matches("-"))
                self.assertTrue(p.matches("a"))
                self.assertFalse(p.matches("m"))

    def test_escaped_dash_is_literal(self):
        p = compile_pattern(r"[a\-z]", case_sensitive=True)
        self.assertTrue(p.matches("-"))
        self.assertFalse(p.matches("m"))

    def test_negated_range_excludes_whole_range(self):
        p = compile_pattern("[!a-z]", case_sensitive=True)
        self.assertFalse(p.matches("m"))
        self.assertTrue(p.matches("-"))
        self.assertTrue(p.matches("0"))

    def test_class_in_matcher_bucket_consistency(self):
        # 含字符类的规则走通配符通道，三个入口结论一致
        matcher = Matcher(["*.py[cod]"])
        self.assertTrue(matcher.ignores("a.pyc"))
        self.assertTrue(matcher.ignores("dir/a.pyd"))
        self.assertFalse(matcher.ignores("a.py"))
        self.assert_consistent("*.py[cod]", "a.pyc")
        self.assert_consistent("*.py[cod]", "a.py")


class TestStarWithinSegmentRegression(unittest.TestCase):
    """回归：段内 `*` 匹配任意个非 `/` 字符，不跨目录。

    回归背景：`*` 曾被翻译成 `.*`，导致 `build/*.tmp` 命中
    `build/x/a.tmp` 这类跨目录路径。
    """

    def test_star_suffix_does_not_cross_directory(self):
        p = compile_pattern("build/*.tmp")
        self.assertTrue(p.matches("build/a.tmp"))
        self.assertFalse(p.matches("build/x/a.tmp"))

    def test_star_middle_does_not_cross_directory(self):
        p = compile_pattern("src/*/main.py")
        self.assertTrue(p.matches("src/mod/main.py"))
        self.assertFalse(p.matches("src/a/b/main.py"))

    def test_unanchored_star_matches_basename_only(self):
        p = compile_pattern("*.tmp")
        self.assertTrue(p.matches("x/y/a.tmp"))
        self.assertFalse(p.matches("a.tmp/b"))

    def test_three_entries_consistent(self):
        for pattern, path in [
            ("build/*.tmp", "build/x/a.tmp"),
            ("build/*.tmp", "build/a.tmp"),
            ("a/*/b", "a/x/y/b"),
            ("a/*/b", "a/x/b"),
        ]:
            with self.subTest(pattern=pattern, path=path):
                expected = compile_pattern(pattern).matches(path)
                matcher = Matcher([pattern])
                self.assertEqual(matcher.match(path) is not None, expected)
                self.assertEqual(matcher.ignores(path), expected)


class TestNormalizeCollapseRegression(unittest.TestCase):
    """回归：normalize_path 折叠重复斜杠、去掉结尾 `/`。

    回归背景：规范化曾保留空段，导致 `a//b` 与 `a/b` 结论不一致。
    """

    def test_repeated_slashes_collapse(self):
        self.assertEqual(normalize_path("a//b"), "a/b")
        self.assertEqual(normalize_path("a///b//c"), "a/b/c")
        self.assertEqual(normalize_path("a/./b//"), "a/b")

    def test_matching_consistent_with_or_without_extra_slashes(self):
        for pattern in ("a/b", "a//b", "a/b/"):
            with self.subTest(pattern=pattern):
                p = compile_pattern(pattern)
                self.assertEqual(p.matches("a//b"), p.matches("a/b"))
        matcher = Matcher(["a/b"])
        self.assertTrue(matcher.ignores("a//b"))
        self.assertTrue(matcher.ignores("a/b"))


class TestEscapeInMatcher(unittest.TestCase):
    """含转义的规则放进 Matcher 后必须与 Pattern.matches 结论一致。

    回归背景：转义规则曾被当作纯字面量分桶，但桶键用的是未反转义的
    原始文本，导致 Matcher 字典查找静默落空（不报错地漏配）。
    """

    def assert_consistent(self, pattern, path, is_dir=False):
        """同一规则、同一路径，三个入口必须给出互相一致的结论。"""
        expected = compile_pattern(pattern).matches(path, is_dir=is_dir)
        matcher = Matcher([pattern])
        matched = matcher.match(path, is_dir=is_dir)
        self.assertEqual(
            matched is not None, expected,
            f"match 与 matches 不一致：{pattern!r} vs {path!r}",
        )
        self.assertEqual(
            matcher.ignores(path, is_dir=is_dir), expected,
            f"ignores 与 matches 不一致：{pattern!r} vs {path!r}",
        )

    def test_escaped_star_question_space_brackets(self):
        # 缺陷报告的四条复现
        for pattern, path in [
            (r"a\*b", "a*b"),
            (r"a\ b", "a b"),
            (r"a\?b", "a?b"),
            (r"a\[b\]c", "a[b]c"),
        ]:
            with self.subTest(pattern=pattern, path=path):
                self.assert_consistent(pattern, path)
                self.assertTrue(Matcher([pattern]).ignores(path))
                self.assertIsNotNone(Matcher([pattern]).match(path))

    def test_escape_at_start_middle_and_end(self):
        for pattern, path in [
            (r"\*x", "*x"),      # 开头
            (r"x\*y", "x*y"),    # 中间
            (r"x\*", "x*"),      # 结尾
            (r"\?q", "?q"),
            (r"q\?", "q?"),
        ]:
            with self.subTest(pattern=pattern, path=path):
                self.assert_consistent(pattern, path)
                self.assertTrue(Matcher([pattern]).ignores(path))

    def test_escaped_bang_and_hash_prefix_unchanged(self):
        # `\!` / `\#` 前缀的既有特例：按字面处理、不触发取反
        for pattern, path in [(r"\!important", "!important"),
                              (r"\#hash", "#hash")]:
            with self.subTest(pattern=pattern):
                pat = compile_pattern(pattern)
                self.assertFalse(pat.negated)
                self.assert_consistent(pattern, path)
                self.assertTrue(Matcher([pattern]).ignores(path))

    def test_escape_in_directory_rule(self):
        # 目录规则（结尾 `/`）里的转义
        matcher = Matcher([r"a\ b/"])
        self.assertTrue(matcher.ignores("a b/x"))
        self.assertTrue(matcher.ignores("a b", is_dir=True))
        self.assertFalse(matcher.ignores("a b", is_dir=False))
        self.assert_consistent(r"a\ b/", "a b/x")
        self.assert_consistent(r"a\ b/", "a b", is_dir=True)

    def test_escape_in_anchored_rule(self):
        # 锚定规则（前导 `/` 或中间含 `/`）里的转义
        matcher = Matcher([r"/a\*b"])
        self.assertTrue(matcher.ignores("a*b"))
        self.assertFalse(matcher.ignores("x/a*b"))
        self.assert_consistent(r"/a\*b", "a*b")
        self.assert_consistent(r"/a\*b", "x/a*b")
        self.assert_consistent(r"dir/a\?b/", "dir/a?b/f")

    def test_escaped_rule_does_not_match_unescaped_path(self):
        # 转义后的字面量不应误中未转义的文本
        matcher = Matcher([r"a\*b"])
        self.assertFalse(matcher.ignores("axb"))
        self.assertFalse(matcher.ignores("a\\*b"))
        self.assert_consistent(r"a\*b", "axb")


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
