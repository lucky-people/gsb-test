[CI] miniregex 流水线红灯 · job: unittest-test_miniregex · miniregex-f09

step 1/2  checkout ................................ 成功
step 2/2  python3 -m unittest test_miniregex -v ...... 失败（6/61）

日志尾部：

    ERROR: test_anchors_multiline
    FAIL: test_backref
    FAIL: test_backref_case_insensitive
    FAIL: test_backref_repeats_last_capture
    FAIL: test_backref_to_unmatched_group_fails
    FAIL: test_zero_backref

构建机结论：本次改动之后基线不再全绿，需要修复后重新触发流水线。

失败分布提示（本地复跑时确认过，症状互不相关）：

- 反向引用指向未参与匹配的组时不再判失败，而是拿空串比较
- \0 这个非法反向引用不再报 PatternError
- multiline=True 时 $ 的判定抄成了 ^ 的写法，行尾锚点错位
- multiline=True 时 ^ 只在整段文本开头认，每行行首失效

受影响文件：miniregex/engine.py、miniregex/parser.py

解这个 job 的要求：

1. 让 `python3 -m unittest test_miniregex -v` 在干净检出后全绿；不允许改动测试文件，也不允许用跳过（skip）或放宽断言的方式让流水线变绿。
2. 流水线里其它 job 依赖的行为不能退化：
   - `(a*)*` 这类可空子表达式不能死循环，`(a+)+b` 这类模式必须抛 `MatchLimitError`，步数预算按起始位置独立计；
   - `PatternError` 要带 `pattern` / `position` / 中文说明，位置精确到出错的字符；
   - 捕获组编号、非捕获组、反向引用、捕获文本保留原文这些对外行为不能变；
   - 贪婪 / 懒惰、`^` `$` 在 `multiline` 下的语义必须与 README 的语义表一致。
3. 每处根因补回归测试；README 的相应章节需要同步更新，否则文档 job 下一轮还会红。
4. 改动范围：`miniregex/engine.py`、`miniregex/parser.py`、`miniregex/classes.py`、`test_miniregex.py`、`README.md`。中文注释与中文报错。
