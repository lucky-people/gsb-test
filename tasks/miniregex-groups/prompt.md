【缺陷报告】miniregex：编号与量词上界同时出错，61 条里挂了 4 条

仓库里的 miniregex（自研迷你正则引擎）现在有 4 条测试红：

    ERROR: test_optional_nullable_no_infinite_loop
    FAIL: test_backref_to_unmatched_group_fails
    FAIL: test_group_numbering            AssertionError: 3 != 2
    FAIL: test_greedy_by_default          AssertionError: 'aa' != 'aaa'

复现：

    python3 -m unittest test_miniregex -v

两组症状都要处理，而且成因不同：

第一组（编号语义）：模式里只要出现非捕获组 `(?:...)`，它后面的捕获组编号就整体后移。受影响的不只是分组个数——`groups()` 返回的元组、`\1`…`\9` 反向引用的解析与「引用不存在的组」的校验都会跟着错，所以 `test_backref_to_unmatched_group_fails` 也一起红了。

第二组（量词上界）：`a{1,3}` 在 `aaaa` 上只匹配到 `aa`（少一层），也就是 `{n,m}` 的上界被当成排他处理了；`a{2,}` 这类无上界形式不受影响。

你要做的：

1. 修掉两处根因，让 61 条测试全绿；不许改测试。
2. 语义要求（README 里都要写清）：
   - 捕获组按左括号出现顺序从 1 开始编号，非捕获组 `(?:...)` 不占用编号；`\n` 引用第 n 个捕获组，引用不存在的组抛 `PatternError` 且 `position` 指向反斜杠；`groups()` 只包含捕获组，未参与的组用 `None` 占位，`start(i)`/`end(i)` 对未参与的组返回 -1。
   - 量词区间是闭区间：`{n,m}` 最多重复 m 次、最少 n 次，`{n,}` 无上界，`{n}` 恰好 n 次；贪婪默认取尽，懒惰（`?` 后缀）尽量少取——`a{1,3}` 匹配 `aaa`，`a{1,3}?` 匹配 `a`。
3. 回归验证：至少覆盖 `(a)(?:b)(c)`、`(?:(a))(b)`、`(?:a)(b)(?:c)(d)`、`(a)(?:b)\1`、越界引用 `(a)\2`，以及量词的 `a{1,3}` / `a{3}` / `a{2,}` / `a{1,3}?` 四种形态。
4. 其余行为不许回退：选择分支的 leftmost 语义、锚点、字符类、可空重复不死循环、ReDoS 步数上限（`(a*)*b` 仍要抛 `MatchLimitError`）都保持现状；修复后 `test_optional_nullable_no_infinite_loop` 也要恢复通过（它是被量词上界的 bug 连带打挂的）。

提示：编号的事在解析器处理 `(` 的那段；量词展开在引擎把 AST 编译成程序的那段，注意「至少 n 次」和「最多 m 次」分别由哪一层负责。
