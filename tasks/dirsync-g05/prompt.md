对账对不上，想请你帮忙定位一下 dirsync（dirsync-g05）

我们把 dirsync（按清单把目标目录同步成与源目录一致的目录同步工具（快照 / 差异 / 应用三层，支持 ignore 规则与 prune））接进了批处理流程，上线前拿一批样本跟参考实现逐条比。抽了三轮，结论不一致的比例明显超出预期，人工核对之后归成下面几类：

- **/ 被翻译成「必须先有一层目录」，顶层的文件匹配不上
- 同一路径上 kind 变了却被判成没变，差异表里看不到
- verify() 只报缺失与多余，内容被篡改和 kind 不对的都不报了

在仓库根目录可以直接复现：

    python3 -m unittest test_dirsync -v

现在是 5/27 条红：

    FAIL: test_detects_kind_mismatch
    FAIL: test_detects_tamper_missing_and_extra
    FAIL: test_double_star_crosses_dirs
    FAIL: test_four_categories
    ERROR: test_kind_switch_file_to_dir

我的判断是这几类来自不同地方——dirsync/apply.py、dirsync/diff.py、dirsync/paths.py 里都有嫌疑，请分别定位。要求：

1. 27 条测试全部恢复通过。测试文件不动。
2. 修复过程中这些约束不能破：
   - `dry_run=True` 只返回报告，目标目录一个字节都不能改；
   - `prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等；
   - 动手前要核对每个待写文件的 size 与 sha256，不符就抛 `ApplyError` 且目标保持原样；
   - 写文件保持「同目录临时文件 + `os.replace`」的原子语义。
3. 每类问题补一条针对性的回归测试（最好能直接复现对账时的那种输入），并在 README 里把判定口径写清楚。
4. 交付：`dirsync/apply.py`、`dirsync/paths.py`、`dirsync/diff.py`、`dirsync/manifest.py`、`test_dirsync.py`、`README.md`。中文注释与中文报错，公开 API 不变。
