[CI] textdiff 流水线红灯 · job: unittest-test_textdiff · textdiff-f02

step 1/2  checkout ................................ 成功
step 2/2  python3 -m unittest test_textdiff -v ...... 失败（6/42）

日志尾部：

    FAIL: test_byte_identical_with_difflib_on_unique_lines
    FAIL: test_change_blocks_keep_document_order
    FAIL: test_conflicting_changes_emit_markers_and_conflict_block
    FAIL: test_crlf_lines_render_delete_before_insert
    FAIL: test_no_trailing_newline_keeps_marker_and_order
    FAIL: test_replace_block_renders_all_deletes_before_inserts

构建机结论：本次改动之后基线不再全绿，需要修复后重新触发流水线。

失败分布提示（本地复跑时确认过，症状互不相关）：

- 冲突块的祖先结束行号少加了 1，半开区间不对
- 同一个替换块里先插后删，渲染顺序与 GNU diff 的规范形态相反

受影响文件：textdiff/merge.py、textdiff/patch.py

解这个 job 的要求：

1. 让 `python3 -m unittest test_textdiff -v` 在干净检出后全绿；不允许改动测试文件，也不允许用跳过（skip）或放宽断言的方式让流水线变绿。
2. 流水线里其它 job 依赖的行为不能退化：
   - `apply(a, unified(a, b)) == b`，含 CRLF 混排、无结尾换行、空文件这些边界；
   - 同一输入多次生成的补丁完全一致，与 difflib 在唯一行文本上逐字节一致；
   - 上下文不匹配、行号越界、hunk 计数与正文不符、补丁结构非法一律抛 `PatchError`，带 hunk 序号与期望/实际内容；
   - 近相似大文本仍要在原来的量级完成，首尾公共前后缀归并不要去掉。
3. 每处根因补回归测试；README 的相应章节需要同步更新，否则文档 job 下一轮还会红。
4. 改动范围：`textdiff/patch.py`、`textdiff/merge.py`、`textdiff/myers.py`、`test_textdiff.py`、`README.md`。中文注释与中文报错。
