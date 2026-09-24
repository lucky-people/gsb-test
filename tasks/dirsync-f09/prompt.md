# 回归批次 dirsync-f09：dirsync 用例执行报告

被测对象：dirsync（按清单把目标目录同步成与源目录一致的目录同步工具（快照 / 差异 / 应用三层，支持 ignore 规则与 prune））
执行方式：仓库根目录 `python3 -m unittest test_dirsync -v`
结果：5/27 失败，判定为**不通过**。

## 失败用例明细

| # | 类型 | 用例 |
|---|---|---|
| 1 | ERROR | test_detects_kind_mismatch |
| 2 | FAIL | test_four_categories |
| 3 | FAIL | test_illegal_paths |
| 4 | ERROR | test_kind_switch_file_to_dir |
| 5 | FAIL | test_order_last_match_wins_and_reinclude |

## 缺陷归类

| 编号 | 缺陷描述 |
|---|---|
| 1 | 忽略规则变成「第一条命中就返回」，后面的规则与 ! 重新包含全部失效 |
| 2 | 同一路径上 kind 变了却被判成没变，差异表里看不到 |
| 3 | 文件与目录互相切换时旧节点没先删掉，创建阶段直接撞车 |
| 4 | 反斜杠路径不再被拦，非法路径静默进了清单 |

归类依据：同一类缺陷在多条用例上重复出现，且分布在不同模块（dirsync/apply.py、dirsync/diff.py、dirsync/paths.py），因此判定为多处独立根因，而不是单一 bug 的连带影响。

## 修复要求

1. 让 27 条用例全部通过；测试文件为本批次的判定依据，禁止修改。
2. 修复后需满足下列行为约定：
   - `dry_run=True` 只返回报告，目标目录一个字节都不能改；
   - `prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等；
   - 动手前要核对每个待写文件的 size 与 sha256，不符就抛 `ApplyError` 且目标保持原样；
   - 写文件保持「同目录临时文件 + `os.replace`」的原子语义。
3. 每一类缺陷补充对应回归用例，并保证新用例同样稳定通过。
4. 交付物：`dirsync/apply.py`、`dirsync/paths.py`、`dirsync/diff.py`、`dirsync/manifest.py`、`test_dirsync.py`、`README.md`；注释与报错信息使用中文，公开 API 不得变更。
