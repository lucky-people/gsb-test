# 回归批次 pathglob-g05：pathglob 用例执行报告

被测对象：pathglob（gitignore 风格相对路径匹配库（模式翻译成正则 + 字面量分桶加速，默认大小写不敏感））
执行方式：仓库根目录 `python3 -m unittest test_pathglob -v`
结果：5/56 失败，判定为**不通过**。

## 失败用例明细

| # | 类型 | 用例 |
|---|---|---|
| 1 | FAIL | test_consecutive_double_star_collapses |
| 2 | FAIL | test_double_star_crosses_directories |
| 3 | FAIL | test_escape_in_anchored_rule |
| 4 | FAIL | test_middle_slash_anchors_to_root |
| 5 | FAIL | test_negated_class_never_matches_slash |

## 缺陷归类

| 编号 | 缺陷描述 |
|---|---|
| 1 | 取反字符类开始匹配路径分隔符，[!x] 能吃下整条路径 |
| 2 | 中间的 /**/ 要求至少一层目录，a/**/b 匹配不到 a/b |
| 3 | 中间含斜杠的模式不再锚定到仓库根 |

归类依据：同一类缺陷在多条用例上重复出现，且分布在不同模块（pathglob/pattern.py、pathglob/translate.py），因此判定为多处独立根因，而不是单一 bug 的连带影响。

## 修复要求

1. 让 56 条用例全部通过；测试文件为本批次的判定依据，禁止修改。
2. 修复后需满足下列行为约定：
   - 同一条规则、同一个路径，`Pattern.matches`、`Matcher.match`、`Matcher.ignores` 三个入口结论必须一致；
   - `Matcher` 的求值顺序仍是「最后命中的规则说了算」，`!` 规则可以重新包含；
   - `normalize_path` 要转分隔符、折叠重复斜杠、去掉 `.` 段与结尾 `/`，并对绝对路径、盘符、`..` 抛 `PathError`；
   - 性能不许退化：`test_batch_500x50` 必须保持通过，字面量规则仍走分桶快查。
3. 每一类缺陷补充对应回归用例，并保证新用例同样稳定通过。
4. 交付物：`pathglob/translate.py`、`pathglob/pattern.py`、`pathglob/matcher.py`、`test_pathglob.py`、`README.md`；注释与报错信息使用中文，公开 API 不得变更。
