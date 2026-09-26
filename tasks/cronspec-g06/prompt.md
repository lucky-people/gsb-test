先跟你同步一下 cronspec 这摊事（cronspec-g06），我这边要交出去了。

情况是：cronspec 是纯标准库实现的 Cron 表达式解析与触发时间计算引擎（按字段推进搜索，不逐分钟扫描）。最近在真实输入上出了问题，我查了一半没查完，跑测试是红的：

    python3 -m unittest test_cronspec -v

8/35 条失败：

    FAIL: test_day_31_skipping
    ERROR: test_exact_fragment_and_position
    ERROR: test_localization_invariant
    FAIL: test_minute_boundaries
    FAIL: test_seconds_input_advances_to_next_trigger
    ERROR: test_step_zero_or_negative
    FAIL: test_strictly_after_and_immutable_input
    FAIL: test_strictly_ascending_unique

我没查完的点，按我的笔记抄给你：

- 小月的天数被写成 31，月底的触发时刻落到不存在的日期
- 步进为 0 不再被拦，*/0 这类非法表达式被接受
- 入参正好命中表达式时 next_after 把入参原样返回，「严格晚于」失效

我已经排除的因素：跟环境、依赖没关系，纯标准库，装上就能跑；也不是测试写错。我怀疑是好几个地方一起坏了，cronspec/engine.py、cronspec/parser.py 都得看。

拜托你做到：

1. 35 条测试全绿，别去改测试文件里的断言。
2. 这些约束别弄丢：
   - `next_after` 严格晚于入参且不修改入参，`next_n` 升序且不重复，`n <= 0` 抛 `ValueError`；
   - `matches` 在秒或微秒不为 0 时返回 False，带 `tzinfo` 的入参抛 `TypeError`；
   - 不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError`，不许死循环；
   - 日与星期都显式限定时取并集（POSIX/vixie 约定）；稀疏表达式取 1000 个触发时刻仍要在 1 秒量级完成。
3. 每一处根因补一条回归测试，顺手把 README 里说得含糊或者跟实现不一致的地方改掉。
4. 交付：`cronspec/engine.py`、`cronspec/fields.py`、`cronspec/parser.py`、`test_cronspec.py`、`README.md`，注释和报错保持中文。

辛苦了。
