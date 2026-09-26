# 需求单：对齐 dirsync 的对外语义（dirsync-g04）

背景：我们把 dirsync 当成基础设施接进了业务链路（按清单把目标目录同步成与源目录一致的目录同步工具（快照 / 差异 / 应用三层，支持 ignore 规则与 prune））。接入测试发现它的实现与我们按 README 理解的语义不一致，先把不一致的地方列出来。

## 现象清单

| 编号 | 现象 |
|---|---|
| 1 | 同一路径上 kind 变了却被判成没变，差异表里看不到 |
| 2 | 目标目录的现状根本没读，每次都当成空目录重建，幂等性没了 |
| 3 | 反斜杠路径不再被拦，非法路径静默进了清单 |

## 复现与失败用例

    python3 -m unittest test_dirsync -v

当前 7/27 条失败：

    FAIL: test_apply_and_idempotent
    FAIL: test_detects_kind_mismatch
    FAIL: test_four_categories
    FAIL: test_illegal_paths
    ERROR: test_kind_switch_file_to_dir
    FAIL: test_prune_on_and_off
    FAIL: test_update_modified_file

## 验收要求

1. 以上现象全部消除，27 条测试全绿；测试文件是验收基线，不允许修改或删除断言。
2. 实现必须满足下列硬性约束：
   - `dry_run=True` 只返回报告，目标目录一个字节都不能改；
   - `prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等；
   - 动手前要核对每个待写文件的 size 与 sha256，不符就抛 `ApplyError` 且目标保持原样；
   - 写文件保持「同目录临时文件 + `os.replace`」的原子语义。
3. 每条现象对应一处独立根因（预计分布在 dirsync/apply.py、dirsync/diff.py、dirsync/paths.py），请逐一定位；只改一处会有用例继续红。
4. 为每处根因补回归测试；README 里与本需求相关的语义说明要与实现一致。
5. 交付物：`dirsync/apply.py`、`dirsync/paths.py`、`dirsync/diff.py`、`dirsync/manifest.py`、`test_dirsync.py`、`README.md`。注释与报错信息使用中文，不得修改公开 API。
