迁移验收单：把批处理链路从旧实现切到 miniregex（miniregex-f01）

我们准备用 miniregex（不使用 `re` 与任何第三方库、从零实现的迷你正则引擎（递归下降解析器 + 线性指令 + 带回溯栈的虚拟机））替换现在的旧实现。灰度阶段按老实现的结果做对照，验收用例跑出 5/61 条不一致，切换因此卡在这里。

对照中暴露的差异：

- 反向引用指向未参与匹配的组时不再判失败，而是拿空串比较
- 超大的 {n,m} 计数不再被拦，可以撑出巨量指令

验收命令（仓库根目录）：

    python3 -m unittest test_miniregex -v

不一致的用例：

    FAIL: test_backref
    FAIL: test_backref_case_insensitive
    FAIL: test_backref_repeats_last_capture
    FAIL: test_backref_to_unmatched_group_fails
    FAIL: test_oversized_repeat

判断：差异跨了 miniregex/engine.py、miniregex/parser.py，不是一处适配问题，需要逐个对齐语义后重新验收。

切换前必须满足：

1. 61 条验收用例全部通过，测试文件作为对照基准不得修改。
2. 切换后这些既有承诺不能被破坏（旧实现里也是这么做的）：
   - `(a*)*` 这类可空子表达式不能死循环，`(a+)+b` 这类模式必须抛 `MatchLimitError`，步数预算按起始位置独立计；
   - `PatternError` 要带 `pattern` / `position` / 中文说明，位置精确到出错的字符；
   - 捕获组编号、非捕获组、反向引用、捕获文本保留原文这些对外行为不能变；
   - 贪婪 / 懒惰、`^` `$` 在 `multiline` 下的语义必须与 README 的语义表一致。
3. 每处差异补一条回归用例，把「为什么这么判定」写进 README，避免下次切换再对不上。
4. 交付：`miniregex/engine.py`、`miniregex/parser.py`、`miniregex/classes.py`、`test_miniregex.py`、`README.md`；注释与报错保持中文，对外接口签名不变。
