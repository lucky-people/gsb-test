# 事故复盘：miniregex 相关链路异常（miniregex-f03）

事故简述：下游今天反馈，miniregex 在处理真实输入时结果不对，一部分直接抛异常炸在半路。我们内部先按最小复现跑了一遍，确认不是环境问题。

这个包是不使用 `re` 与任何第三方库、从零实现的迷你正则引擎（递归下降解析器 + 线性指令 + 带回溯栈的虚拟机），目前的问题集中在它的核心逻辑上。

初判的影响面，按严重程度排：

- 反向引用指向未参与匹配的组时不再判失败，而是拿空串比较
- multiline=True 时 $ 的判定抄成了 ^ 的写法，行尾锚点错位
- 量词前面没有原子时不再报错，直接当字面量吃掉

复现命令（仓库根目录）：

    python3 -m unittest test_miniregex -v

现在 61 条里红 6 条：

    ERROR: test_anchors_multiline
    FAIL: test_backref
    FAIL: test_backref_case_insensitive
    FAIL: test_backref_repeats_last_capture
    FAIL: test_backref_to_unmatched_group_fails
    FAIL: test_quantifier_without_atom

我看下来这不像一处原因，至少分布在 miniregex/engine.py、miniregex/parser.py 这几个文件里，修一处另一处仍会红。请你：

1. 定位并修掉全部根因，让 61 条测试全绿。不许改测试、删断言，也不许把校验放宽或注释掉来「让它过」。
2. 这些不变量必须继续成立：
   - `(a*)*` 这类可空子表达式不能死循环，`(a+)+b` 这类模式必须抛 `MatchLimitError`，步数预算按起始位置独立计；
   - `PatternError` 要带 `pattern` / `position` / 中文说明，位置精确到出错的字符；
   - 捕获组编号、非捕获组、反向引用、捕获文本保留原文这些对外行为不能变；
   - 贪婪 / 懒惰、`^` `$` 在 `multiline` 下的语义必须与 README 的语义表一致。
3. 每处根因补至少一条回归测试；README 里与本次改动相关的小节要同步改到与实现一致。
4. 修完请用同一条命令复跑确认，并在 README 里写明本次修复涉及哪几条语义。

交付：`miniregex/engine.py`、`miniregex/parser.py`、`miniregex/classes.py`、`test_miniregex.py`、`README.md`。注释与报错信息保持中文，公开 API 与已有行为不要动。
