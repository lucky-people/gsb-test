先跟你同步一下 dirsync 这摊事（dirsync-g06），我这边要交出去了。

情况是：dirsync 是按清单把目标目录同步成与源目录一致的目录同步工具（快照 / 差异 / 应用三层，支持 ignore 规则与 prune）。最近在真实输入上出了问题，我查了一半没查完，跑测试是红的：

    python3 -m unittest test_dirsync -v

5/27 条失败：

    FAIL: test_detects_kind_mismatch
    FAIL: test_dry_run_changes_nothing
    FAIL: test_four_categories
    ERROR: test_kind_switch_file_to_dir
    FAIL: test_order_last_match_wins_and_reinclude

我没查完的点，按我的笔记抄给你：

- 同一路径上 kind 变了却被判成没变，差异表里看不到
- dry_run=True 直接落盘，预览变成了真同步
- 忽略规则变成「第一条命中就返回」，后面的规则与 ! 重新包含全部失效

我已经排除的因素：跟环境、依赖没关系，纯标准库，装上就能跑；也不是测试写错。我怀疑是好几个地方一起坏了，dirsync/apply.py、dirsync/diff.py、dirsync/paths.py 都得看。

拜托你做到：

1. 27 条测试全绿，别去改测试文件里的断言。
2. 这些约束别弄丢：
   - `dry_run=True` 只返回报告，目标目录一个字节都不能改；
   - `prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等；
   - 动手前要核对每个待写文件的 size 与 sha256，不符就抛 `ApplyError` 且目标保持原样；
   - 写文件保持「同目录临时文件 + `os.replace`」的原子语义。
3. 每一处根因补一条回归测试，顺手把 README 里说得含糊或者跟实现不一致的地方改掉。
4. 交付：`dirsync/apply.py`、`dirsync/paths.py`、`dirsync/diff.py`、`dirsync/manifest.py`、`test_dirsync.py`、`README.md`，注释和报错保持中文。

辛苦了。
