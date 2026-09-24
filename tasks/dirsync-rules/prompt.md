【用户报障】dirsync：忽略规则整体失灵，27 条里挂了 4 条

我们的目录同步工具 dirsync 支持类似 .gitignore 的忽略规则，现在规则基本不生效了，测试红了一片：

    FAIL: test_fnmatch_star_not_cross_slash
    FAIL: test_double_star_crosses_dirs
    FAIL: test_order_last_match_wins_and_reinclude
      AssertionError: 'drop.log' unexpectedly found in ['build', 'build/out.bin', 'drop.log', 'keep.txt', 'logs', ...]
    ERROR: test_symlink_recorded_with_target

复现：

    python3 -m unittest test_dirsync -v
    # 其中 test_symlink_recorded_with_target 在 Windows 上会因为创建符号链接缺少权限报 OSError，
    # 在 WSL/Linux 下正常，与本次缺陷无关，可以忽略它

两组症状，成因不同：

一是**文件类规则被跳过**：`*.log`、`*.tmp` 这类针对文件的规则对文件不再起作用（`drop.log` 出现在清单里），而针对目录的规则表面上还在生效——说明过滤发生在哪一层出了问题。

二是**重新包含失效**：`["*.log", "!logs/keep.log"]` 这种写法里，`logs/keep.log` 被漏掉了；也就是「多条规则按顺序求值、最后一条匹配的规则说了算」这条语义没有落实。

你要做的：

1. 修掉两处根因，让 `python3 -m unittest test_dirsync` 在 Linux/WSL 下 27 条全绿（Windows 上除了那条符号链接权限错误之外也应只剩它）；不许改测试。
2. 语义要求（README 里要写清，并给例子）：
   - 规则按书写顺序逐条求值，**最后一条匹配的规则**决定结果；普通规则表示忽略，`!` 前缀表示重新包含；
   - 不带 `/` 的规则同时匹配完整相对路径与 basename；`*` 不跨 `/`、`?` 不跨 `/`、`**` 可跨目录；
   - 以 `/` 结尾的规则匹配该目录本身及其整棵子树；
   - 文件与目录都要参与规则判定（目录规则命中即剪掉整棵子树）。
3. 回归验证：至少补三条测试——`["*.log", "!logs/keep.log"]`（重新包含生效）、`["!keep.txt", "*.txt"]`（后面的普通规则覆盖前面的 `!`）、以及 `["*.tmp", "**/cache/", "!cache/keep.tmp"]` 这种三条以上混合顺序；同时确认目录规则与 basename 匹配没有变化。
4. 不许用「把 `!` 规则一律提到最高优先级」这类取巧做法蒙混，顺序语义必须严格按上面的定义。
5. 对照 README 的忽略规则一节，与实现不一致的地方以语义要求为准改文档。

提示：规则怎么求值在 `paths.py`，规则在什么地方被调用、什么时候被跳过在 `manifest.py`——两处都要看，只改一处仍会红。
