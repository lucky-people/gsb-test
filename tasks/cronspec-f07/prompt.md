您好，反馈一个 cronspec 的问题（工单 cronspec-f07）

我们把这个包接进了生产的处理链路，最近运维那边报了几类异常，麻烦帮忙看下。我们不是专业审代码的，只能把现象描述清楚：

- 起点月固定从 1 号开始找，返回的候选可能早于入参
- 日与星期都限定时从并集变成交集，13 号或周五只剩同时满足
- @weekly 的星期值与文档不符，短写语义整体偏移一天

我们自己复现的方式就是在仓库根目录跑：

    python3 -m unittest test_cronspec -v

现在 35 条里红 5 条，红的名字如下：

    FAIL: test_dom_dow_union
    FAIL: test_expected_descriptions
    FAIL: test_later_today_versus_later_day
    FAIL: test_shortcuts
    FAIL: test_strictly_after_and_immutable_input

期望的行为其实都写在 README 里了，我们照着 README 用的。麻烦：

1. 把上面这些现象逐条修掉，让 35 条测试全部通过。测试文件请不要改动，那是我们和你们约定的验收依据。
2. 修的过程中请守住这些约束：
   - `next_after` 严格晚于入参且不修改入参，`next_n` 升序且不重复，`n <= 0` 抛 `ValueError`；
   - `matches` 在秒或微秒不为 0 时返回 False，带 `tzinfo` 的入参抛 `TypeError`；
   - 不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError`，不许死循环；
   - 日与星期都显式限定时取并集（POSIX/vixie 约定）；稀疏表达式取 1000 个触发时刻仍要在 1 秒量级完成。
3. 每个问题点都补一条回归测试，避免下次又回归；README 里描述不一致的地方也请一并改掉。
4. 需要交付的内容：`cronspec/engine.py`、`cronspec/fields.py`、`cronspec/parser.py`、`test_cronspec.py`、`README.md`。注释、报错信息请保持中文。
