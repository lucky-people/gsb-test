【缺陷报告】miniregex：三处独立缺陷，61 条里挂了 5 条

仓库里的 miniregex（自研迷你正则引擎）现在有 5 条测试红，分属三组不同成因：

    ERROR: test_optional_nullable_no_infinite_loop   (TestQuantifiers)
    FAIL:  test_greedy_by_default                    AssertionError: 'aa' != 'aaa'
    FAIL:  test_lazy                                 （同一组量词问题）
    FAIL:  test_group_numbering                      AssertionError: 3 != 2
    FAIL:  test_backref_to_unmatched_group_fails
    FAIL:  test_backref_repeats_last_capture

复现：

    python3 -m unittest test_miniregex -v

三组症状分别是：

第一组（量词上界）：`a{1,3}` 在 `aaaa` 上只匹配到 `aa`，也就是 `{n,m}` 的上界被当成排他处理；连带的 `test_optional_nullable_no_infinite_loop` 也被打挂。`a{2,}` 这类无上界形式不受影响。

第二组（分组编号）：模式里只要出现非捕获组 `(?:...)`，它后面的捕获组编号就整体后移——分组个数、`groups()` 的元组、`\1`…`\9` 的解析与「引用不存在的组」的校验都会跟着错，所以 `test_backref_to_unmatched_group_fails` 一起红。

第三组（回溯语义）：`(a|b)+` 这类模式在发生回溯后，捕获组里残留的是上一次迭代的边界（`test_backref_repeats_last_capture` 就是靠 `\1` 检查这一点）。匹配引擎在回退到更早的分支时必须把捕获槽恢复到当时的状态，否则 `\n` 会引用到错误的位置。

你要做的：

1. 定位并修掉三处根因，让 61 条测试全绿；不许改测试。
2. 语义要求（README 里都要写清）：
   - 量词是闭区间：`{n,m}` 最少 n 次、最多 m 次，`{n,}` 无上界，`{n}` 恰好 n 次；贪婪默认取尽、懒惰（`?` 后缀）尽量少取——`a{1,3}` 匹配 `aaa`，`a{1,3}?` 匹配 `a`。
   - 捕获组按左括号出现顺序从 1 开始编号，非捕获组 `(?:...)` 不占编号；`\n` 引用第 n 个捕获组，引用不存在的组抛 `PatternError` 且 `position` 指向反斜杠；`groups()` 只含捕获组，未参与的组为 `None`，`start(i)`/`end(i)` 对未参与的组返回 -1。
   - 回溯必须恢复捕获状态：任何一次分支回退后，捕获槽的值都要与进入该分支时一致；重复结构里同一组被多次匹配时，保留最后一次成功迭代的边界。
3. 回归验证：至少覆盖量词 `a{1,3}` / `a{3}` / `a{2,}` / `a{1,3}?`；编号 `(a)(?:b)(c)` / `(?:(a))(b)` / `(?:a)(b)(?:c)(d)` / 越界引用 `(a)\2`；回溯 `(a|b)+` 后接 `\1`、`(a+)(b+)?\2` 这类「可选组未参与」的场景。
4. 其余行为不许回退：leftmost 语义、锚点、字符类、可空重复不死循环、ReDoS 步数上限（`(a*)*b` 仍要抛 `MatchLimitError`）都保持现状。

提示：编号与量词上界分别在解析器和引擎把 AST 编译成程序的那一层；第三组要看虚拟机执行循环里回溯栈都保存了什么状态。
