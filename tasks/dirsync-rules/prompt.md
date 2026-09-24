【用户报障】dirsync：忽略规则失灵 + dry_run 动了盘，27 条里挂了 5 条

我们的目录同步工具 dirsync 现在问题不少，测试红了 5 条：

    FAIL: test_fnmatch_star_not_cross_slash
    FAIL: test_double_star_crosses_dirs
    FAIL: test_order_last_match_wins_and_reinclude
      AssertionError: 'drop.log' unexpectedly found in ['build', 'build/out.bin', 'drop.log', 'keep.txt', 'logs', ...]
    FAIL: test_dry_run_changes_nothing
    ERROR: test_symlink_recorded_with_target

复现：

    python3 -m unittest test_dirsync -v
    # test_symlink_recorded_with_target 在 Windows 上会因为创建符号链接缺少权限报 OSError，
    # 在 WSL/Linux 下正常，与本次缺陷无关

三组症状，成因不同：

一是**文件类规则被跳过**：`*.log`、`*.tmp` 这类针对文件的规则对文件不再起作用（`drop.log` 出现在清单里），而针对目录的规则表面上还有效——过滤发生在哪一层出了问题。

二是**重新包含失效**：`["*.log", "!logs/keep.log"]` 里 `logs/keep.log` 被漏掉，也就是「按顺序求值、最后一条匹配的规则说了算」没有落实。

三是**`dry_run` 破坏了只读约定**：`apply(..., dry_run=True)` 现在会真的改目标目录。这是对外承诺的语义（「只计算报告，不改磁盘」），比前两组更危险——调用方用它做预览，结果把线上目录改了。

你要做的：

1. 修掉三处根因，让 `python3 -m unittest test_dirsync` 在 Linux/WSL 下 27 条全绿；不许改测试。
2. 语义要求（README 里都要写清并给例子）：
   - 规则按书写顺序逐条求值，**最后一条匹配的规则**决定结果；普通规则表示忽略，`!` 前缀表示重新包含；不带 `/` 的规则同时匹配完整相对路径与 basename；`*` 不跨 `/`、`?` 不跨 `/`、`**` 可跨目录；以 `/` 结尾的规则匹配该目录本身及其整棵子树；文件与目录都要参与判定（目录规则命中即剪掉整棵子树）。
   - `dry_run=True` 时只返回报告，目标目录一个字节都不能改；`prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等（第二次 `created`/`updated`/`deleted` 都为空）。
   - 源文件在 snapshot 之后被改动时，必须在动手之前抛 `ApplyError`，且目标目录保持原样；写文件保持「同目录临时文件 + `os.replace`」的原子语义。
3. 回归验证：至少补四条测试——`["*.log", "!logs/keep.log"]`（重新包含生效）、`["!keep.txt", "*.txt"]`（后面的普通规则覆盖前面的 `!`）、`["*.tmp", "**/cache/", "!cache/keep.tmp"]`（三条以上混合顺序）、以及 dry_run 下目标目录的 mtime 与内容都不变。
4. 不许用「把 `!` 规则一律提到最高优先级」这类取巧做法蒙混，顺序语义必须严格按上面的定义。
5. 对照 README 的忽略规则与 apply 语义两节，与实现不一致的地方以语义要求为准改文档。

提示：规则怎么求值在 `paths.py`，规则在何处被调用、何时被跳过在 `manifest.py`，`dry_run` 的分支在 `apply.py`——三处都要看，只改一处仍会红。
