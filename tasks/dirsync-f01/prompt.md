“dirsync 这个包你帮我看下，我这边结果不对。”

“什么现象？”

“我列了几个，都是真跑出来的：

- 目标目录的现状根本没读，每次都当成空目录重建，幂等性没了
- 同一路径上 kind 变了却被判成没变，差异表里看不到

”

“先跑一遍测试确认下？”

“跑了，仓库根目录 `python3 -m unittest test_dirsync -v`，6/27 条红：

    ERROR: test_apply_and_idempotent
    ERROR: test_detects_kind_mismatch
    FAIL: test_four_categories
    FAIL: test_kind_switch_file_to_dir
    FAIL: test_prune_on_and_off
    FAIL: test_update_modified_file

”

“看着不像一处问题。”

“我也这么觉得，dirsync/apply.py、dirsync/diff.py 我都翻过，几个地方都可疑。麻烦你排一下，要求是：

1. 27 条测试全部弄绿，别改测试文件——那是验收基线；
2. 这些行为不能变：
   - `dry_run=True` 只返回报告，目标目录一个字节都不能改；
   - `prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等；
   - 动手前要核对每个待写文件的 size 与 sha256，不符就抛 `ApplyError` 且目标保持原样；
   - 写文件保持「同目录临时文件 + `os.replace`」的原子语义。
3. 每处根因补一条回归测试，README 里说不清楚的地方一起补；
4. 交付 `dirsync/apply.py`、`dirsync/paths.py`、`dirsync/diff.py`、`dirsync/manifest.py`、`test_dirsync.py`、`README.md`，注释和报错用中文。”
