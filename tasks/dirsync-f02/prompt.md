# 事故复盘：dirsync 相关链路异常（dirsync-f02）

事故简述：下游今天反馈，dirsync 在处理真实输入时结果不对，一部分直接抛异常炸在半路。我们内部先按最小复现跑了一遍，确认不是环境问题。

这个包是按清单把目标目录同步成与源目录一致的目录同步工具（快照 / 差异 / 应用三层，支持 ignore 规则与 prune），目前的问题集中在它的核心逻辑上。

初判的影响面，按严重程度排：

- 目标目录的现状根本没读，每次都当成空目录重建，幂等性没了
- 忽略规则变成「第一条命中就返回」，后面的规则与 ! 重新包含全部失效

复现命令（仓库根目录）：

    python3 -m unittest test_dirsync -v

现在 27 条里红 5 条：

    ERROR: test_apply_and_idempotent
    FAIL: test_kind_switch_file_to_dir
    FAIL: test_order_last_match_wins_and_reinclude
    FAIL: test_prune_on_and_off
    FAIL: test_update_modified_file

我看下来这不像一处原因，至少分布在 dirsync/apply.py、dirsync/paths.py 这几个文件里，修一处另一处仍会红。请你：

1. 定位并修掉全部根因，让 27 条测试全绿。不许改测试、删断言，也不许把校验放宽或注释掉来「让它过」。
2. 这些不变量必须继续成立：
   - `dry_run=True` 只返回报告，目标目录一个字节都不能改；
   - `prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等；
   - 动手前要核对每个待写文件的 size 与 sha256，不符就抛 `ApplyError` 且目标保持原样；
   - 写文件保持「同目录临时文件 + `os.replace`」的原子语义。
3. 每处根因补至少一条回归测试；README 里与本次改动相关的小节要同步改到与实现一致。
4. 修完请用同一条命令复跑确认，并在 README 里写明本次修复涉及哪几条语义。

交付：`dirsync/apply.py`、`dirsync/paths.py`、`dirsync/diff.py`、`dirsync/manifest.py`、`test_dirsync.py`、`README.md`。注释与报错信息保持中文，公开 API 与已有行为不要动。
