[CI] cronspec 流水线红灯 · job: unittest-test_cronspec · cronspec-g07

step 1/2  checkout ................................ 成功
step 2/2  python3 -m unittest test_cronspec -v ...... 失败（14/35）

日志尾部：

    ERROR: test_cross_year
    FAIL: test_day_31_skipping
    ERROR: test_exact_fragment_and_position
    FAIL: test_expected_descriptions
    FAIL: test_later_today_versus_later_day
    ERROR: test_localization_invariant
    FAIL: test_minute_boundaries
    ERROR: test_month_and_weekday_names_case_insensitive
    FAIL: test_seconds_input_advances_to_next_trigger
    FAIL: test_shortcuts
    ERROR: test_sparse_schedules_1000_in_one_second
    ERROR: test_step_zero_or_negative
    FAIL: test_strictly_after_and_immutable_input
    ERROR: test_strictly_ascending_unique

构建机结论：本次改动之后基线不再全绿，需要修复后重新触发流水线。

失败分布提示（本地复跑时确认过，症状互不相关）：

- 「大于等于 value 的最小值」被写成严格大于，正好命中的取值被跳过
- 月份与星期的名字变成大小写敏感，小写 jan/mon 解析失败
- @weekly 的星期值与文档不符，短写语义整体偏移一天
- 步进为 0 不再被拦，*/0 这类非法表达式被接受

受影响文件：cronspec/fields.py、cronspec/parser.py

解这个 job 的要求：

1. 让 `python3 -m unittest test_cronspec -v` 在干净检出后全绿；不允许改动测试文件，也不允许用跳过（skip）或放宽断言的方式让流水线变绿。
2. 流水线里其它 job 依赖的行为不能退化：
   - `next_after` 严格晚于入参且不修改入参，`next_n` 升序且不重复，`n <= 0` 抛 `ValueError`；
   - `matches` 在秒或微秒不为 0 时返回 False，带 `tzinfo` 的入参抛 `TypeError`；
   - 不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError`，不许死循环；
   - 日与星期都显式限定时取并集（POSIX/vixie 约定）；稀疏表达式取 1000 个触发时刻仍要在 1 秒量级完成。
3. 每处根因补回归测试；README 的相应章节需要同步更新，否则文档 job 下一轮还会红。
4. 改动范围：`cronspec/engine.py`、`cronspec/fields.py`、`cronspec/parser.py`、`test_cronspec.py`、`README.md`。中文注释与中文报错。
