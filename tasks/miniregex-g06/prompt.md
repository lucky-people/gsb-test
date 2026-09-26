您好，反馈一个 miniregex 的问题（工单 miniregex-g06）

我们把这个包接进了生产的处理链路，最近运维那边报了几类异常，麻烦帮忙看下。我们不是专业审代码的，只能把现象描述清楚：

- \0 这个非法反向引用不再报 PatternError
- multiline=True 时 $ 的判定抄成了 ^ 的写法，行尾锚点错位
- 超大的 {n,m} 计数不再被拦，可以撑出巨量指令
- 星号类量词后缀的 ? 被忽略，懒惰量词全变贪婪

我们自己复现的方式就是在仓库根目录跑：

    python3 -m unittest test_miniregex -v

现在 61 条里红 5 条，红的名字如下：

    ERROR: test_anchors_multiline
    FAIL: test_lazy
    FAIL: test_lazy_vs_greedy_search
    FAIL: test_oversized_repeat
    FAIL: test_zero_backref

期望的行为其实都写在 README 里了，我们照着 README 用的。麻烦：

1. 把上面这些现象逐条修掉，让 61 条测试全部通过。测试文件请不要改动，那是我们和你们约定的验收依据。
2. 修的过程中请守住这些约束：
   - `(a*)*` 这类可空子表达式不能死循环，`(a+)+b` 这类模式必须抛 `MatchLimitError`，步数预算按起始位置独立计；
   - `PatternError` 要带 `pattern` / `position` / 中文说明，位置精确到出错的字符；
   - 捕获组编号、非捕获组、反向引用、捕获文本保留原文这些对外行为不能变；
   - 贪婪 / 懒惰、`^` `$` 在 `multiline` 下的语义必须与 README 的语义表一致。
3. 每个问题点都补一条回归测试，避免下次又回归；README 里描述不一致的地方也请一并改掉。
4. 需要交付的内容：`miniregex/engine.py`、`miniregex/parser.py`、`miniregex/classes.py`、`test_miniregex.py`、`README.md`。注释、报错信息请保持中文。
