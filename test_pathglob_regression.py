"""pathglob 切换验收的回归用例（对照基准 test_pathglob.py 的补充）。

本文件只记录迁移对照（pathglob-f02）中暴露过的差异及其判定理由，
基准用例文件 test_pathglob.py 不得修改。
"""

import time
import unittest

from pathglob import Matcher, compile_pattern, normalize_path


class TestMiddleSlashAnchoring(unittest.TestCase):
    """差异一：中间含斜杠的模式必须锚定到仓库根。

    为什么：gitignore 规定，只要模式里除前导 `/` 外还出现 `/`，
    该模式就相对于 .gitignore 所在目录匹配，不会在任意深度下按
    basename 命中。旧实现按此行为做灰度对照，迁移时一度退化成
    “任意深度命中”，导致 doc/*.md 误中 x/doc/a.md。
    """

    def test_slash_in_middle_sets_anchored(self):
        pat = compile_pattern("doc/*.md")
        self.assertTrue(pat.anchored)
        self.assertTrue(pat.matches("doc/a.md"))
        self.assertFalse(pat.matches("x/doc/a.md"))

    def test_leading_double_star_slash_is_not_anchored(self):
        # 例外：开头的 `**/` 语义就是“任意深度”，不能因为模式里
        # 出现 `/` 而被锚定，否则深层路径会漏配。
        pat = compile_pattern("**/end.txt")
        self.assertFalse(pat.anchored)
        self.assertTrue(pat.matches("end.txt"))
        self.assertTrue(pat.matches("a/b/end.txt"))

    def test_matcher_buckets_follow_anchoring(self):
        # 锚定的字面量规则必须进“完整路径桶”，不能按 basename 在
        # 任意深度下命中（保证分桶与正则结论一致）。
        matcher = Matcher(["dir/keep.txt"])
        self.assertTrue(matcher.ignores("dir/keep.txt"))
        self.assertFalse(matcher.ignores("other/dir/keep.txt"))


class TestNegationSemantics(unittest.TestCase):
    """差异二：ignores() 必须把 `!` 规则判为“不忽略”。

    为什么：`!` 是否定前缀，命中的 `!` 规则表达“重新包含”，
    取最后命中规则时 ignores 的结论必须是 not negated。迁移时
    结论被整个写反（negated 为真反而返回 True），普通忽略与
    重新包含全部颠倒，命中数归零。
    """

    def test_negated_rule_means_reinclude(self):
        matcher = Matcher(["*.txt", "!keep.txt"])
        self.assertTrue(matcher.ignores("a.txt"))
        self.assertFalse(matcher.ignores("keep.txt"))
        self.assertTrue(matcher.match("keep.txt").negated)

    def test_negation_without_prior_rule_matches_but_not_ignored(self):
        matcher = Matcher(["!foo.txt"])
        matched = matcher.match("foo.txt")
        self.assertIsNotNone(matched)
        self.assertTrue(matched.negated)
        self.assertFalse(matcher.ignores("foo.txt"))

    def test_last_match_wins_including_reinclude(self):
        matcher = Matcher(["*.txt", "!a.txt", "keep.txt"])
        self.assertFalse(matcher.ignores("a.txt"))
        self.assertTrue(matcher.ignores("keep.txt"))


class TestThreeEntriesAgree(unittest.TestCase):
    """同一条规则、同一路径，三个入口的结论必须一致。

    为什么：Pattern.matches 走正则，Matcher.match/ignores 走
    “字面量分桶 + 通配符正则”两套路径，任何一处键值或布尔
    语义对不上，灰度对照都会出现“单测过、链路错”。
    """

    def assert_three_entries_agree(self, rules, path, is_dir=False):
        expected = [
            compile_pattern(rule).matches(path, is_dir=is_dir)
            if isinstance(rule, str) else rule.matches(path, is_dir=is_dir)
            for rule in rules
        ]
        matcher = Matcher(rules)
        hit_by_any = any(expected)
        matched = matcher.match(path, is_dir=is_dir)
        self.assertEqual(
            matched is not None, hit_by_any,
            f"Matcher.match 与 Pattern.matches 不一致：{rules!r} vs {path!r}",
        )
        self.assertEqual(
            matcher.ignores(path, is_dir=is_dir),
            hit_by_any and not matcher.match(path, is_dir=is_dir).negated
            if hit_by_any else False,
            f"ignores 与 match 语义不一致：{rules!r} vs {path!r}",
        )

    def test_escaped_literal_rules_agree(self):
        # 转义规则是纯字面量，桶键必须是“反转义后”的文本
        for pattern, path in [
            (r"a\*b", "a*b"),
            (r"a\ b", "a b"),
            (r"a\?b", "a?b"),
            (r"a\[b\]c", "a[b]c"),
            (r"\!important", "!important"),
            (r"\#hash", "#hash"),
        ]:
            with self.subTest(pattern=pattern, path=path):
                self.assert_three_entries_agree([pattern], path)

    def test_negated_and_anchored_rules_agree(self):
        cases = [
            (["*.txt", "!keep.txt"], "keep.txt"),
            (["doc/*.md", "!doc/note.md"], "doc/note.md"),
            (["dir/keep.txt"], "x/dir/keep.txt"),
        ]
        for rules, path in cases:
            with self.subTest(rules=rules, path=path):
                self.assert_three_entries_agree(rules, path)

    def test_normalize_contract_still_holds(self):
        self.assertEqual(normalize_path("./a//b/"), "a/b")
        for bad in ("/abs", "C:/x", "a/../b", ""):
            with self.subTest(bad=bad):
                from pathglob.errors import PathError
                with self.assertRaises(PathError):
                    normalize_path(bad)


class TestLiteralBucketPerfRegression(unittest.TestCase):
    """差异的性能护栏：字面量规则必须始终走分桶快查。

    为什么：修复中间斜杠锚定后，形如 `cache/dir/file.tmp` 的
    规则被正确判为锚定并进入完整路径桶；要保证它们不会退化成
    逐条正则扫描，500×50 批处理用例的时间承诺才不被破坏。
    """

    def test_literal_rules_go_to_buckets_not_wild_scan(self):
        rules = [f"cache/dir{i}/file{i}.tmp" for i in range(300)]
        matcher = Matcher(rules)
        self.assertEqual(len(matcher._wild), 0)
        self.assertEqual(len(matcher._abs_file), 300)
        self.assertTrue(matcher.ignores("cache/dir123/file123.tmp"))
        self.assertFalse(matcher.ignores("else/cache/dir123/file123.tmp"))

    def test_deep_path_under_double_star_still_fast(self):
        # 4096 字符深层路径 + `**/` 规则：既不能因锚定漏配，
        # 也不能出现指数级回溯。
        deep = "/".join(["d"] * 2047 + ["end.txt"])
        self.assertGreaterEqual(len(deep), 4096)
        self.assertTrue(compile_pattern("**/end.txt").matches(deep))
        start = time.perf_counter()
        hits = sum(
            Matcher(["d/**/end.txt", "!d/d/end.txt"]).ignores(deep)
            for _ in range(20)
        )
        self.assertLess(time.perf_counter() - start, 1.0)
        self.assertEqual(hits, 20)


if __name__ == "__main__":
    unittest.main()
