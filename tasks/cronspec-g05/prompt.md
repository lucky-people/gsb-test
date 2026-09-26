对账对不上，想请你帮忙定位一下 cronspec（cronspec-g05）

我们把 cronspec（纯标准库实现的 Cron 表达式解析与触发时间计算引擎（按字段推进搜索，不逐分钟扫描））接进了批处理流程，上线前拿一批样本跟参考实现逐条比。抽了三轮，结论不一致的比例明显超出预期，人工核对之后归成下面几类：

- 「大于等于 value 的最小值」被写成严格大于，正好命中的取值被跳过
- 入参正好命中表达式时 next_after 把入参原样返回，「严格晚于」失效
- @weekly 的星期值与文档不符，短写语义整体偏移一天

在仓库根目录可以直接复现：

    python3 -m unittest test_cronspec -v

现在是 10/35 条红：

    ERROR: test_cross_year
    FAIL: test_day_31_skipping
    FAIL: test_expected_descriptions
    FAIL: test_later_today_versus_later_day
    FAIL: test_minute_boundaries
    FAIL: test_seconds_input_advances_to_next_trigger
    FAIL: test_shortcuts
    ERROR: test_sparse_schedules_1000_in_one_second
    FAIL: test_strictly_after_and_immutable_input
    ERROR: test_strictly_ascending_unique

我的判断是这几类来自不同地方——cronspec/engine.py、cronspec/fields.py、cronspec/parser.py 里都有嫌疑，请分别定位。要求：

1. 35 条测试全部恢复通过。测试文件不动。
2. 修复过程中这些约束不能破：
   - `next_after` 严格晚于入参且不修改入参，`next_n` 升序且不重复，`n <= 0` 抛 `ValueError`；
   - `matches` 在秒或微秒不为 0 时返回 False，带 `tzinfo` 的入参抛 `TypeError`；
   - 不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError`，不许死循环；
   - 日与星期都显式限定时取并集（POSIX/vixie 约定）；稀疏表达式取 1000 个触发时刻仍要在 1 秒量级完成。
3. 每类问题补一条针对性的回归测试（最好能直接复现对账时的那种输入），并在 README 里把判定口径写清楚。
4. 交付：`cronspec/engine.py`、`cronspec/fields.py`、`cronspec/parser.py`、`test_cronspec.py`、`README.md`。中文注释与中文报错，公开 API 不变。
