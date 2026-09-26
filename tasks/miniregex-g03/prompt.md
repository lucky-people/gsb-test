“miniregex 这个包你帮我看下，我这边结果不对。”

“什么现象？”

“我列了几个，都是真跑出来的：

- 超大的 {n,m} 计数不再被拦，可以撑出巨量指令
- 反向引用指向未参与匹配的组时不再判失败，而是拿空串比较
- multiline=True 时 $ 的判定抄成了 ^ 的写法，行尾锚点错位

”

“先跑一遍测试确认下？”

“跑了，仓库根目录 `python3 -m unittest test_miniregex -v`，6/61 条红：

    ERROR: test_anchors_multiline
    FAIL: test_backref
    FAIL: test_backref_case_insensitive
    FAIL: test_backref_repeats_last_capture
    FAIL: test_backref_to_unmatched_group_fails
    FAIL: test_oversized_repeat

”

“看着不像一处问题。”

“我也这么觉得，miniregex/engine.py、miniregex/parser.py 我都翻过，几个地方都可疑。麻烦你排一下，要求是：

1. 61 条测试全部弄绿，别改测试文件——那是验收基线；
2. 这些行为不能变：
   - `(a*)*` 这类可空子表达式不能死循环，`(a+)+b` 这类模式必须抛 `MatchLimitError`，步数预算按起始位置独立计；
   - `PatternError` 要带 `pattern` / `position` / 中文说明，位置精确到出错的字符；
   - 捕获组编号、非捕获组、反向引用、捕获文本保留原文这些对外行为不能变；
   - 贪婪 / 懒惰、`^` `$` 在 `multiline` 下的语义必须与 README 的语义表一致。
3. 每处根因补一条回归测试，README 里说不清楚的地方一起补；
4. 交付 `miniregex/engine.py`、`miniregex/parser.py`、`miniregex/classes.py`、`test_miniregex.py`、`README.md`，注释和报错用中文。”
