# 回归批次 cronspec-f02：cronspec 用例执行报告

被测对象：cronspec（纯标准库实现的 Cron 表达式解析与触发时间计算引擎（按字段推进搜索，不逐分钟扫描））
执行方式：仓库根目录 `python3 -m unittest test_cronspec -v`
结果：9/35 失败，判定为**不通过**。

## 失败用例明细

| # | 类型 | 用例 |
|---|---|---|
| 1 | ERROR | test_cross_year |
| 2 | FAIL | test_day_31_skipping |
| 3 | FAIL | test_later_today_versus_later_day |
| 4 | ERROR | test_leap_day |
| 5 | FAIL | test_minute_boundaries |
| 6 | FAIL | test_seconds_input_advances_to_next_trigger |
| 7 | FAIL | test_sparse_schedules_1000_in_one_second |
| 8 | FAIL | test_strictly_after_and_immutable_input |
| 9 | FAIL | test_strictly_ascending_unique |

## 缺陷归类

| 编号 | 缺陷描述 |
|---|---|
| 1 | 闰年只按能不能被 4 整除判，整百年被误判 |
| 2 | 「大于等于 value 的最小值」被写成严格大于，正好命中的取值被跳过 |

归类依据：同一类缺陷在多条用例上重复出现，且分布在不同模块（cronspec/engine.py、cronspec/fields.py），因此判定为多处独立根因，而不是单一 bug 的连带影响。

## 修复要求

1. 让 35 条用例全部通过；测试文件为本批次的判定依据，禁止修改。
2. 修复后需满足下列行为约定：
   - `next_after` 严格晚于入参且不修改入参，`next_n` 升序且不重复，`n <= 0` 抛 `ValueError`；
   - `matches` 在秒或微秒不为 0 时返回 False，带 `tzinfo` 的入参抛 `TypeError`；
   - 不存在触发时刻的表达式（如 `0 0 30 2 *`）抛 `NoMatchingTimeError`，不许死循环；
   - 日与星期都显式限定时取并集（POSIX/vixie 约定）；稀疏表达式取 1000 个触发时刻仍要在 1 秒量级完成。
3. 每一类缺陷补充对应回归用例，并保证新用例同样稳定通过。
4. 交付物：`cronspec/engine.py`、`cronspec/fields.py`、`cronspec/parser.py`、`test_cronspec.py`、`README.md`；注释与报错信息使用中文，公开 API 不得变更。
