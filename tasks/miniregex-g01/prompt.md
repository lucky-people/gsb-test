# 回归批次 miniregex-g01：miniregex 用例执行报告

被测对象：miniregex（不使用 `re` 与任何第三方库、从零实现的迷你正则引擎（递归下降解析器 + 线性指令 + 带回溯栈的虚拟机））
执行方式：仓库根目录 `python3 -m unittest test_miniregex -v`
结果：5/61 失败，判定为**不通过**。

## 失败用例明细

| # | 类型 | 用例 |
|---|---|---|
| 1 | FAIL | test_backref |
| 2 | FAIL | test_backref_case_insensitive |
| 3 | FAIL | test_backref_repeats_last_capture |
| 4 | FAIL | test_backref_to_unmatched_group_fails |
| 5 | FAIL | test_zero_backref |

## 缺陷归类

| 编号 | 缺陷描述 |
|---|---|
| 1 | \0 这个非法反向引用不再报 PatternError |
| 2 | 反向引用指向未参与匹配的组时不再判失败，而是拿空串比较 |

归类依据：同一类缺陷在多条用例上重复出现，且分布在不同模块（miniregex/engine.py、miniregex/parser.py），因此判定为多处独立根因，而不是单一 bug 的连带影响。

## 修复要求

1. 让 61 条用例全部通过；测试文件为本批次的判定依据，禁止修改。
2. 修复后需满足下列行为约定：
   - `(a*)*` 这类可空子表达式不能死循环，`(a+)+b` 这类模式必须抛 `MatchLimitError`，步数预算按起始位置独立计；
   - `PatternError` 要带 `pattern` / `position` / 中文说明，位置精确到出错的字符；
   - 捕获组编号、非捕获组、反向引用、捕获文本保留原文这些对外行为不能变；
   - 贪婪 / 懒惰、`^` `$` 在 `multiline` 下的语义必须与 README 的语义表一致。
3. 每一类缺陷补充对应回归用例，并保证新用例同样稳定通过。
4. 交付物：`miniregex/engine.py`、`miniregex/parser.py`、`miniregex/classes.py`、`test_miniregex.py`、`README.md`；注释与报错信息使用中文，公开 API 不得变更。
