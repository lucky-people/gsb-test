PR 评审意见 —— cronspec：逻辑调整（cronspec-g02）

结论：先别合。基线在 `python3 -m unittest test_cronspec -v` 下已经红 6/35 条，逐条写在下面。

1. 入参正好命中表达式时 next_after 把入参原样返回，「严格晚于」失效
2. 日与星期都限定时从并集变成交集，13 号或周五只剩同时满足

失败的用例：

    FAIL: test_day_31_skipping
    FAIL: test_dom_dow_union
    FAIL: test_minute_boundaries
    FAIL: test_seconds_input_advances_to_next_trigger
    FAIL: test_strictly_after_and_immutable_input
    FAIL: test_strictly_ascending_unique

几点说明：

1. 上面每一条我都在本地单独验过，症状各自独立，改一处不会让另一处跟着好。改动面看着分散在 cronspec/engine.py、cronspec/fields.py。
2. 修的时候别动 `test_cronspec.py` 里的断言——那份测试是验收基线，写的是这个包对外承诺的行为，红了说明实现错了，不是测试写错了。
3. 下面这些约束请一起保持：
   - `next_after` 严格晚于入参且不修改入参，`next_n` 升序且不重复，`n <= 0` 抛 `ValueError`；
   - `matches` 在秒或微秒不为 0 时返回 False，带 `tzinfo` 的入参抛 `TypeError`；
   - 不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError`，不许死循环；
   - 日与星期都显式限定时取并集（POSIX/vixie 约定）；稀疏表达式取 1000 个触发时刻仍要在 1 秒量级完成。
4. 每条根因都要补回归测试，别只把现有用例弄绿就算完；README 对应段落（语义说明、边界取舍）要跟实现对齐。
5. 交付范围：`cronspec/engine.py`、`cronspec/fields.py`、`cronspec/parser.py`、`test_cronspec.py`、`README.md`。注释与报错保持中文，公开 API 签名不要改。
