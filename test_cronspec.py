"""cronspec 的 unittest 测试套件（仅使用标准库）。"""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timezone

from cronspec import Schedule, describe, parse
from cronspec.errors import NoMatchingTimeError, ScheduleSyntaxError


def dt(year, month=1, day=1, hour=0, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second)


class ParseTests(unittest.TestCase):
    def test_five_fields_and_shapes(self):
        s = parse("* * * * *")
        self.assertEqual(s.minute.values, tuple(range(60)))
        self.assertEqual(s.hour.values, tuple(range(24)))
        self.assertEqual(s.dom.values, tuple(range(1, 32)))
        self.assertEqual(s.month.values, tuple(range(1, 13)))
        self.assertEqual(s.dow.values, tuple(range(7)))

    def test_shortcuts(self):
        cases = {
            "@yearly": ("0", "0", "1", "1", "*"),
            "@annually": ("0", "0", "1", "1", "*"),
            "@monthly": ("0", "0", "1", "*", "*"),
            "@weekly": ("0", "0", "*", "*", "0"),
            "@daily": ("0", "0", "*", "*", "*"),
            "@midnight": ("0", "0", "*", "*", "*"),
            "@hourly": ("0", "*", "*", "*", "*"),
        }
        for shortcut, fields in cases.items():
            shortcut_sched = parse(shortcut)
            plain_sched = parse(" ".join(fields))
            for attr in ("minute", "hour", "dom", "month", "dow"):
                self.assertEqual(
                    getattr(shortcut_sched, attr).values,
                    getattr(plain_sched, attr).values,
                    f"{shortcut} 与 {' '.join(fields)} 应等价（{attr}）",
                )

    def test_whitespace_separators(self):
        s1 = parse("0\t0 1 1 *")
        s2 = parse("  0   0\t\t1    1  *  ")
        self.assertEqual(s1.minute.values, s2.minute.values)
        self.assertEqual(s1.dom.values, s2.dom.values)

    def test_ranges_steps_lists(self):
        self.assertEqual(parse("1-5 * * * *").minute.values, (1, 2, 3, 4, 5))
        self.assertEqual(parse("*/15 * * * *").minute.values, (0, 15, 30, 45))
        self.assertEqual(parse("0-30/10 * * * *").minute.values, (0, 10, 20, 30))
        self.assertEqual(
            parse("1,15,30-40/5 * * * *").minute.values,
            (1, 15, 30, 35, 40),
        )
        self.assertEqual(
            parse("1-5,20-25/2 * * * *").minute.values,
            (1, 2, 3, 4, 5, 20, 22, 24),
        )

    def test_star_step_one_equals_star(self):
        self.assertEqual(parse("*/1 * * * *").minute.values, tuple(range(60)))
        self.assertTrue(parse("*/1 * * * *").minute.is_star)

    def test_star_step_n_keeps_star_flag(self):
        # 与 Vixie 一致：以 * 开头即设星号位，DOM/DOW 并集规则中视为通配
        s = parse("0 0 */10 * 5")
        self.assertTrue(s.dom.is_star)
        self.assertFalse(s.dow.is_star)
        self.assertEqual(s.dom.values, (1, 11, 21, 31))
        # DOW 限定、DOM 视为星号：仅按周五判断，日号不构成额外限制
        self.assertTrue(s.matches(dt(2024, 10, 4)))   # 周五
        self.assertFalse(s.matches(dt(2024, 10, 7)))   # 周一（11/21/31 也不生效）
        self.assertTrue(s.matches(dt(2024, 10, 11)))   # 周五，恰好是 11 号也只算一次

    def test_name_range_with_step(self):
        self.assertEqual(parse("0 0 * * MON-FRI/2").dow.values, (1, 3, 5))

    def test_duplicate_values_dedup(self):
        self.assertEqual(parse("1,1,1 * * * *").minute.values, (1,))
        self.assertEqual(parse("1-3,2,3 * * * *").minute.values, (1, 2, 3))

    def test_step_overflow_is_deterministic(self):
        self.assertEqual(parse("*/90 * * * *").minute.values, (0,))
        self.assertEqual(parse("55-57/10 * * * *").minute.values, (55,))

    def test_names_case_insensitive(self):
        self.assertEqual(parse("0 0 1 jan-dec *").month.values, tuple(range(1, 13)))
        self.assertEqual(parse("0 0 * * Mon-Fri").dow.values, (1, 2, 3, 4, 5))
        self.assertEqual(parse("0 0 * jan,feb,mar *").month.values, (1, 2, 3))
        self.assertEqual(parse("0 0 * * SUN,WED,sat").dow.values, (0, 3, 6))

    def test_dow_zero_and_seven(self):
        self.assertEqual(parse("0 0 * * 0").dow.values, (0,))
        self.assertEqual(parse("0 0 * * 7").dow.values, (0,))
        self.assertEqual(parse("0 0 * * 0-7").dow.values, (0, 1, 2, 3, 4, 5, 6))


class ErrorTests(unittest.TestCase):
    def assertSyntaxError(self, expr, field=None, value=None, position=None):
        with self.assertRaises(ScheduleSyntaxError) as cm:
            parse(expr)
        err = cm.exception
        if field is not None or value is not None or position is not None:
            self.assertEqual(err.field, field, f"{expr}: field 不匹配，{err}")
            self.assertEqual(err.value, value, f"{expr}: value 不匹配，{err}")
            self.assertEqual(err.position, position, f"{expr}: position 不匹配，{err}")
        self.assertTrue(str(err))
        return err

    def test_field_count(self):
        self.assertSyntaxError("* * * *", field=None, value="* * * *", position=0)
        self.assertSyntaxError("* * * * * *", field=None,
                               value="* * * * * *", position=0)
        self.assertSyntaxError("   ", field=None, value="   ", position=0)

    def test_out_of_range(self):
        self.assertSyntaxError("60 * * * *", "minute", "60", 0)
        self.assertSyntaxError("* 24 * * *", "hour", "24", 2)
        self.assertSyntaxError("* * 0 * *", "dom", "0", 4)
        self.assertSyntaxError("* * 32 * *", "dom", "32", 4)
        self.assertSyntaxError("* * * 13 *", "month", "13", 6)
        self.assertSyntaxError("* * * * 8", "dow", "8", 8)

    def test_reversed_range(self):
        self.assertSyntaxError("5-1 * * * *", "minute", "5-1", 0)
        self.assertSyntaxError("* * * DEC-JAN *", "month", "DEC-JAN", 6)
        self.assertSyntaxError("* * * * FRI-MON", "dow", "FRI-MON", 8)

    def test_bad_step(self):
        self.assertSyntaxError("*/0 * * * *", "minute", "*/0", 0)
        self.assertSyntaxError("*/-1 * * * *", "minute", "*/-1", 0)
        self.assertSyntaxError("1-10/x * * * *", "minute", "1-10/x", 0)
        self.assertSyntaxError("*/ * * * *", "minute", "*/", 0)

    def test_empty_piece(self):
        self.assertSyntaxError("1,,2 * * * *", "minute", "", 2)
        self.assertSyntaxError(",1 * * * *", "minute", "", 0)
        self.assertSyntaxError("1, * * * *", "minute", "", 2)

    def test_unknown_names(self):
        self.assertSyntaxError("* * * JANUARY *", "month", "JANUARY", 6)
        self.assertSyntaxError("* * * * MONDAY", "dow", "MONDAY", 8)
        self.assertSyntaxError("* * * FOO *", "month", "FOO", 6)

    def test_unknown_shortcut(self):
        self.assertSyntaxError("@never", field=None, value="@never", position=0)
        self.assertSyntaxError("@hourly *", field=None,
                               value="@hourly *", position=0)

    def test_illegal_characters(self):
        self.assertSyntaxError("1$ * * * *", "minute", "1$", 0)
        self.assertSyntaxError("1.5 * * * *", "minute", "1.5", 0)
        self.assertSyntaxError("5#3 * * * *", "minute", "5#3", 0)
        self.assertSyntaxError("1-2-3 * * * *", "minute", "1-2-3", 0)
        self.assertSyntaxError("*5 * * * *", "minute", "*5", 0)
        self.assertSyntaxError("1/2 * * * *", "minute", "1/2", 0)
        self.assertSyntaxError("5- * * * *", "minute", "5-", 0)

    def test_error_message_is_chinese(self):
        err = self.assertSyntaxError("60 * * * *")
        self.assertTrue(any("\u4e00" <= ch <= "\u9fff" for ch in str(err)))

    def test_non_string(self):
        with self.assertRaises(TypeError):
            parse(123)


class DomDowUnionTests(unittest.TestCase):
    def setUp(self):
        # 每月 13 日 或 每周五 触发
        self.s = parse("0 0 13 * FRI")

    def test_dom_only_match(self):
        # 2024-10-13 是周日，但命中日号
        self.assertTrue(self.s.matches(dt(2024, 10, 13)))

    def test_dow_only_match(self):
        # 2024-10-04 是周五
        self.assertTrue(self.s.matches(dt(2024, 10, 4)))

    def test_both_match(self):
        # 2024-09-13 恰好是周五
        self.assertTrue(self.s.matches(dt(2024, 9, 13)))

    def test_neither(self):
        # 2024-10-10 是周四，也不是 13 号
        self.assertFalse(self.s.matches(dt(2024, 10, 10)))

    def test_dom_restricted_only(self):
        s = parse("0 0 1 * *")
        self.assertTrue(s.matches(dt(2024, 10, 1)))
        self.assertFalse(s.matches(dt(2024, 10, 4)))  # 周五但非 1 号

    def test_dow_restricted_only(self):
        s = parse("0 0 * * 5")
        self.assertTrue(s.matches(dt(2024, 10, 4)))
        self.assertFalse(s.matches(dt(2024, 10, 13)))  # 周日

    def test_both_star_matches_every_day(self):
        s = parse("0 0 * * *")
        self.assertTrue(s.matches(dt(2024, 2, 29)))
        self.assertTrue(s.matches(dt(2024, 12, 31)))

    def test_union_search_order(self):
        seq = self.s.next_n(dt(2024, 9, 1), 4)
        self.assertEqual(
            seq,
            [dt(2024, 9, 6), dt(2024, 9, 13), dt(2024, 9, 20), dt(2024, 9, 27)],
        )


class CalendarTests(unittest.TestCase):
    def test_leap_day(self):
        s = parse("0 0 29 2 *")
        self.assertEqual(
            s.next_n(dt(2020, 1, 1), 5),
            [
                dt(2020, 2, 29),
                dt(2024, 2, 29),
                dt(2028, 2, 29),
                dt(2032, 2, 29),
                dt(2036, 2, 29),
            ],
        )
        self.assertTrue(s.matches(dt(2024, 2, 29)))

    def test_century_leap_rules(self):
        s = parse("0 0 29 2 *")
        # 2000 是闰年；1900、2100 不是
        self.assertTrue(s.matches(dt(2000, 2, 29)))
        self.assertFalse(s.matches(dt(1900, 2, 28)))
        self.assertEqual(s.next_after(dt(2096, 3, 1)), dt(2104, 2, 29))

    def test_31_skips_short_months(self):
        s = parse("0 0 31 * *")
        seq = s.next_n(dt(2024, 1, 1), 7)
        self.assertEqual(
            seq,
            [
                dt(2024, 1, 31),
                dt(2024, 3, 31),
                dt(2024, 5, 31),
                dt(2024, 7, 31),
                dt(2024, 8, 31),
                dt(2024, 10, 31),
                dt(2024, 12, 31),
            ],
        )

    def test_cross_year(self):
        s = parse("0 0 1 1 *")
        self.assertEqual(s.next_after(dt(2020, 12, 31, 23, 59)), dt(2021, 1, 1))
        self.assertEqual(s.next_after(dt(2020, 1, 1, 0, 0)), dt(2021, 1, 1))
        s2 = parse("59 23 31 12 *")
        self.assertEqual(s2.next_after(dt(2020, 12, 31, 23, 59)),
                         dt(2021, 12, 31, 23, 59))

    def test_minute_boundaries(self):
        s = parse("0,59 * * * *")
        self.assertEqual(s.next_after(dt(2020, 1, 1, 10, 0)),
                         dt(2020, 1, 1, 10, 59))
        self.assertEqual(s.next_after(dt(2020, 1, 1, 10, 59)),
                         dt(2020, 1, 1, 11, 0))

    def test_same_day_later_vs_passed(self):
        s = parse("0 9-17 * * *")
        # 当天稍后：直接跳到当天下一个小时
        self.assertEqual(s.next_after(dt(2020, 1, 1, 12, 30)),
                         dt(2020, 1, 1, 13, 0))
        # 当天已过：次日最早时刻
        self.assertEqual(s.next_after(dt(2020, 1, 1, 18, 0)),
                         dt(2020, 1, 2, 9, 0))

    def test_impossible_date_raises(self):
        s = parse("0 0 30 2 *")  # 2 月永远没有 30 号
        with self.assertRaises(NoMatchingTimeError):
            s.next_after(dt(2020, 1, 1))
        with self.assertRaises(NoMatchingTimeError):
            s.next_n(dt(2020, 1, 1), 3)


class NextAfterTests(unittest.TestCase):
    def test_strictly_after(self):
        s = parse("0 12 * * *")
        hit = dt(2020, 1, 1, 12, 0)
        # 命中时刻本身作为输入，也必须返回下一次
        self.assertEqual(s.next_after(hit), dt(2020, 1, 2, 12, 0))

    def test_input_not_modified(self):
        s = parse("*/30 * * * *")
        original = dt(2020, 6, 15, 10, 10, 10)
        snapshot = (original.year, original.month, original.day,
                    original.hour, original.minute, original.second,
                    original.microsecond)
        s.next_after(original)
        self.assertEqual(
            snapshot,
            (original.year, original.month, original.day,
             original.hour, original.minute, original.second,
             original.microsecond),
        )

    def test_next_n_ascending_unique(self):
        s = parse("15 10 * * MON,WED")
        seq = s.next_n(dt(2024, 1, 1), 10)
        self.assertEqual(len(seq), 10)
        self.assertEqual(seq, sorted(seq))
        self.assertEqual(len(set(seq)), 10)
        self.assertTrue(all(a < b for a, b in zip(seq, seq[1:])))

    def test_next_n_bad_n(self):
        s = parse("* * * * *")
        for bad in (0, -1, -100):
            with self.assertRaises(ValueError):
                s.next_n(dt(2020, 1, 1), bad)
        with self.assertRaises(TypeError):
            s.next_n(dt(2020, 1, 1), True)

    def test_high_frequency_progress(self):
        s = parse("* * * * *")
        seq = s.next_n(dt(2020, 1, 1, 0, 0), 61)
        self.assertEqual(seq[0], dt(2020, 1, 1, 0, 1))
        self.assertEqual(seq[-1], dt(2020, 1, 1, 1, 1))


class MatchesTests(unittest.TestCase):
    def test_seconds_must_be_zero(self):
        s = parse("0 12 * * *")
        self.assertTrue(s.matches(dt(2020, 1, 1, 12, 0, 0)))
        self.assertFalse(s.matches(dt(2020, 1, 1, 12, 0, 1)))
        self.assertFalse(s.matches(dt(2020, 1, 1, 12, 0, 59)))

    def test_tzinfo_raises(self):
        s = parse("* * * * *")
        aware = dt(2020, 1, 1).replace(tzinfo=timezone.utc)
        with self.assertRaises(TypeError):
            s.matches(aware)
        with self.assertRaises(TypeError):
            s.next_after(aware)
        with self.assertRaises(TypeError):
            s.next_n(aware, 2)

    def test_non_datetime_raises(self):
        s = parse("* * * * *")
        with self.assertRaises(TypeError):
            s.matches("2020-01-01")
        with self.assertRaises(TypeError):
            s.next_after(123)


class DescribeTests(unittest.TestCase):
    EXPECTED = {
        "* * * * *": "每分钟",
        "0 2 * * *": "每天 02:00",
        "30 9 * * MON,THU": "每周一、周四 09:30",
        "0 0 1 * *": "每月1日 00:00",
        "@hourly": "每小时整点",
        "@daily": "每天 00:00",
        "@weekly": "每周日 00:00",
        "@monthly": "每月1日 00:00",
        "@yearly": "1月的1日 00:00",
        "0 0 13 * FRI": "每月13日以及每周五 00:00",
        "0 0 29 2 *": "2月的29日 00:00",
        "*/15 * * * *": "每小时的 第 0 分、第 15 分、第 30 分、第 45 分",
        "0 */6 * * *": "每天 00:00、06:00、12:00、18:00",
        "5 * * * *": "每小时第 5 分",
    }

    def test_expected_descriptions(self):
        for expr, expected in self.EXPECTED.items():
            self.assertEqual(describe(expr), expected, expr)

    def test_stable_output(self):
        exprs = list(self.EXPECTED.keys()) + [
            "1,15,30-40/5 * * * *",
            "0 0 31 * *",
            "0 9-17 * * MON-FRI",
        ]
        for expr in exprs:
            self.assertEqual(describe(expr), describe(expr))

    def test_returns_type(self):
        self.assertIsInstance(describe("* * * * *"), str)


class PerformanceTests(unittest.TestCase):
    SPARSE_EXPRS = ("0 0 1 1 *", "0 0 29 2 *")

    def test_sparse_1000_within_one_second(self):
        start = dt(2020, 1, 1)
        for expr in self.SPARSE_EXPRS:
            s = parse(expr)
            begin = time.perf_counter()
            seq = s.next_n(start, 1000)
            elapsed = time.perf_counter() - begin
            self.assertEqual(len(seq), 1000)
            self.assertLess(elapsed, 1.0, f"{expr} 取 1000 个触发耗时 {elapsed:.3f}s")
            self.assertTrue(all(a < b for a, b in zip(seq, seq[1:])))

    def test_internal_iterator_sparse_fast(self):
        # 直接走整数元组迭代器验证按字段推进的效率（无 datetime 包装开销）
        from cronspec.engine import _bump_minute
        start = (2020, 1, 1, 0, 0)
        for expr in self.SPARSE_EXPRS:
            s = parse(expr)
            it = s._iter_tuples(start)
            begin = time.perf_counter()
            for _ in range(10000):
                next(it)
            elapsed = time.perf_counter() - begin
            self.assertLess(elapsed, 1.0, f"{expr} 内部迭代 1 万次耗时 {elapsed:.3f}s")
            self.assertEqual(_bump_minute((2020, 1, 1, 0, 59)),
                             (2020, 1, 1, 1, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
