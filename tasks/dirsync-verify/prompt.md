PR《dirsync：补上增量校验与 prune 开关》我审完了，先别合，下面几条得先回去改。

整体方向没问题，但这版把几处已经承诺出去的语义改坏或者漏掉了，而且测试就是照着那些语义写的，现在 `python3 -m unittest test_dirsync -v` 是红的：

    FAIL:  test_prune_on_and_off
    FAIL:  test_source_tampered_raises_and_untouched
    FAIL:  test_detects_kind_mismatch
    FAIL:  test_detects_tamper_missing_and_extra
    ERROR: test_symlink_recorded_with_target

最后那条 ERROR 先说明一下：它在 Windows 上是因为当前用户没有创建符号链接的权限，跟这次改动无关，Linux/WSL 下是正常通过的，你不用管它。剩下四条是真问题。

四条意见：

第一，`prune=False` 这个开关现在等于没有。调用方用它表达「目标目录里多出来的条目留着别动」，现在照样给你删了；`deleted` 报告也照报。这不是小事，我们有个工具就是拿 `prune=False` 做保守同步的。

第二，动手之前的那道校验窄了。原来的约定是：清单里每一个「这次要写过去」的文件，动手前都要核对源文件的大小与 sha256，任何一个不符就抛 `ApplyError`，并且**此时磁盘上什么都没改**。现在只有新建的文件会被核到，内容被改过的文件被直接放过去——`test_source_tampered_raises_and_untouched` 就是为这条写的，它现在还要求失败后目标文件内容原封不动。

第三，`verify()` 的返回值语义被你改小了。它的职责是「列出目标目录里一切与清单不符的路径」，包括内容被篡改的、缺失的、多余的、以及 kind 不对的（文件位置变成了目录之类）。现在内容和 kind 这两类都不报了，只剩下增删。

第四条我在本地跑了一下，是上面几条修完之后要顺带确认的：连续两次 `apply` 必须幂等（第二次 `created`/`updated`/`deleted` 都为空）；`dry_run=True` 时目标目录一个字节都不能动；写文件仍是「同目录临时文件 + `os.replace`」的原子语义，别为了绕开校验改成直接原地写。

改完请做到：

1. 上面 27 条测试在 Linux/WSL 下全绿（Windows 下除了那条符号链接用例之外也全绿）。不许改测试。
2. 补四条回归测试：`prune=False` 时多余的文件与目录都保留、`prune=True` 时它们被删且出现在 `deleted` 里；源文件在快照之后被改动时抛 `ApplyError` 且目标原样；`verify()` 能报出同长度与不同长度的内容篡改；`file -> dir` 与 `dir -> file` 的 kind 切换都能自愈。
3. README 的「apply 语义」与「verify 语义」两节要和改完的实现一致，把 `prune`、`dry_run`、以及「校验失败时目标不动」这三条写成明确承诺。

交付：`dirsync/apply.py`、`dirsync/diff.py`（如需）、`test_dirsync.py`、`README.md`。注释与报错保持中文，公开函数签名不要动。
