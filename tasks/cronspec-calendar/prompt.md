【缺陷报告】cronspec：日历与名字解析出问题，35 条里挂了 4 条

    ERROR: test_leap_day
    ERROR: test_month_and_weekday_names_case_insensitive
    ERROR: test_sparse_schedules_1000_in_one_second
    FAIL:  test_exact_field_value_position (expr='0 0 * jan- *')

复现：

    python3 -m unittest test_cronspec -v

三组症状：

1. 闰年判断退化：现在只按 `year % 4` 判闰年，1900、2100 这类整百年被误判为闰年，`0 0 29 2 *` 会在非闰年的 2 月 29 日给出触发时刻。
2. 月份/星期名字变成大小写敏感：`jan`、`mon` 这类小写写法解析失败（README 写明大小写不敏感）；连带错误定位用例 `0 0 * jan- *` 也红了。
3. DOM/DOW 并集语义被破坏：当「日」与「星期」都被显式限定时（如 `0 0 13 * FRI`），现在只按其中一个字段判定；POSIX 要求两者取并集（满足任一即触发）。

要求（每条都要有测试，README 把三条语义写清并给例子）：

1. 闰年规则恢复为公历规则（能被 4 整除且不能被 100 整除，或能被 400 整除），并给出 1900 / 2000 / 2100 / 2024 的断言。
2. 月份与星期名字大小写不敏感（`JAN`/`jan`/`Jan` 等价，`MON`/`mon` 等价）；非法名字仍抛 `ScheduleSyntaxError`，且 `field`/`value`/`position` 的不变量（`expr[position:position+len(value)] == value`）继续成立。
3. DOM/DOW 并集规则恢复：两者都被限定时取并集，只有一个被限定时按该字段，两者都是 `*` 时每天都判定；`0 0 13 * FRI` 要在每个 13 号与每个周五都触发（给一个跨月份的 `next_n` 断言）。
4. 稀疏表达式的性能门不能丢：`0 0 29 2 *` 与 `0 0 1 1 *` 从 2020-01-01 起取 1000 个触发时刻仍要在 1 秒内（`test_sparse_schedules_1000_in_one_second` 必须恢复通过）。
5. 原有 35 条测试全部恢复通过，不许改断言；`next_after` 严格晚于入参、`next_n` 升序不重复、`n <= 0` 抛 `ValueError`、不可达抛 `NoMatchingTimeError` 等边界保持不变。
6. 补回归测试覆盖三组根因，README 的 DOM/DOW 并集一节与闰年说明要与实现一致。

交付：改 `cronspec/engine.py`、`cronspec/parser.py`（必要时 `fields.py`）、`test_cronspec.py`、`README.md`；中文注释与报错；不动公开 API 签名。
