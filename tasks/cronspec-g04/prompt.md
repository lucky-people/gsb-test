# 需求单：对齐 cronspec 的对外语义（cronspec-g04）

背景：我们把 cronspec 当成基础设施接进了业务链路（纯标准库实现的 Cron 表达式解析与触发时间计算引擎（按字段推进搜索，不逐分钟扫描））。接入测试发现它的实现与我们按 README 理解的语义不一致，先把不一致的地方列出来。

## 现象清单

| 编号 | 现象 |
|---|---|
| 1 | 「大于等于 value 的最小值」被写成严格大于，正好命中的取值被跳过 |
| 2 | @weekly 的星期值与文档不符，短写语义整体偏移一天 |
| 3 | 步进为 0 不再被拦，*/0 这类非法表达式被接受 |

## 复现与失败用例

    python3 -m unittest test_cronspec -v

当前 13/35 条失败：

    ERROR: test_cross_year
    FAIL: test_day_31_skipping
    ERROR: test_exact_fragment_and_position
    FAIL: test_expected_descriptions
    FAIL: test_later_today_versus_later_day
    ERROR: test_localization_invariant
    FAIL: test_minute_boundaries
    FAIL: test_seconds_input_advances_to_next_trigger
    FAIL: test_shortcuts
    ERROR: test_sparse_schedules_1000_in_one_second
    ERROR: test_step_zero_or_negative
    FAIL: test_strictly_after_and_immutable_input
    ERROR: test_strictly_ascending_unique

## 验收要求

1. 以上现象全部消除，35 条测试全绿；测试文件是验收基线，不允许修改或删除断言。
2. 实现必须满足下列硬性约束：
   - `next_after` 严格晚于入参且不修改入参，`next_n` 升序且不重复，`n <= 0` 抛 `ValueError`；
   - `matches` 在秒或微秒不为 0 时返回 False，带 `tzinfo` 的入参抛 `TypeError`；
   - 不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError`，不许死循环；
   - 日与星期都显式限定时取并集（POSIX/vixie 约定）；稀疏表达式取 1000 个触发时刻仍要在 1 秒量级完成。
3. 每条现象对应一处独立根因（预计分布在 cronspec/fields.py、cronspec/parser.py），请逐一定位；只改一处会有用例继续红。
4. 为每处根因补回归测试；README 里与本需求相关的语义说明要与实现一致。
5. 交付物：`cronspec/engine.py`、`cronspec/fields.py`、`cronspec/parser.py`、`test_cronspec.py`、`README.md`。注释与报错信息使用中文，不得修改公开 API。
