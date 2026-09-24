“cronspec 这个包你帮我看下，我这边结果不对。”

“什么现象？”

“我列了几个，都是真跑出来的：

- 起点月固定从 1 号开始找，返回的候选可能早于入参
- 闰年只按能不能被 4 整除判，整百年被误判
- 日与星期都限定时从并集变成交集，13 号或周五只剩同时满足

”

“先跑一遍测试确认下？”

“跑了，仓库根目录 `python3 -m unittest test_cronspec -v`，5/35 条红：

    FAIL: test_dom_dow_union
    FAIL: test_later_today_versus_later_day
    ERROR: test_leap_day
    FAIL: test_sparse_schedules_1000_in_one_second
    FAIL: test_strictly_after_and_immutable_input

”

“看着不像一处问题。”

“我也这么觉得，cronspec/engine.py、cronspec/fields.py 我都翻过，几个地方都可疑。麻烦你排一下，要求是：

1. 35 条测试全部弄绿，别改测试文件——那是验收基线；
2. 这些行为不能变：
   - `next_after` 严格晚于入参且不修改入参，`next_n` 升序且不重复，`n <= 0` 抛 `ValueError`；
   - `matches` 在秒或微秒不为 0 时返回 False，带 `tzinfo` 的入参抛 `TypeError`；
   - 不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError`，不许死循环；
   - 日与星期都显式限定时取并集（POSIX/vixie 约定）；稀疏表达式取 1000 个触发时刻仍要在 1 秒量级完成。
3. 每处根因补一条回归测试，README 里说不清楚的地方一起补；
4. 交付 `cronspec/engine.py`、`cronspec/fields.py`、`cronspec/parser.py`、`test_cronspec.py`、`README.md`，注释和报错用中文。”
