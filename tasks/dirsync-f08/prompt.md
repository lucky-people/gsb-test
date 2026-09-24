[CI] dirsync 流水线红灯 · job: unittest-test_dirsync · dirsync-f08

step 1/2  checkout ................................ 成功
step 2/2  python3 -m unittest test_dirsync -v ...... 失败（5/27）

日志尾部：

    FAIL: test_detects_kind_mismatch
    FAIL: test_detects_tamper_missing_and_extra
    FAIL: test_double_star_crosses_dirs
    FAIL: test_four_categories
    FAIL: test_source_tampered_raises_and_untouched

构建机结论：本次改动之后基线不再全绿，需要修复后重新触发流水线。

失败分布提示（本地复跑时确认过，症状互不相关）：

- verify() 只报缺失与多余，内容被篡改和 kind 不对的都不报了
- 只有新建的文件会被核对，被修改的文件放过去了，源被篡改也不拦
- 文件是否改动只看大小，等长改写被当成没变
- **/ 被翻译成「必须先有一层目录」，顶层的文件匹配不上

受影响文件：dirsync/apply.py、dirsync/diff.py、dirsync/paths.py

解这个 job 的要求：

1. 让 `python3 -m unittest test_dirsync -v` 在干净检出后全绿；不允许改动测试文件，也不允许用跳过（skip）或放宽断言的方式让流水线变绿。
2. 流水线里其它 job 依赖的行为不能退化：
   - `dry_run=True` 只返回报告，目标目录一个字节都不能改；
   - `prune=False` 时保留目标里多出来的条目；连续两次 `apply` 必须幂等；
   - 动手前要核对每个待写文件的 size 与 sha256，不符就抛 `ApplyError` 且目标保持原样；
   - 写文件保持「同目录临时文件 + `os.replace`」的原子语义。
3. 每处根因补回归测试；README 的相应章节需要同步更新，否则文档 job 下一轮还会红。
4. 改动范围：`dirsync/apply.py`、`dirsync/paths.py`、`dirsync/diff.py`、`dirsync/manifest.py`、`test_dirsync.py`、`README.md`。中文注释与中文报错。
