【用户报障】dirsync：忽略规则里的 `!` 重新包含突然不生效了

我们的目录同步工具 dirsync 支持类似 .gitignore 的忽略规则，一直用这套：

    ["*.log", "!logs/keep.log"]

预期 `logs/keep.log` 被重新包含、出现在清单里，实际它被漏掉了。测试里正好有一条覆盖这个场景，现在是红的：

    FAIL: test_order_last_match_wins_and_reinclude (test_dirsync.TestIgnoreRules...)
    AssertionError: 'logs/keep.log' not found in ['build', 'build/out.bin', 'keep.txt', 'logs', 'src', ...]
    ----------------------------------------------------------------------
    Ran 27 tests in 0.454s
    FAILED (failures=1, errors=1)

复现：

    python3 -m unittest test_dirsync -v
    # 27 条里这条失败；另有一条符号链接用例在 Windows 上会因为权限报 OSError，
    # 在 WSL/Linux 下正常，与本次缺陷无关，不用管它

你要做的：

1. 修掉根因，让 `python3 -m unittest test_dirsync` 在 Linux/WSL 下 27 条全绿；不许改测试。
2. 语义要求（README 里也要写清）：规则按书写顺序逐条求值，**最后一条匹配的规则**决定结果；普通规则表示忽略，`!` 前缀表示重新包含；不带 `/` 的规则同时匹配完整相对路径与 basename；以 `/` 结尾的规则匹配该目录本身及其整棵子树。
3. 回归验证：至少补三条测试——`["*.log", "!logs/keep.log"]`（重新包含生效）、`["!keep.txt", "*.txt"]`（后面的普通规则覆盖前面的 `!`）、以及三条以上规则的混合顺序；同时确认目录规则、basename 匹配、大小写敏感度这些行为没有变化。
4. 不许用「把 `!` 规则一律提到最高优先级」这类取巧做法蒙混，顺序语义必须严格按上面的定义。
5. 对照 README 的忽略规则一节，与实现不一致的地方以语义要求为准改文档。

提示：先想清楚「规则顺序」与「规则优先级」的区别，再看当前求值循环是不是在第一个命中的规则处就返回了。
