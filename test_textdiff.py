"""textdiff 的标准库 unittest 测试。"""

import unittest

import textdiff
from textdiff import apply, diff, merge, unified
from textdiff.errors import PatchError
from textdiff.myers import Line, join_lines, split_lines


def _reconstruct_b(edits):
    """用编辑脚本拼出新文件，验证脚本自洽。"""
    lines = []
    for edit in edits:
        if edit.op in ("equal", "insert", "replace"):
            lines.extend(edit.lines_b)
    return join_lines(lines)


def _reconstruct_a(edits):
    lines = []
    for edit in edits:
        if edit.op in ("equal", "delete", "replace"):
            lines.extend(edit.lines_a)
    return join_lines(lines)


class SplitJoinTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(split_lines(""), [])
        self.assertEqual(join_lines([]), "")

    def test_no_final_newline(self):
        self.assertEqual(split_lines("abc"), [Line("abc", "")])
        self.assertEqual(join_lines(split_lines("abc")), "abc")

    def test_crlf_and_lf_mixed(self):
        text = "a\r\nb\nc\r\nd"
        lines = split_lines(text)
        self.assertEqual(
            lines,
            [Line("a", "\r\n"), Line("b", "\n"), Line("c", "\r\n"), Line("d", "")],
        )
        self.assertEqual(join_lines(lines), text)

    def test_lone_cr_is_content(self):
        # 单独的 \r 不被当成行尾，也不被吞掉
        self.assertEqual(split_lines("a\rb\n"), [Line("a\rb", "\n")])

    def test_roundtrip_many(self):
        for text in ["\n", "\n\n", "\r\n", "x", "x\n\n", "a\r\n\r\nb"]:
            self.assertEqual(join_lines(split_lines(text)), text)


class DiffTest(unittest.TestCase):
    def test_both_empty(self):
        self.assertEqual(diff("", ""), [])

    def test_delete_to_empty_and_insert_from_empty(self):
        edits = diff("a\nb\n", "")
        self.assertEqual([e.op for e in edits], ["delete"])
        self.assertEqual(_reconstruct_a(edits), "a\nb\n")
        edits = diff("", "a\nb\n")
        self.assertEqual([e.op for e in edits], ["insert"])
        self.assertEqual(_reconstruct_b(edits), "a\nb\n")

    def test_common_prefix_suffix_merged(self):
        a = "h1\nh2\nh3\nold1\nold2\nt1\nt2\n"
        b = "h1\nh2\nh3\nnew\nt1\nt2\n"
        edits = diff(a, b)
        self.assertEqual([e.op for e in edits], ["equal", "replace", "equal"])
        self.assertEqual(_reconstruct_b(edits), b)
        self.assertEqual(_reconstruct_a(edits), a)

    def test_delete_before_insert(self):
        # 删除一行、在同区域插入一行时，删除必须排在插入之前（或合并为 replace）
        a = "1\n2\n3\n"
        b = "1\nX\n3\n"
        edits = diff(a, b)
        ops = [e.op for e in edits]
        self.assertEqual(ops, ["equal", "replace", "equal"])

    def test_separate_delete_and_insert_order(self):
        # 删除点在插入点之前：delete 段排在前
        a = "a\nb\nc\nd\n"
        b = "a\nc\nd\ne\n"
        edits = diff(a, b)
        self.assertEqual([e.op for e in edits].count("delete"), 1)
        self.assertEqual([e.op for e in edits].count("insert"), 1)
        ops = [e.op for e in edits if e.op in ("delete", "insert", "replace")]
        self.assertEqual([op for op in ops if op in ("delete", "insert")],
                         ["delete", "insert"])
        self.assertEqual(_reconstruct_b(edits), b)

    def test_identical_single_equal(self):
        edits = diff("a\nb\n", "a\nb\n")
        self.assertEqual([e.op for e in edits], ["equal"])

    def test_repeated_lines(self):
        # 大量重复行：脚本必须最短且确定
        a = ("x\n" * 100 + "y\n" + "x\n" * 100)
        b = "x\n" * 201
        edits1 = diff(a, b)
        edits2 = diff(a, b)
        self.assertEqual(edits1, edits2)
        self.assertEqual(_reconstruct_b(edits1), b)
        self.assertEqual(_reconstruct_a(edits1), a)

    def test_deterministic(self):
        a = "\n".join(str(i % 7) for i in range(500))
        b = "\n".join(str(i % 5) for i in range(520))
        self.assertEqual(diff(a, b), diff(a, b))

    def test_shortest_against_lcs(self):
        # 用独立的 O(N*M) LCS 核对最短脚本长度：
        # Myers 脚本长度 = 插入数 + 删除数 = n + m - 2*LCS（替换算两步）。
        def edit_distance(a_lines, b_lines):
            n, m = len(a_lines), len(b_lines)
            dp = [[0] * (m + 1) for _ in range(n + 1)]
            for i in range(1, n + 1):
                for j in range(1, m + 1):
                    if a_lines[i - 1] == b_lines[j - 1]:
                        dp[i][j] = dp[i - 1][j - 1] + 1
                    else:
                        dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
            return n + m - 2 * dp[n][m]

        samples = [
            ("a\nb\nc\n", "x\nb\nc\ny\n"),
            ("1\n2\n3\n4\n", "1\n9\n3\n8\n4\n"),
            ("\n".join("ab"), "\n".join("ba")),
            ("", "q\n"),
        ]
        for a, b in samples:
            al, bl = split_lines(a), split_lines(b)
            edits = diff(a, b)
            script_len = sum(
                len(e.lines_a) + len(e.lines_b)
                for e in edits
                if e.op in ("delete", "insert", "replace")
            )
            self.assertEqual(script_len, edit_distance(al, bl), (a, b))

    def test_crlf_change_is_detected(self):
        # 行内容相同但行尾不同必须算差异，且可还原
        edits = diff("a\nb\n", "a\r\nb\r\n")
        self.assertEqual(_reconstruct_b(edits), "a\r\nb\r\n")


class UnifiedTest(unittest.TestCase):
    def test_identical_returns_empty(self):
        self.assertEqual(unified("a\n", "a\n"), "")

    def test_header_and_hunk_line_numbers(self):
        a = "".join(f"line{i}\n" for i in range(1, 11))
        b = "".join("line5-CHANGED\n" if i == 5 else f"line{i}\n" for i in range(1, 11))
        text = unified(a, b, context=3)
        self.assertTrue(text.startswith("--- a\n+++ b\n"))
        self.assertIn("@@ -2,7 +2,7 @@", text)

    def test_empty_file_insert_header(self):
        text = unified("", "x\n")
        self.assertIn("@@ -0,0 +1 @@", text)
        self.assertIn("+x\n", text)

    def test_delete_whole_file_header(self):
        text = unified("x\ny\n", "")
        self.assertIn("@@ -1,2 +0,0 @@", text)

    def test_no_newline_marker(self):
        text = unified("a\nb", "a\nB")
        self.assertIn("\\ No newline at end of file\n", text)

    def test_context_one_merges_nearby_hunks(self):
        a = "".join(f"{i}\n" for i in range(1, 11))
        b = a.replace("2\n", "TWO\n").replace("8\n", "EIGHT\n")
        text = unified(a, b, context=3)
        # 两处改动距离 6 行，context=3 时合并成一个 hunk
        self.assertEqual(text.count("@@ "), 1)
        text1 = unified(a, b, context=1)
        self.assertEqual(text1.count("@@ "), 2)


class ApplyTest(unittest.TestCase):
    def _roundtrip(self, a, b):
        self.assertEqual(apply(a, unified(a, b)), b)

    def test_roundtrip_basic(self):
        self._roundtrip("a\nb\nc\n", "a\nB\nc\n")

    def test_roundtrip_empty_cases(self):
        self._roundtrip("", "x\n")
        self._roundtrip("x\n", "")
        self._roundtrip("", "")
        self._roundtrip("only", "only2")

    def test_roundtrip_no_newline(self):
        self._roundtrip("a\nb", "a\nB")
        self._roundtrip("a\nb\n", "a\nb")
        self._roundtrip("a\nb", "a\nb\n")

    def test_roundtrip_crlf(self):
        self._roundtrip("a\r\nb\r\n", "a\r\nB\r\n")
        self._roundtrip("a\r\nb\n", "a\r\nb\r\n")

    def test_roundtrip_multi_hunk(self):
        a = "".join(f"line{i}\n" for i in range(1, 51))
        b = a.replace("line5\n", "FIVE\n").replace("line40\n", "FORTY\n")
        self._roundtrip(a, b)

    def test_context_mismatch_raises(self):
        patch = unified("a\nb\nc\n", "a\nX\nc\n")
        with self.assertRaises(PatchError) as cm:
            apply("a\nZZ\nc\n", patch)
        message = str(cm.exception)
        self.assertIn("1", message)  # hunk 序号
        self.assertIn("期望", message)
        self.assertIn("实际", message)

    def test_out_of_range_raises(self):
        patch = unified("a\nb\nc\n", "a\nX\nc\n")
        with self.assertRaises(PatchError):
            apply("a\n", patch)

    def test_malformed_patch_raises(self):
        with self.assertRaises(PatchError):
            apply("a\n", "这不是一个补丁\n")
        with self.assertRaises(PatchError):
            apply("a\n", "--- a\n+++ b\n@@ -1 +1 @@\n?bad\n")

    def test_empty_patch_is_noop(self):
        self.assertEqual(apply("a\nb\n", ""), "a\nb\n")

    def test_does_not_guess_wrong_offset(self):
        # 声明行号错位：绝不允许"找个差不多的位置"套用
        patch = "--- a\n+++ b\n@@ -2,1 +2,1 @@\n-b\n+B\n"
        # 第 2 行确实是 b：严格按声明行号套用，正常成立
        ok = apply("a\nb\n", patch)
        self.assertEqual(ok, "a\nB\n")
        ok = apply("x\nb\n", patch)
        self.assertEqual(ok, "x\nB\n")
        with self.assertRaises(PatchError):
            apply("b\nx\n", patch)  # 第 2 行不是 b


class MergeTest(unittest.TestCase):
    def test_one_side_change(self):
        result = merge("a\nb\nc\n", "a\nB\nc\n", "a\nb\nc\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.text, "a\nB\nc\n")
        self.assertEqual(result.conflicts, ())

    def test_disjoint_changes_merge_cleanly(self):
        result = merge("a\nb\nc\n", "X\nb\nc\n", "a\nb\nY\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.text, "X\nb\nY\n")

    def test_both_same_change_no_conflict(self):
        result = merge("a\nb\n", "a\nB\n", "a\nB\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.text, "a\nB\n")

    def test_both_same_insert_no_conflict_and_no_duplicate(self):
        result = merge("a\nb\n", "a\nNEW\nb\n", "a\nNEW\nb\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.text, "a\nNEW\nb\n")

    def test_conflict_markers_and_block(self):
        result = merge("a\nb\nc\n", "a\nOURS\nc\n", "a\nTHEIRS\nc\n")
        self.assertTrue(result.has_conflicts)
        self.assertIn("<<<<<<< ours\n", result.text)
        self.assertIn("=======\n", result.text)
        self.assertIn(">>>>>>> theirs\n", result.text)
        self.assertEqual(len(result.conflicts), 1)
        block = result.conflicts[0]
        self.assertEqual((block.base_start, block.base_end), (1, 2))
        self.assertEqual(block.ours_text, "OURS\n")
        self.assertEqual(block.theirs_text, "THEIRS\n")

    def test_conflict_at_same_insert_point(self):
        result = merge("a\nb\n", "a\nI1\nb\n", "a\nI2\nb\n")
        self.assertTrue(result.has_conflicts)
        block = result.conflicts[0]
        self.assertEqual(block.base_start, block.base_end)  # 纯插入：空区间
        self.assertEqual(block.base_start, 1)

    def test_conflict_block_count_for_two_regions(self):
        base = "a\nb\nc\nd\ne\n"
        ours = "A\nb\nc\nd\nE\n"
        theirs = "a2\nb\nc\nd\ne2\n"
        result = merge(base, ours, theirs)
        # 两个互不相邻的区域各自冲突
        self.assertEqual(len(result.conflicts), 2)

    def test_insert_adjacent_to_replace_conflicts(self):
        # 一侧在区域开头插入，另一侧替换该区域首行：触碰同一处，应报冲突
        base = "a\nb\nc\n"
        ours = "INS\na\nb\nc\n"
        theirs = "A\nb\nc\n"
        result = merge(base, ours, theirs)
        self.assertTrue(result.has_conflicts)
        # 交换两侧，结论必须对称
        swapped = merge(base, theirs, ours)
        self.assertTrue(swapped.has_conflicts)

    def test_merge_without_final_newline(self):
        result = merge("a\nb", "a\nB", "a\nb")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.text, "a\nB")

    def test_merge_empty_base(self):
        result = merge("", "x\n", "y\n")
        self.assertTrue(result.has_conflicts)
        self.assertEqual(result.conflicts[0].base_start, 0)

    def test_no_changes(self):
        result = merge("a\nb\n", "a\nb\n", "a\nb\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.text, "a\nb\n")


if __name__ == "__main__":
    unittest.main()
