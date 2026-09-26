"""textdiff 的标准库 unittest 测试。"""

import difflib
import random
import unittest

import textdiff
from textdiff import merge as merge_mod
from textdiff import myers
from textdiff.errors import PatchError


def lines(text):
    return myers.split_lines(text)


class LineSplitTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(lines(""), [])

    def test_single_line_with_newline(self):
        self.assertEqual(lines("abc\n"), [myers.Line("abc", "\n")])

    def test_single_line_no_newline(self):
        self.assertEqual(lines("abc"), [myers.Line("abc", "")])

    def test_crlf_mix_does_not_swallow_or_attach_cr(self):
        result = lines("a\r\nb\nc\rd")
        self.assertEqual(
            result,
            [myers.Line("a", "\r\n"), myers.Line("b", "\n"),
             myers.Line("c", "\r"), myers.Line("d", "")])
        # 每个 \r 都必须属于行终止符，绝不能混进文本内容。
        self.assertTrue(all("\r" not in line.text for line in result))

    def test_join_roundtrip(self):
        for text in ("", "a", "a\n", "a\r\n", "a\nb\r\nc", "\n\n\n"):
            self.assertEqual(myers.join_lines(lines(text)), text)


class DiffTests(unittest.TestCase):
    def test_identical_is_one_equal_block(self):
        edits = textdiff.diff("a\nb\n", "a\nb\n")
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].tag, "equal")

    def test_common_prefix_and_suffix_are_merged(self):
        a = "h1\nh2\nmid1\nmid2\nt1\nt2\n"
        b = "h1\nh2\nNEW\nt1\nt2\n"
        edits = textdiff.diff(a, b)
        tags = [edit.tag for edit in edits]
        self.assertEqual(tags, ["equal", "replace", "equal"])
        # 前缀两行、后缀两行都被归并进单个 equal 块。
        self.assertEqual((edits[0].a_start, edits[0].a_end), (0, 2))
        self.assertEqual((edits[2].a_start, edits[2].a_end), (4, 6))

    def test_delete_insert_ordering_and_tags(self):
        edits = textdiff.diff("x\n", "y\n")
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].tag, "replace")
        pure_del = textdiff.diff("a\nb\n", "a\n")
        self.assertIn("delete", [e.tag for e in pure_del])
        pure_ins = textdiff.diff("a\n", "a\nb\n")
        self.assertIn("insert", [e.tag for e in pure_ins])

    def test_edits_partition_both_inputs(self):
        a = "one\ntwo\nthree\nfour\n"
        b = "one\nTWO\nthree\nfour\nfive\n"
        la, lb = lines(a), lines(b)
        aa = bb = 0
        for edit in textdiff.diff(a, b):
            self.assertEqual((edit.a_start, edit.b_start), (aa, bb))
            aa, bb = edit.a_end, edit.b_end
        self.assertEqual((aa, bb), (len(la), len(lb)))

    def test_deterministic_across_calls(self):
        a = "\n".join(["r"] * 50 + ["x"] + ["r"] * 50) + "\n"
        b = "\n".join(["r"] * 50 + ["y"] + ["r"] * 50) + "\n"
        first = textdiff.unified(a, b)
        for _ in range(5):
            self.assertEqual(textdiff.unified(a, b), first)

    def test_repeated_lines_are_handled(self):
        a = "".join("dup\n" for _ in range(300))
        b = "".join("dup\n" for _ in range(150)) + \
            "NEW\n" + "".join("dup\n" for _ in range(149))
        self.assertEqual(textdiff.apply(a, textdiff.unified(a, b)), b)

    def test_empty_to_text_and_text_to_empty(self):
        self.assertEqual(textdiff.apply("", textdiff.unified("", "x\n")), "x\n")
        self.assertEqual(textdiff.apply("x\n", textdiff.unified("x\n", "")), "")


class UnifiedHeaderTests(unittest.TestCase):
    def test_header_and_hunk_numbers_basic(self):
        a = "".join(f"l{i}\n" for i in range(1, 11))
        b = a.replace("l5\n", "L5\n")
        patch = textdiff.unified(a, b, context=2)
        self.assertTrue(patch.startswith("--- a\n+++ b\n"))
        self.assertIn("@@ -3,5 +3,5 @@", patch)

    def test_insert_at_head_uses_zero_start_for_old_side(self):
        patch = textdiff.unified("a\n", "n\na\n", context=0)
        self.assertIn("@@ -0,0 +1 @@", patch)

    def test_delete_to_empty_old_side(self):
        patch = textdiff.unified("a\n", "", context=0)
        self.assertIn("@@ -1 +0,0 @@", patch)

    def test_identical_inputs_produce_empty_patch(self):
        self.assertEqual(textdiff.unified("a\n", "a\n"), "")

    def test_no_newline_marker_on_both_sides(self):
        patch = textdiff.unified("a\nb", "a\nB")
        self.assertIn("\\ No newline at end of file", patch)
        # 被修改行（-b / +B）以及保留的无结束行（a）都应被正确处理。
        self.assertEqual(textdiff.apply("a\nb", patch), "a\nB")

    def test_long_context_separates_hunks(self):
        a = "".join(f"l{i}\n" for i in range(20))
        b = a.replace("l0\n", "X\n", 1).replace("l19\n", "Y\n", 1)
        patch = textdiff.unified(a, b, context=1)
        self.assertEqual(patch.count("@@ -"), 2)


class UnifiedOrderingTests(unittest.TestCase):
    """改动块内「先删后插」的渲染顺序约定（交错回归）。"""

    def test_replace_block_renders_all_deletes_before_inserts(self):
        # 回归：同一替换块曾把 - / + 交错输出（-u3 +mod4 -u4）。
        a = "u0\nu1\nu2\nu3-755\nu4-568\nu5\n"
        b = "u0\nu1\nu2\nmod4-360\nu5\n"
        patch = textdiff.unified(a, b, 0)
        self.assertEqual(
            patch,
            "--- a\n+++ b\n"
            "@@ -4,2 +4 @@\n"
            "-u3-755\n"
            "-u4-568\n"
            "+mod4-360\n")

    def test_change_blocks_keep_document_order(self):
        # 不同改动块之间仍按文档顺序排列，各自内部先删后插。
        a = "a1\na2\nkeep\nb1\nb2\n"
        b = "A\nkeep\nB\n"
        patch = textdiff.unified(a, b, 0)
        self.assertEqual(
            patch,
            "--- a\n+++ b\n"
            "@@ -1,2 +1 @@\n"
            "-a1\n"
            "-a2\n"
            "+A\n"
            "@@ -4,2 +3 @@\n"
            "-b1\n"
            "-b2\n"
            "+B\n")

    def test_byte_identical_with_difflib_on_unique_lines(self):
        # 唯一行文本上逐字节对齐 difflib.unified_diff，随机 1000 组。
        rng = random.Random(20260924)
        stamp = [0]

        def fresh(tag):
            stamp[0] += 1
            return f"{tag}{stamp[0]}"

        for _ in range(1000):
            a_lines = [fresh("u") for _ in range(rng.randint(0, 12))]
            b_lines = list(a_lines)
            for _ in range(rng.randint(1, 4)):
                op = rng.choice(("replace", "insert", "delete"))
                if op == "replace" and b_lines:
                    b_lines[rng.randrange(len(b_lines))] = fresh("mod")
                elif op == "insert":
                    b_lines.insert(rng.randrange(len(b_lines) + 1),
                                   fresh("ins"))
                elif op == "delete" and b_lines:
                    del b_lines[rng.randrange(len(b_lines))]
            a = "".join(x + "\n" for x in a_lines)
            b = "".join(x + "\n" for x in b_lines)
            for context in (0, 1, 3, 5):
                expected = "".join(difflib.unified_diff(
                    a.splitlines(keepends=True),
                    b.splitlines(keepends=True),
                    fromfile="a", tofile="b", n=context))
                patch = textdiff.unified(a, b, context)
                self.assertEqual(patch, expected,
                                 msg=(a, b, context))
                self.assertEqual(textdiff.apply(a, patch), b)

    def test_empty_file_cases(self):
        self.assertEqual(textdiff.unified("", ""), "")
        patch = textdiff.unified("", "only\n")
        self.assertEqual(patch,
                         "--- a\n+++ b\n@@ -0,0 +1 @@\n+only\n")
        self.assertEqual(textdiff.apply("", patch), "only\n")

    def test_pure_insert_and_pure_delete(self):
        patch = textdiff.unified("a\nc\n", "a\nx\ny\nc\n", 0)
        self.assertEqual(patch,
                         "--- a\n+++ b\n@@ -1,0 +2,2 @@\n+x\n+y\n")
        patch = textdiff.unified("a\nx\ny\nc\n", "a\nc\n", 0)
        self.assertEqual(patch,
                         "--- a\n+++ b\n@@ -2,2 +1,0 @@\n-x\n-y\n")

    def test_no_trailing_newline_keeps_marker_and_order(self):
        patch = textdiff.unified("a\nb1\nb2", "a\nB", 0)
        self.assertEqual(
            patch,
            "--- a\n+++ b\n"
            "@@ -2,2 +2 @@\n"
            "-b1\n"
            "-b2\n"
            "\\ No newline at end of file\n"
            "+B\n"
            "\\ No newline at end of file\n")
        self.assertEqual(textdiff.apply("a\nb1\nb2", patch), "a\nB")

    def test_crlf_lines_render_delete_before_insert(self):
        patch = textdiff.unified("a\r\nb1\r\nb2\r\n", "a\r\nB\r\n", 0)
        self.assertEqual(
            patch,
            "--- a\n+++ b\n"
            "@@ -2,2 +2 @@\n"
            "-b1\r\n"
            "-b2\r\n"
            "+B\r\n")
        self.assertEqual(
            textdiff.apply("a\r\nb1\r\nb2\r\n", patch), "a\r\nB\r\n")


class HunkMergeBoundaryTests(unittest.TestCase):
    """hunk 合并边界：间隔公共行 <= 2*context 合并，>= 2*context+1 拆开。"""

    @staticmethod
    def _make_pair(gap, context):
        # 两处单行替换，中间夹 gap 行公共上下文，两端再各留 context 行。
        pad = [f"p{i}" for i in range(context)]
        mid = [f"m{i}" for i in range(gap)]
        a_rows = pad + ["X1"] + mid + ["X2"] + pad
        b_rows = pad + ["Y1"] + mid + ["Y2"] + pad
        a = "".join(row + "\n" for row in a_rows)
        b = "".join(row + "\n" for row in b_rows)
        return a, b

    def test_gap_exactly_2x_context_merges_into_one_hunk(self):
        # 回归：间隔正好 2*context 行公共上下文时必须合并为一个 hunk。
        for context in (0, 1, 3, 5):
            a, b = self._make_pair(2 * context, context)
            patch = textdiff.unified(a, b, context)
            self.assertEqual(patch.count("@@ -"), 1, msg=context)
            self.assertEqual(textdiff.apply(a, patch), b)

    def test_gap_2x_context_plus_one_splits_into_two_hunks(self):
        # 边界另一侧：间隔 2*context+1 行公共上下文时必须拆开。
        for context in (0, 1, 3, 5):
            a, b = self._make_pair(2 * context + 1, context)
            patch = textdiff.unified(a, b, context)
            self.assertEqual(patch.count("@@ -"), 2, msg=context)
            self.assertEqual(textdiff.apply(a, patch), b)


class ApplyTests(unittest.TestCase):
    def test_roundtrip_varied_contexts(self):
        cases = [
            ("", "x\n"),
            ("x\n", ""),
            ("a\nb\nc\n", "a\nB\nc\n"),
            ("a\r\nb\r\n", "a\r\nB\r\n"),
            ("a\nb\n", "a\r\nb\r\n"),
            ("only", "only changed"),
            ("x\ny\nz\n", "x\nz\n"),
        ]
        for a, b in cases:
            for context in (0, 1, 3, 5):
                self.assertEqual(textdiff.apply(a, textdiff.unified(a, b, context)),
                                 b, msg=(a, b, context))

    def test_empty_patch_returns_original(self):
        self.assertEqual(textdiff.apply("anything\n", ""), "anything\n")

    def test_context_mismatch_raises_with_details(self):
        a = "a\nb\nc\n"
        patch = textdiff.unified(a, "a\nX\nc\n")
        # 篡改 hunk 中保留的上下文行 c（它两侧都在 hunk 内，无法位移规避）。
        broken = patch.replace(" c\n", " Z\n", 1)
        with self.assertRaises(PatchError) as caught:
            textdiff.apply(a, broken)
        self.assertEqual(caught.exception.hunk_index, 1)
        self.assertIsNotNone(caught.exception.expected)
        self.assertIsNotNone(caught.exception.actual)
        self.assertEqual(caught.exception.actual, "c\n")

    def test_hunk_line_out_of_range_raises(self):
        patch = "--- a\n+++ b\n@@ -10 +10 @@\n-x\n+y\n"
        with self.assertRaises(PatchError) as caught:
            textdiff.apply("z\n", patch)
        self.assertEqual(caught.exception.hunk_index, 1)
        self.assertEqual(caught.exception.line_no, 10)

    def test_malformed_patch_raises(self):
        with self.assertRaises(PatchError):
            textdiff.apply("a\n", "not a patch")

    def test_count_mismatch_in_header_raises(self):
        patch = ("--- a\n+++ b\n@@ -1,9 +1,1 @@\n a\n")
        with self.assertRaises(PatchError):
            textdiff.apply("a\n", patch)


class MergeTests(unittest.TestCase):
    BASE = "1\n2\n3\n4\n5\n"

    def test_single_side_changes_auto_apply(self):
        result = textdiff.merge(self.BASE,
                                "1\n2\nO\n4\n5\n",
                                "1\n2\n3\n4\nT\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.merged, "1\n2\nO\n4\nT\n")

    def test_both_sides_identical_change_no_conflict(self):
        result = textdiff.merge(self.BASE,
                                "1\n2\nX\n4\n5\n",
                                "1\n2\nX\n4\n5\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.merged, "1\n2\nX\n4\n5\n")

    def test_conflicting_changes_emit_markers_and_conflict_block(self):
        result = textdiff.merge(self.BASE,
                                "1\n2\nA\n4\n5\n",
                                "1\n2\nB\n4\n5\n")
        self.assertTrue(result.has_conflicts)
        self.assertEqual(len(result.conflicts), 1)
        conflict = result.conflicts[0]
        self.assertEqual((conflict.base_start, conflict.base_end), (3, 4))
        self.assertEqual(conflict.ours_lines, ["A\n"])
        self.assertEqual(conflict.theirs_lines, ["B\n"])
        self.assertIn("<<<<<<< ours", result.merged)
        self.assertIn("=======", result.merged)
        self.assertIn(">>>>>>> theirs", result.merged)
        self.assertEqual(conflict.source, "ours vs theirs")

    def test_same_point_insert_conflict_location(self):
        result = textdiff.merge("a\nb\n", "a\nI\nb\n", "a\nJ\nb\n")
        self.assertTrue(result.has_conflicts)
        conflict = result.conflicts[0]
        self.assertEqual((conflict.base_start, conflict.base_end), (1, 1))

    def test_non_overlapping_inserts_merge_cleanly(self):
        result = textdiff.merge("a\nb\n", "a\n1\nb\n", "a\nb\n2\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.merged, "a\n1\nb\n2\n")

    def test_changes_on_adjacent_lines_merge_cleanly(self):
        # ours 改第 2 行、theirs 改第 3 行：区间只在边界相接，不算冲突。
        result = textdiff.merge("1\n2\n3\n",
                                "1\nO\n3\n",
                                "1\n2\nT\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.merged, "1\nO\nT\n")

    def test_inserts_at_different_adjacent_points_merge_cleanly(self):
        result = textdiff.merge("a\nb\nc\n",
                                "a\nI\nb\nc\n",
                                "a\nb\nJ\nc\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.merged, "a\nI\nb\nJ\nc\n")

    def test_both_delete_same_line_is_consistent(self):
        result = textdiff.merge("a\nb\nc\n", "a\nc\n", "a\nc\n")
        self.assertFalse(result.has_conflicts)
        self.assertEqual(result.merged, "a\nc\n")

    def test_delete_vs_modify_is_conflict(self):
        result = textdiff.merge("a\nb\nc\n", "a\nc\n", "a\nB\nc\n")
        self.assertTrue(result.has_conflicts)
        self.assertEqual(len(result.conflicts), 1)

    def test_multiple_distinct_conflicts_count_and_content(self):
        base = "a\nb\nc\nd\ne\n"
        ours = "a\nB1\nc\nD1\ne\n"
        theirs = "a\nB2\nc\nD2\ne\n"
        result = textdiff.merge(base, ours, theirs)
        # 两个冲突点间隔一行公共行 c，应产出两个独立冲突块。
        self.assertEqual(len(result.conflicts), 2)
        self.assertEqual(result.conflicts[0].ours_lines, ["B1\n"])
        self.assertEqual(result.conflicts[1].theirs_lines, ["D2\n"])
        self.assertEqual(result.merged.count("<<<<<<<"), 2)

    def test_conflict_range_is_one_based_half_open_over_base(self):
        # 回归：base_start/base_end 为 1 基半开区间，按它切 base 原文
        # 正好得到冲突覆盖的祖先行。
        base = "1\n2\n3\n4\n5\n"
        result = textdiff.merge(base, "1\n2\nA\n4\n5\n", "1\n2\nB\n4\n5\n")
        conflict = result.conflicts[0]
        base_rows = base.splitlines(keepends=True)
        covered = base_rows[conflict.base_start - 1:conflict.base_end - 1]
        self.assertEqual(covered, ["3\n"])

        # 删除 vs 修改的冲突同样覆盖被改动的祖先行区间。
        result = textdiff.merge("a\nb\nc\n", "a\nc\n", "a\nB\nc\n")
        conflict = result.conflicts[0]
        base_rows = "a\nb\nc\n".splitlines(keepends=True)
        covered = base_rows[conflict.base_start - 1:conflict.base_end - 1]
        self.assertEqual(covered, ["b\n"])

    def test_pure_insert_conflict_range_slices_to_empty(self):
        # 纯插入冲突：lo == hi 为插入点，按区间切片为空。
        base = "a\nb\n"
        result = textdiff.merge(base, "a\nI\nb\n", "a\nJ\nb\n")
        conflict = result.conflicts[0]
        base_rows = base.splitlines(keepends=True)
        covered = base_rows[conflict.base_start - 1:conflict.base_end - 1]
        self.assertEqual(covered, [])


class RandomRoundTripTests(unittest.TestCase):
    def test_randomized_roundtrip_and_shortest(self):
        rng = random.Random(2026)

        def lcs_len(a, b):
            n, m = len(a), len(b)
            prev = [0] * (m + 1)
            for i in range(n):
                cur = [0] * (m + 1)
                for j in range(m):
                    cur[j + 1] = (prev[j] + 1 if a[i] == b[j]
                                  else max(prev[j + 1], cur[j]))
                prev = cur
            return prev[m]

        for _ in range(120):
            a_lines = [rng.choice("ab") for _ in range(rng.randint(0, 20))]
            b_lines = [rng.choice("ab") for _ in range(rng.randint(0, 20))]
            a = "".join(x + "\n" for x in a_lines)
            b = "".join(x + "\n" for x in b_lines)
            la, lb = lines(a), lines(b)
            distance = sum(
                (edit.a_end - edit.a_start) + (edit.b_end - edit.b_start)
                for edit in textdiff.diff(a, b) if edit.tag != "equal")
            self.assertEqual(distance,
                             len(la) + len(lb) - 2 * lcs_len(la, lb))
            for context in (0, 2, 3):
                self.assertEqual(
                    textdiff.apply(a, textdiff.unified(a, b, context)), b)


if __name__ == "__main__":
    unittest.main()
