# 事故复盘：cronspec 相关链路异常（cronspec-g01）

事故简述：下游今天反馈，cronspec 在处理真实输入时结果不对，一部分直接抛异常炸在半路。我们内部先按最小复现跑了一遍，确认不是环境问题。

这个包是纯标准库实现的 Cron 表达式解析与触发时间计算引擎（按字段推进搜索，不逐分钟扫描），目前的问题集中在它的核心逻辑上。

初判的影响面，按严重程度排：

- 带 tzinfo 的入参不再被拒，时区语义悄悄跑偏
- 「大于等于 value 的最小值」被写成严格大于，正好命中的取值被跳过

复现命令（仓库根目录）：

    python3 -m unittest test_cronspec -v

现在 35 条里红 9 条：

    ERROR: test_cross_year
    FAIL: test_day_31_skipping
    FAIL: test_later_today_versus_later_day
    FAIL: test_minute_boundaries
    FAIL: test_seconds_input_advances_to_next_trigger
    ERROR: test_sparse_schedules_1000_in_one_second
    FAIL: test_strictly_after_and_immutable_input
    ERROR: test_strictly_ascending_unique
    FAIL: test_tzinfo_rejected

我看下来这不像一处原因，至少分布在 cronspec/engine.py、cronspec/fields.py 这几个文件里，修一处另一处仍会红。请你：

1. 定位并修掉全部根因，让 35 条测试全绿。不许改测试、删断言，也不许把校验放宽或注释掉来「让它过」。
2. 这些不变量必须继续成立：
   - `next_after` 严格晚于入参且不修改入参，`next_n` 升序且不重复，`n <= 0` 抛 `ValueError`；
   - `matches` 在秒或微秒不为 0 时返回 False，带 `tzinfo` 的入参抛 `TypeError`；
   - 不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError`，不许死循环；
   - 日与星期都显式限定时取并集（POSIX/vixie 约定）；稀疏表达式取 1000 个触发时刻仍要在 1 秒量级完成。
3. 每处根因补至少一条回归测试；README 里与本次改动相关的小节要同步改到与实现一致。
4. 修完请用同一条命令复跑确认，并在 README 里写明本次修复涉及哪几条语义。

交付：`cronspec/engine.py`、`cronspec/fields.py`、`cronspec/parser.py`、`test_cronspec.py`、`README.md`。注释与报错信息保持中文，公开 API 与已有行为不要动。
