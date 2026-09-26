PR 评审意见 —— dirsync：逻辑调整（dirsync-g02）

结论：先别合。基线在 `python3 -m unittest test_dirsync -v` 下已经红 5/27 条，逐条写在下面。

1. 目标目录的现状根本没读，每次都当成空目录重建，幂等性没了
2. 反斜杠路径不再被拦，非法路径静默进了清单

失败的用例：

    FAIL: test_apply_and_idempotent
    FAIL: test_illegal_paths
    ERROR: test_kind_switch_file_to_dir
    FAIL: test_prune_on_and_off
    FAIL: test_update_modified_file

几点说明：

1. 上面每一条我都在本地单独验过，症状各自独立，改一处不会让另一处跟着好。改动面看着分散在 dirsync/apply.py、dirsync/paths.py。
2. 修的时候别动 `test_dirsync.py` 里的断言——那份测试是验收基线，写的是这个包对外承诺的行为，红了说明实现错了，不是测试写错了。
3. 下面这些约束请一起保持：
   - `dry_run=True` 只返回报告，目标目录一个字节都不能改；
   - `prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等；
   - 动手前要核对每个待写文件的 size 与 sha256，不符就抛 `ApplyError` 且目标保持原样；
   - 写文件保持「同目录临时文件 + `os.replace`」的原子语义。
4. 每条根因都要补回归测试，别只把现有用例弄绿就算完；README 对应段落（语义说明、边界取舍）要跟实现对齐。
5. 交付范围：`dirsync/apply.py`、`dirsync/paths.py`、`dirsync/diff.py`、`dirsync/manifest.py`、`test_dirsync.py`、`README.md`。注释与报错保持中文，公开 API 签名不要改。
