对账对不上，想请你帮忙定位一下 dirsync（dirsync-f06）

我们把 dirsync（按清单把目标目录同步成与源目录一致的目录同步工具（快照 / 差异 / 应用三层，支持 ignore 规则与 prune））接进了批处理流程，上线前拿一批样本跟参考实现逐条比。抽了三轮，结论不一致的比例明显超出预期，人工核对之后归成下面几类：

- 忽略规则变成「第一条命中就返回」，后面的规则与 ! 重新包含全部失效
- 文件是否改动只看大小，等长改写被当成没变
- 目标目录的现状根本没读，每次都当成空目录重建，幂等性没了

在仓库根目录可以直接复现：

    python3 -m unittest test_dirsync -v

现在是 6/27 条红：

    ERROR: test_apply_and_idempotent
    FAIL: test_four_categories
    FAIL: test_kind_switch_file_to_dir
    FAIL: test_order_last_match_wins_and_reinclude
    FAIL: test_prune_on_and_off
    FAIL: test_update_modified_file

我的判断是这几类来自不同地方——dirsync/apply.py、dirsync/diff.py、dirsync/paths.py 里都有嫌疑，请分别定位。要求：

1. 27 条测试全部恢复通过。测试文件不动。
2. 修复过程中这些约束不能破：
   - `dry_run=True` 只返回报告，目标目录一个字节都不能改；
   - `prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等；
   - 动手前要核对每个待写文件的 size 与 sha256，不符就抛 `ApplyError` 且目标保持原样；
   - 写文件保持「同目录临时文件 + `os.replace`」的原子语义。
3. 每类问题补一条针对性的回归测试（最好能直接复现对账时的那种输入），并在 README 里把判定口径写清楚。
4. 交付：`dirsync/apply.py`、`dirsync/paths.py`、`dirsync/diff.py`、`dirsync/manifest.py`、`test_dirsync.py`、`README.md`。中文注释与中文报错，公开 API 不变。
