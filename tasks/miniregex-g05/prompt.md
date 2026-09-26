PR 评审意见 —— miniregex：逻辑调整（miniregex-g05）

结论：先别合。基线在 `python3 -m unittest test_miniregex -v` 下已经红 5/61 条，逐条写在下面。

1. 反向引用指向未参与匹配的组时不再判失败，而是拿空串比较
2. 大小写不敏感模式下反向引用按原样比较，Aa 这类匹配被漏掉
3. \0 这个非法反向引用不再报 PatternError

失败的用例：

    FAIL: test_backref
    FAIL: test_backref_case_insensitive
    FAIL: test_backref_repeats_last_capture
    FAIL: test_backref_to_unmatched_group_fails
    FAIL: test_zero_backref

几点说明：

1. 上面每一条我都在本地单独验过，症状各自独立，改一处不会让另一处跟着好。改动面看着分散在 miniregex/engine.py、miniregex/parser.py。
2. 修的时候别动 `test_miniregex.py` 里的断言——那份测试是验收基线，写的是这个包对外承诺的行为，红了说明实现错了，不是测试写错了。
3. 下面这些约束请一起保持：
   - `(a*)*` 这类可空子表达式不能死循环，`(a+)+b` 这类模式必须抛 `MatchLimitError`，步数预算按起始位置独立计；
   - `PatternError` 要带 `pattern` / `position` / 中文说明，位置精确到出错的字符；
   - 捕获组编号、非捕获组、反向引用、捕获文本保留原文这些对外行为不能变；
   - 贪婪 / 懒惰、`^` `$` 在 `multiline` 下的语义必须与 README 的语义表一致。
4. 每条根因都要补回归测试，别只把现有用例弄绿就算完；README 对应段落（语义说明、边界取舍）要跟实现对齐。
5. 交付范围：`miniregex/engine.py`、`miniregex/parser.py`、`miniregex/classes.py`、`test_miniregex.py`、`README.md`。注释与报错保持中文，公开 API 签名不要改。
