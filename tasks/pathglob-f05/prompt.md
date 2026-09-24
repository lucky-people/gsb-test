PR 评审意见 —— pathglob：逻辑调整（pathglob-f05）

结论：先别合。基线在 `python3 -m unittest test_pathglob -v` 下已经红 8/56 条，逐条写在下面。

1. 字符类里的 - 被转义，[a-z] 这类区间退化成三个字面字符
2. 路径规范化不再折叠多余的斜杠，a//b 与 a/b 结论不一致
3. 段内的 * 变成可以跨目录，build/*.tmp 会命中 build/x/a.tmp

失败的用例：

    ERROR: test_batch_500x50
    FAIL: test_bracket_as_first_char_is_literal
    FAIL: test_collapses_repeated_slashes_and_dot
    FAIL: test_negated_class_both_forms
    FAIL: test_range_class
    FAIL: test_simple_class
    FAIL: test_star_does_not_cross_slash
    FAIL: test_strips_trailing_slash

几点说明：

1. 上面每一条我都在本地单独验过，症状各自独立，改一处不会让另一处跟着好。改动面看着分散在 pathglob/pattern.py、pathglob/translate.py。
2. 修的时候别动 `test_pathglob.py` 里的断言——那份测试是验收基线，写的是这个包对外承诺的行为，红了说明实现错了，不是测试写错了。
3. 下面这些约束请一起保持：
   - 同一条规则、同一个路径，`Pattern.matches`、`Matcher.match`、`Matcher.ignores` 三个入口结论必须一致；
   - `Matcher` 的求值顺序仍是「最后命中的规则说了算」，`!` 规则可以重新包含；
   - `normalize_path` 要转分隔符、折叠重复斜杠、去掉 `.` 段与结尾 `/`，并对绝对路径、盘符、`..` 抛 `PathError`；
   - 性能不许退化：`test_batch_500x50` 必须保持通过，字面量规则仍走分桶快查。
4. 每条根因都要补回归测试，别只把现有用例弄绿就算完；README 对应段落（语义说明、边界取舍）要跟实现对齐。
5. 交付范围：`pathglob/translate.py`、`pathglob/pattern.py`、`pathglob/matcher.py`、`test_pathglob.py`、`README.md`。注释与报错保持中文，公开 API 签名不要改。
