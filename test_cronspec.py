"""cronspec 标准库 unittest 测试套件。"""

import random
import time
import unittest
from datetime import datetime, timezone

from cronspec import describe, parse
from cronspec.errors import NoMatchingTimeError, ScheduleSyntaxError


def dt(year, month, day, hour=0, minute=0, second=0, microsecond=0):
    return datetime(year, month, day, hour, minute, second, microsecond)


class ParseTests(unittest.TestCase):
    def test_basic_fields_and_dedup(self):
        schedule = parse("1,1,1 * * * *")
        self.assertEqual(schedule.minute.values, (1,))
        self.assertEqual(parse("*/1 * * * *").minute.values, tuple(range(60)))
        self.assertTrue(parse("*/1 * * * *").minute.is_star)

    def test_range_step_list_combination(self):
        schedule = parse("1-5,20-25/2 * * * *")
        self.assertEqual(schedule.minute.values, (1, 2, 3, 4, 5, 20, 22, 24))

    def test_month_and_weekday_names_case_insensitive(self):
        schedule = parse("0 0 * jan,dec mon-FRI")
        self.assertEqual(schedule.month.values, (1, 12))
        self.assertEqual(schedule.day_of_week.values, (1, 2, 3, 4, 5))
        # 0 与 7 都表示周日。
        self.assertEqual(parse("0 0 * * 0").day_of_week.values, (0,))
        self.assertEqual(parse("0 0 * * 7").day_of_week.values, (0,))
        self.assertEqual(parse("0 0 * * SUN,sat").day_of_week.values, (0, 6))

    def test_whitespace(self):
        schedule = parse("\t  0\t\t2  *   *  *  ")
        self.assertEqual(schedule.minute.values, (0,))
        self.assertEqual(schedule.hour.values, (2,))
        with self.assertRaises(ScheduleSyntaxError):
            parse("0 2 * * *\n")

    def test_shortcuts(self):
        cases = {
            "@yearly": "0 0 1 1 *",
            "@annually": "0 0 1 1 *",
            "@monthly": "0 0 1 * *",
            "@weekly": "0 0 * * 0",
            "@daily": "0 0 * * *",
            "@midnight": "0 0 * * *",
            "@hourly": "0 * * * *",
        }
        for shortcut, expanded in cases.items():
            shortcut_schedule = parse(shortcut)
            expanded_schedule = parse(expanded)
            self.assertEqual(shortcut_schedule.minute, expanded_schedule.minute)
            self.assertEqual(shortcut_schedule.hour, expanded_schedule.hour)
            self.assertEqual(
                shortcut_schedule.day_of_month, expanded_schedule.day_of_month
            )
            self.assertEqual(shortcut_schedule.month, expanded_schedule.month)
            self.assertEqual(
                shortcut_schedule.day_of_week, expanded_schedule.day_of_week
            )


class SyntaxErrorTests(unittest.TestCase):
    def assert_error(self, expr, field, value, position, keywords=()):
        with self.assertRaises(ScheduleSyntaxError) as captured:
            parse(expr)
        error = captured.exception
        self.assertEqual(error.field, field)
        self.assertEqual(error.value, value)
        self.assertEqual(error.position, position)
        self.assertTrue(str(error))
        for keyword in keywords:
            self.assertIn(keyword, str(error))

    def test_wrong_field_count(self):
        self.assert_error("0 2 * *", None, "0 2 * *", 0)
        self.assert_error("0 2 * * * *", None, "0 2 * * * *", 0)
        self.assert_error("   ", None, "", 0)

    def test_unknown_shortcut(self):
        self.assert_error("@never", None, "@never", 0)
        self.assert_error("@daily x", None, "@daily x", 0)

    def test_out_of_range(self):
        self.assert_error("60 * * * *", "minute", "60", 0, ["范围"])
        self.assert_error("* 24 * * *", "hour", "24", 2, ["范围"])
        self.assert_error("* * 0 * *", "day_of_month", "0", 4, ["范围"])
        self.assert_error("* * 32 * *", "day_of_month", "32", 4, ["范围"])
        self.assert_error("* * * 13 *", "month", "13", 6, ["范围"])
        self.assert_error("* * * * 8", "day_of_week", "8", 8, ["范围"])

    def test_reversed_range(self):
        self.assert_error("5-1 * * * *", "minute", "5-1", 0, ["倒序"])

    def test_step_zero_or_negative(self):
        self.assert_error("*/0 * * * *", "minute", "0", 2, ["步进"])
        self.assert_error("1-10/-2 * * * *", "minute", "-2", 5, ["步进"])

    def test_empty_fragment(self):
        self.assert_error("1,,2 * * * *", "minute", "", 2, ["空片段"])
        self.assert_error(",1 * * * *", "minute", "", 0, ["空片段"])
        self.assert_error("1, * * * *", "minute", "", 2, ["空片段"])

    def test_unknown_names(self):
        self.assert_error(
            "* * * JANUARY *", "month", "JANUARY", 6, ["未知名字"]
        )
        self.assert_error(
            "* * * * MONDAY", "day_of_week", "MONDAY", 8, ["未知名字"]
        )

    def test_invalid_characters(self):
        self.assert_error("1.5 * * * *", "minute", "1.5", 0)
        self.assert_error("1- * * * *", "minute", "", 2, ["缺少结束值"])
        self.assert_error("*-5 * * * *", "minute", "*-5", 0)
        self.assert_error("5/10 * * * *", "minute", "5/10", 0, ["步进"])
        self.assert_error("** * * * *", "minute", "**", 0)
        self.assert_error("*/*5 * * * *", "minute", "*5", 2, ["步进"])


class ErrorLocationTests(unittest.TestCase):
    """错误定位约定：value 是最小出错片段原文，position 指向它的 0 基起点。

    每条用例既断言精确的 (field, value, position)，也断言不变量
    ``expr[position:position+len(value)] == value``。
    """

    # (表达式, field, value, position, 报错说明中应出现的关键词)
    CASES = [
        # 数字越界
        ("60 0 * * *", "minute", "60", 0, "超出允许范围"),
        ("0 24 * * *", "hour", "24", 2, "超出允许范围"),
        ("0 0 0 * *", "day_of_month", "0", 4, "超出允许范围"),
        ("0 0 32 * *", "day_of_month", "32", 4, "超出允许范围"),
        ("0 0 * 0 *", "month", "0", 6, "超出允许范围"),
        ("0 0 * 13 *", "month", "13", 6, "超出允许范围"),
        ("0 0 * * 8", "day_of_week", "8", 8, "超出允许范围"),
        # 范围倒序
        ("5-1 0 * * *", "minute", "5-1", 0, "倒序"),
        ("0 0 * 12-1 *", "month", "12-1", 6, "倒序"),
        ("5-1/2 0 * * *", "minute", "5-1", 0, "倒序"),
        # 步进非法
        ("*/0 0 * * *", "minute", "0", 2, "步进"),
        ("0 */0 * * *", "hour", "0", 4, "步进"),
        ("1-5/0 0 * * *", "minute", "0", 4, "步进"),
        ("0 0 * * FRI/SAT", "day_of_week", "SAT", 12, "步进"),
        ("0 0 * * /5", "day_of_week", "/5", 8, "步进"),
        # 空片段
        ("1,,2 0 * * *", "minute", "", 2, "空片段"),
        (",1 0 * * *", "minute", "", 0, "空片段"),
        ("1, 0 * * *", "minute", "", 2, "空片段"),
        ("0 0 * * ,", "day_of_week", "", 8, "空片段"),
        # 未知名字
        ("0 0 * JANUARY *", "month", "JANUARY", 6, "未知名字"),
        ("0 0 * * MONDAY", "day_of_week", "MONDAY", 8, "未知名字"),
        # 非法范围字符
        ("0 a * * *", "hour", "a", 2, "非法字符"),
        ("0 0 * * 1--2", "day_of_week", "1--2", 8, "范围符"),
        ("-1 0 * * *", "minute", "", 0, "缺少起始值"),
        # 未闭合范围
        ("0 0 * jan- *", "month", "", 10, "缺少结束值"),
        ("0 0 * * 1-", "day_of_week", "", 10, "缺少结束值"),
        # 字段数错
        ("0 0 1 *", None, "0 0 1 *", 0, "5 个字段"),
        ("0 0 1 * * *", None, "0 0 1 * * *", 0, "5 个字段"),
        # 短写非法
        ("@never", None, "@never", 0, "未知短写"),
        ("@", None, "@", 0, "未知短写"),
        # 空表达式
        ("", None, "", 0, "为空"),
    ]

    def test_exact_field_value_position(self):
        for expr, field, value, position, keyword in self.CASES:
            with self.subTest(expr=expr):
                with self.assertRaises(ScheduleSyntaxError) as captured:
                    parse(expr)
                error = captured.exception
                self.assertEqual(error.field, field)
                self.assertEqual(error.value, value)
                self.assertEqual(error.position, position)
                self.assertIn(keyword, str(error))

    def test_location_invariant(self):
        for expr, _field, _value, _position, _keyword in self.CASES:
            with self.subTest(expr=expr):
                with self.assertRaises(ScheduleSyntaxError) as captured:
                    parse(expr)
                error = captured.exception
                end = error.position + len(error.value)
                self.assertEqual(expr[error.position:end], error.value)


class MutationTests(unittest.TestCase):
    """对合法表达式做固定种子的随机字符变异，校验报错路径的健壮性。"""

    VALID_EXPRESSIONS = (
        "* * * * *",
        "0 0 * * *",
        "*/15 9-17/2 1,15 JAN-MAR MON-FRI",
        "1-5,20-25/2 8-10/2 * JAN-MAR MON,WED",
        "0 0 29 2 *",
        "30 9 * * MON-FRI",
        "@daily",
        "@hourly",
        "@yearly",
    )

    # 覆盖语法字符、名字字母、分隔空白与 Unicode 陷阱字符。
    MUTATION_ALPHABET = "0123456789*,/-@ \t\n.aZJNMF~²"

    FIELDS = (None, "minute", "hour", "day_of_month", "month", "day_of_week")

    def _mutate(self, rng, expr):
        chars = list(expr)
        for _ in range(rng.randint(1, 3)):
            operation = rng.choice(("insert", "delete", "replace"))
            if operation == "insert" or not chars:
                chars.insert(
                    rng.randint(0, len(chars)),
                    rng.choice(self.MUTATION_ALPHABET),
                )
            elif operation == "delete":
                del chars[rng.randrange(len(chars))]
            else:
                chars[rng.randrange(len(chars))] = rng.choice(
                    self.MUTATION_ALPHABET
                )
        return "".join(chars)

    def test_random_mutations_keep_error_contract(self):
        rng = random.Random(20260924)
        error_count = 0
        for expr in self.VALID_EXPRESSIONS:
            for _ in range(50):
                mutated = self._mutate(rng, expr)
                try:
                    parse(mutated)
                except ScheduleSyntaxError as error:
                    error_count += 1
                    self.assertIn(error.field, self.FIELDS, repr(mutated))
                    self.assertIsInstance(error.value, str)
                    self.assertIsInstance(error.position, int)
                    self.assertGreaterEqual(error.position, 0)
                    end = error.position + len(error.value)
                    self.assertEqual(
                        mutated[error.position:end],
                        error.value,
                        "不变量被破坏：%r -> field=%r value=%r position=%r"
                        % (mutated, error.field, error.value, error.position),
                    )
                    self.assertTrue(str(error))
                except Exception as unexpected:
                    self.fail(
                        "变异输入 %r 漏出了非 ScheduleSyntaxError：%r"
                        % (mutated, unexpected)
                    )
        # 确保变异确实制造出了大量非法输入，而不是全部意外合法。
        self.assertGreater(error_count, 100)


class MatchesTests(unittest.TestCase):
    def test_simple_match(self):
        schedule = parse("30 9 * * MON-FRI")
        self.assertTrue(schedule.matches(dt(2024, 9, 23, 9, 30)))
        self.assertFalse(schedule.matches(dt(2024, 9, 21, 9, 30)))
        self.assertFalse(schedule.matches(dt(2024, 9, 23, 9, 31)))

    def test_seconds_must_be_zero(self):
        schedule = parse("* * * * *")
        self.assertTrue(schedule.matches(dt(2024, 1, 1, 0, 0)))
        self.assertFalse(schedule.matches(dt(2024, 1, 1, 0, 0, second=1)))
        self.assertFalse(schedule.matches(dt(2024, 1, 1, 0, 0, microsecond=1)))

    def test_tzinfo_rejected(self):
        schedule = parse("* * * * *")
        aware = datetime(2024, 1, 1, tzinfo=timezone.utc)
        with self.assertRaises(TypeError):
            schedule.matches(aware)
        with self.assertRaises(TypeError):
            schedule.next_after(aware)
        with self.assertRaises(TypeError):
            schedule.next_n(aware, 1)

    def test_dom_dow_union(self):
        # 每个 13 号以及每个周五触发。
        schedule = parse("0 0 13 * FRI")
        self.assertTrue(schedule.matches(dt(2024, 9, 13)))  # 周五且 13 号
        self.assertTrue(schedule.matches(dt(2024, 9, 20)))  # 周五
        self.assertTrue(schedule.matches(dt(2025, 6, 13)))  # 13 号
        self.assertFalse(schedule.matches(dt(2024, 9, 14)))  # 周六非 13 号

    def test_dom_dow_single_restriction(self):
        dom_only = parse("0 0 13 * *")
        self.assertTrue(dom_only.matches(dt(2024, 9, 13)))
        self.assertFalse(dom_only.matches(dt(2024, 9, 20)))
        dow_only = parse("0 0 * * FRI")
        self.assertFalse(dow_only.matches(dt(2024, 8, 13)))  # 13 号是周二
        self.assertTrue(dow_only.matches(dt(2024, 9, 20)))


class NextAfterTests(unittest.TestCase):
    def test_strictly_after_and_immutable_input(self):
        schedule = parse("0 12 * * *")
        start = dt(2024, 3, 10, 12, 0)
        snapshot = start.replace()
        result = schedule.next_after(start)
        self.assertEqual(result, dt(2024, 3, 11, 12, 0))
        self.assertGreater(result, start)
        self.assertEqual(start, snapshot)

    def test_later_today_versus_later_day(self):
        schedule = parse("30 9 * * *")
        # 当天稍晚时刻 -> 今天。
        self.assertEqual(
            schedule.next_after(dt(2024, 3, 10, 8, 0)), dt(2024, 3, 10, 9, 30)
        )
        # 当天已过 -> 次日。
        self.assertEqual(
            schedule.next_after(dt(2024, 3, 10, 10, 0)),
            dt(2024, 3, 11, 9, 30),
        )

    def test_minute_boundaries(self):
        schedule = parse("0,59 * * * *")
        self.assertEqual(
            schedule.next_after(dt(2024, 1, 1, 0, 0)),
            dt(2024, 1, 1, 0, 59),
        )
        self.assertEqual(
            schedule.next_after(dt(2024, 1, 1, 0, 59, 30)),
            dt(2024, 1, 1, 1, 0),
        )

    def test_seconds_input_advances_to_next_trigger(self):
        schedule = parse("0 0 * * *")
        self.assertEqual(
            schedule.next_after(dt(2024, 1, 1, 0, 0, 59)),
            dt(2024, 1, 2, 0, 0),
        )

    def test_cross_year(self):
        schedule = parse("0 0 1 1 *")
        self.assertEqual(
            schedule.next_after(dt(2024, 12, 31, 23, 59)),
            dt(2025, 1, 1, 0, 0),
        )

    def test_leap_day(self):
        schedule = parse("0 0 29 2 *")
        self.assertEqual(schedule.next_after(dt(2019, 1, 1)), dt(2020, 2, 29))
        self.assertEqual(
            schedule.next_after(dt(2020, 2, 29, 12, 0)), dt(2024, 2, 29)
        )
        # 2100 年不是闰年，应跳到 2104 年。
        self.assertEqual(schedule.next_after(dt(2096, 3, 1)), dt(2104, 2, 29))

    def test_day_31_skipping(self):
        schedule = parse("0 0 31 * *")
        results = schedule.next_n(dt(2025, 1, 15), 5)
        self.assertEqual(
            results,
            [
                dt(2025, 1, 31),
                dt(2025, 3, 31),
                dt(2025, 5, 31),
                dt(2025, 7, 31),
                dt(2025, 8, 31),
            ],
        )

    def test_impossible_schedule(self):
        schedule = parse("0 0 30 2 *")
        with self.assertRaises(NoMatchingTimeError):
            schedule.next_after(dt(2020, 1, 1))
        with self.assertRaises(NoMatchingTimeError):
            schedule.next_n(dt(2020, 1, 1), 3)

    def test_matches_agrees_with_next_after(self):
        schedule = parse("15 10 1,15 * MON,WED,FRI")
        current = dt(2023, 5, 1)
        following = schedule.next_after(current)
        self.assertTrue(schedule.matches(following))
        self.assertGreater(following, current)


class NextNTests(unittest.TestCase):
    def test_strictly_ascending_unique(self):
        schedule = parse("0 0 1 1 *")
        results = schedule.next_n(dt(2020, 1, 1), 100)
        self.assertEqual(len(results), 100)
        self.assertEqual(results, sorted(results))
        self.assertEqual(len(set(results)), 100)
        self.assertEqual(results[0], dt(2021, 1, 1))
        self.assertEqual(results[1], dt(2022, 1, 1))

    def test_invalid_n(self):
        schedule = parse("* * * * *")
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                schedule.next_n(dt(2024, 1, 1), bad)


class DescribeTests(unittest.TestCase):
    EXPECTED = {
        "* * * * *": "每分钟",
        "0 2 * * *": "每天 02:00",
        "30 9 * * MON,THU": "每周一、周四 09:30",
        "0 0 1 * *": "每月 1 日 00:00",
        "@hourly": "每小时整点",
        "@weekly": "每周日 00:00",
        "@yearly": "每年 1 月 1 日 00:00",
        "0 0 29 2 *": "每年 2 月 29 日 00:00",
        "0 0 13 * FRI": "每月 13 日或周五 00:00",
    }

    def test_expected_descriptions(self):
        for expr, expected in self.EXPECTED.items():
            self.assertEqual(describe(expr), expected, expr)

    def test_stable_output(self):
        expr = "1-5,20-25/2 8-10/2 * JAN-MAR MON,WED"
        self.assertEqual(describe(expr), describe(expr))


class PerformanceTests(unittest.TestCase):
    def test_sparse_schedules_1000_in_one_second(self):
        cases = ("0 0 1 1 *", "0 0 29 2 *")
        start = dt(2020, 1, 1)
        for expr in cases:
            schedule = parse(expr)
            begin = time.perf_counter()
            results = schedule.next_n(start, 1000)
            elapsed = time.perf_counter() - begin
            self.assertEqual(len(results), 1000)
            self.assertLess(elapsed, 1.0, "%s 耗时 %.3fs" % (expr, elapsed))


class LeapYearRegressionTests(unittest.TestCase):
    """回归：闰年必须按公历规则判定，不能只看 year % 4。"""

    def test_gregorian_leap_rule(self):
        from cronspec.engine import is_leap

        # 能被 4 整除且不能被 100 整除，或能被 400 整除。
        self.assertFalse(is_leap(1900))  # 整百年且不能被 400 整除
        self.assertTrue(is_leap(2000))   # 能被 400 整除
        self.assertFalse(is_leap(2100))
        self.assertTrue(is_leap(2024))

    def test_feb29_skips_century_years(self):
        schedule = parse("0 0 29 2 *")
        # 1900 年不是闰年：从 1896 年的 2 月 29 日之后应直接跳到 1904 年。
        self.assertEqual(
            schedule.next_after(dt(1896, 3, 1)), dt(1904, 2, 29)
        )
        # 2000 年是闰年，2000-02-29 本身可达。
        self.assertTrue(schedule.matches(dt(2000, 2, 29)))
        self.assertEqual(
            schedule.next_after(dt(1996, 3, 1)), dt(2000, 2, 29)
        )

    def test_days_in_february_century_years(self):
        from cronspec.engine import days_in_month

        self.assertEqual(days_in_month(1900, 2), 28)
        self.assertEqual(days_in_month(2000, 2), 29)
        self.assertEqual(days_in_month(2100, 2), 28)
        self.assertEqual(days_in_month(2024, 2), 29)


class CaseInsensitiveNamesRegressionTests(unittest.TestCase):
    """回归：月份/星期名字必须大小写不敏感，非法名字仍精确定位报错。"""

    def test_month_name_any_case(self):
        for token in ("JAN", "jan", "Jan", "jAn"):
            schedule = parse("0 0 * %s *" % token)
            self.assertEqual(schedule.month.values, (1,), token)
        mixed = parse("0 0 * jAn,DeC,Mar *")
        self.assertEqual(mixed.month.values, (1, 3, 12))
        # 名字参与范围与步进时同样不区分大小写。
        ranged = parse("0 0 * jan-mar/2 *")
        self.assertEqual(ranged.month.values, (1, 3))

    def test_weekday_name_any_case(self):
        for token in ("MON", "mon", "Mon"):
            schedule = parse("0 0 * * %s" % token)
            self.assertEqual(schedule.day_of_week.values, (1,), token)
        ranged = parse("0 0 * * mon-fri")
        self.assertEqual(ranged.day_of_week.values, (1, 2, 3, 4, 5))

    def test_unknown_name_still_syntax_error_with_invariant(self):
        for expr, field, value, position in (
            ("0 0 * jaa *", "month", "jaa", 6),
            ("0 0 * * frii", "day_of_week", "frii", 8),
            ("0 0 * jan-x *", "month", "x", 10),
        ):
            with self.subTest(expr=expr):
                with self.assertRaises(ScheduleSyntaxError) as captured:
                    parse(expr)
                error = captured.exception
                self.assertEqual(error.field, field)
                self.assertEqual(error.value, value)
                self.assertEqual(error.position, position)
                # 定位不变量在小写非法名字上继续成立。
                end = error.position + len(error.value)
                self.assertEqual(expr[error.position:end], error.value)


class DomDowUnionRegressionTests(unittest.TestCase):
    """回归：DOM 与 DOW 都被限定时必须取并集（满足任一即触发）。"""

    def test_union_matches(self):
        schedule = parse("0 0 13 * FRI")
        # 2024-09-13 既是周五又是 13 号；09-20 只是周五；
        # 2025-06-13 是 13 号；2024-09-14 两者都不是。
        self.assertTrue(schedule.matches(dt(2024, 9, 13)))
        self.assertTrue(schedule.matches(dt(2024, 9, 20)))
        self.assertTrue(schedule.matches(dt(2025, 6, 13)))
        self.assertFalse(schedule.matches(dt(2024, 9, 14)))

    def test_union_next_n_across_months(self):
        schedule = parse("0 0 13 * FRI")
        results = schedule.next_n(dt(2024, 9, 1), 8)
        # 跨 9、10 两个月：每个周五以及每个 13 号，按时间升序去重。
        expected = [
            dt(2024, 9, 6),
            dt(2024, 9, 13),
            dt(2024, 9, 20),
            dt(2024, 9, 27),
            dt(2024, 10, 4),
            dt(2024, 10, 11),
            dt(2024, 10, 13),
            dt(2024, 10, 18),
        ]
        self.assertEqual(results, expected)
        # 升序、严格晚于起点、不重复。
        self.assertEqual(results, sorted(set(results)))
        self.assertTrue(all(day > dt(2024, 9, 1) for day in results))

    def test_single_restriction_uses_only_that_field(self):
        dom_only = parse("0 0 13 * *")
        dow_only = parse("0 0 * * FRI")
        self.assertEqual(
            dom_only.next_n(dt(2024, 9, 1), 3),
            [dt(2024, 9, 13), dt(2024, 10, 13), dt(2024, 11, 13)],
        )
        self.assertEqual(
            dow_only.next_n(dt(2024, 9, 1), 3),
            [dt(2024, 9, 6), dt(2024, 9, 13), dt(2024, 9, 20)],
        )

    def test_both_star_is_every_day(self):
        schedule = parse("0 0 * * *")
        self.assertEqual(
            schedule.next_after(dt(2024, 2, 28)), dt(2024, 2, 29)
        )
        # 2100 年不是闰年，星号表达式在 2 月只有 28 天，次日为 3 月 1 日。
        self.assertEqual(
            schedule.next_after(dt(2100, 2, 28)), dt(2100, 3, 1)
        )


if __name__ == "__main__":
    unittest.main()
