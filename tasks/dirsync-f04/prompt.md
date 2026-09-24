您好，反馈一个 dirsync 的问题（工单 dirsync-f04）

我们把这个包接进了生产的处理链路，最近运维那边报了几类异常，麻烦帮忙看下。我们不是专业审代码的，只能把现象描述清楚：

- 文件是否改动只看大小，等长改写被当成没变
- 目标目录的现状根本没读，每次都当成空目录重建，幂等性没了
- 只有新建的文件会被核对，被修改的文件放过去了，源被篡改也不拦

我们自己复现的方式就是在仓库根目录跑：

    python3 -m unittest test_dirsync -v

现在 27 条里红 5 条，红的名字如下：

    ERROR: test_apply_and_idempotent
    FAIL: test_four_categories
    FAIL: test_kind_switch_file_to_dir
    FAIL: test_prune_on_and_off
    FAIL: test_update_modified_file

期望的行为其实都写在 README 里了，我们照着 README 用的。麻烦：

1. 把上面这些现象逐条修掉，让 27 条测试全部通过。测试文件请不要改动，那是我们和你们约定的验收依据。
2. 修的过程中请守住这些约束：
   - `dry_run=True` 只返回报告，目标目录一个字节都不能改；
   - `prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等；
   - 动手前要核对每个待写文件的 size 与 sha256，不符就抛 `ApplyError` 且目标保持原样；
   - 写文件保持「同目录临时文件 + `os.replace`」的原子语义。
3. 每个问题点都补一条回归测试，避免下次又回归；README 里描述不一致的地方也请一并改掉。
4. 需要交付的内容：`dirsync/apply.py`、`dirsync/paths.py`、`dirsync/diff.py`、`dirsync/manifest.py`、`test_dirsync.py`、`README.md`。注释、报错信息请保持中文。
