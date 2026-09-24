需求单：调度平台从 APScheduler 迁到 cronspec（对接人：调度平台 / 后端）

背景：我们要下线 APScheduler，改用贵组的 cronspec 做表达式解析与下次触发时间计算。昨天联调发现三处对不上，按优先级列在下面。请在仓库里改掉，改完我们要拿它跑一遍全量任务表。

复现命令（仓库根目录）：

    python3 -m unittest test_cronspec -v

当前 35 条里红 7 条，全部集中在 `NextAfterTests` / `NextNTests`：

    ERROR: test_leap_day
    FAIL:  test_later_today_versus_later_day
    FAIL:  test_day_31_skipping
    FAIL:  test_minute_boundaries
    FAIL:  test_seconds_input_advances_to_next_trigger
    FAIL:  test_strictly_after_and_immutable_input
    FAIL:  test_strictly_ascending_unique

问题一：`next_after` 的「严格晚于」在整分输入上失效。传进去的时刻正好命中表达式时，返回的应该是**下一个**触发时刻，现在直接把入参原样返回了。我们下游是靠「算下一个时间点，睡到那个时刻，再算下一个」这个循环跑的，返回同一个值会直接死循环。

问题二：搜索窗口太短。`0 0 29 2 *` 从 `2096-03-01` 往后找，正确结果应该是 `2104-02-29`，现在直接抛 `NoMatchingTimeError`。闰年的间隔最长能到 8 年，搜索窗口至少要覆盖公历星期与闰年的完整周期；这个上限如果被调小，对外的「找不到匹配时间」判断就变成误报，而 `NoMatchingTimeError` 我们是要拿来做配置校验的。

问题三：从入参所在的那个月开始搜的时候，起始日被定死成了 1 号。结果是：给的时刻在当月 15 号，返回的候选可能落在同月 1 号——比入参还早。要求很明确：返回的时刻必须严格晚于入参，且升序、不重复。

验收要求：

1. 上面 7 条红全部恢复，同时原有 35 条测试整体通过；测试文件不许动。
2. 这几条语义要保持：`matches` 秒不为 0 返回 False；带 `tzinfo` 的入参抛 `TypeError`；`next_after` 不修改入参；`next_n(dt, n)` 在 `n <= 0` 时抛 `ValueError`；不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError` 而不是死循环。
3. DOM/DOW 并集语义（两者都显式限定时取并集，只有一个限定时按该字段判定）不能动，这是 POSIX/vixie 的约定，README 里已经单独写过一节。
4. 性能门槛不能丢：`0 0 1 1 *` 与 `0 0 29 2 *` 从 `2020-01-01 00:00` 起连续取 1000 个触发时刻，仍要在 1 秒量级内完成——搜索必须按字段推进，不许退化成逐分钟线性扫描。
5. 三处根因各补一条回归测试，README 里「搜索算法与搜索窗口」那一节要把窗口取值依据（为什么不能小于 8 年）写清楚。

交付：`cronspec/engine.py`（必要时连带 `cronspec/fields.py`、`cronspec/parser.py`）、`test_cronspec.py`、`README.md`。注释与报错保持中文，`parse` / `describe` / `Schedule` 的对外签名不要变。
