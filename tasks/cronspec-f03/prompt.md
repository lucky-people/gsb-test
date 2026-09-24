迁移验收单：把批处理链路从旧实现切到 cronspec（cronspec-f03）

我们准备用 cronspec（纯标准库实现的 Cron 表达式解析与触发时间计算引擎（按字段推进搜索，不逐分钟扫描））替换现在的旧实现。灰度阶段按老实现的结果做对照，验收用例跑出 5/35 条不一致，切换因此卡在这里。

对照中暴露的差异：

- @weekly 的星期值与文档不符，短写语义整体偏移一天
- 月份与星期的名字变成大小写敏感，小写 jan/mon 解析失败
- 起点月固定从 1 号开始找，返回的候选可能早于入参

验收命令（仓库根目录）：

    python3 -m unittest test_cronspec -v

不一致的用例：

    FAIL: test_expected_descriptions
    FAIL: test_later_today_versus_later_day
    ERROR: test_month_and_weekday_names_case_insensitive
    FAIL: test_shortcuts
    FAIL: test_strictly_after_and_immutable_input

判断：差异跨了 cronspec/engine.py、cronspec/parser.py，不是一处适配问题，需要逐个对齐语义后重新验收。

切换前必须满足：

1. 35 条验收用例全部通过，测试文件作为对照基准不得修改。
2. 切换后这些既有承诺不能被破坏（旧实现里也是这么做的）：
   - `next_after` 严格晚于入参且不修改入参，`next_n` 升序且不重复，`n <= 0` 抛 `ValueError`；
   - `matches` 在秒或微秒不为 0 时返回 False，带 `tzinfo` 的入参抛 `TypeError`；
   - 不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError`，不许死循环；
   - 日与星期都显式限定时取并集（POSIX/vixie 约定）；稀疏表达式取 1000 个触发时刻仍要在 1 秒量级完成。
3. 每处差异补一条回归用例，把「为什么这么判定」写进 README，避免下次切换再对不上。
4. 交付：`cronspec/engine.py`、`cronspec/fields.py`、`cronspec/parser.py`、`test_cronspec.py`、`README.md`；注释与报错保持中文，对外接口签名不变。
