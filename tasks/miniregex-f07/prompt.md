对账对不上，想请你帮忙定位一下 miniregex（miniregex-f07）

我们把 miniregex（不使用 `re` 与任何第三方库、从零实现的迷你正则引擎（递归下降解析器 + 线性指令 + 带回溯栈的虚拟机））接进了批处理流程，上线前拿一批样本跟参考实现逐条比。抽了三轮，结论不一致的比例明显超出预期，人工核对之后归成下面几类：

- 反向引用指向未参与匹配的组时不再判失败，而是拿空串比较
- 超大的 {n,m} 计数不再被拦，可以撑出巨量指令
- . 默认不再排除换行，dot_all=False 也跨行

在仓库根目录可以直接复现：

    python3 -m unittest test_miniregex -v

现在是 6/61 条红：

    FAIL: test_backref
    FAIL: test_backref_case_insensitive
    FAIL: test_backref_repeats_last_capture
    FAIL: test_backref_to_unmatched_group_fails
    FAIL: test_dot_excludes_newline_by_default
    FAIL: test_oversized_repeat

我的判断是这几类来自不同地方——miniregex/engine.py、miniregex/parser.py 里都有嫌疑，请分别定位。要求：

1. 61 条测试全部恢复通过。测试文件不动。
2. 修复过程中这些约束不能破：
   - `(a*)*` 这类可空子表达式不能死循环，`(a+)+b` 这类模式必须抛 `MatchLimitError`，步数预算按起始位置独立计；
   - `PatternError` 要带 `pattern` / `position` / 中文说明，位置精确到出错的字符；
   - 捕获组编号、非捕获组、反向引用、捕获文本保留原文这些对外行为不能变；
   - 贪婪 / 懒惰、`^` `$` 在 `multiline` 下的语义必须与 README 的语义表一致。
3. 每类问题补一条针对性的回归测试（最好能直接复现对账时的那种输入），并在 README 里把判定口径写清楚。
4. 交付：`miniregex/engine.py`、`miniregex/parser.py`、`miniregex/classes.py`、`test_miniregex.py`、`README.md`。中文注释与中文报错，公开 API 不变。
