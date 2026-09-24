迁移验收单：把批处理链路从旧实现切到 textdiff（textdiff-f04）

我们准备用 textdiff（文本差异与三方合并引擎（Myers 最短编辑脚本 + unified diff 生成与套用 + diff3 风格合并））替换现在的旧实现。灰度阶段按老实现的结果做对照，验收用例跑出 12/42 条不一致，切换因此卡在这里。

对照中暴露的差异：

- 区间长度为 1 时也带上了计数，与 unified 规范不一致
- 旧侧计数为 0 的 hunk 定位方式被统一成减一，插入点整体前移
- 冲突块的祖先起始行号少加了 1，替换/删除冲突定位偏一行

验收命令（仓库根目录）：

    python3 -m unittest test_textdiff -v

不一致的用例：

    FAIL: test_byte_identical_with_difflib_on_unique_lines
    FAIL: test_change_blocks_keep_document_order
    FAIL: test_conflicting_changes_emit_markers_and_conflict_block
    FAIL: test_crlf_lines_render_delete_before_insert
    FAIL: test_delete_to_empty_old_side
    FAIL: test_empty_file_cases
    FAIL: test_empty_to_text_and_text_to_empty
    FAIL: test_insert_at_head_uses_zero_start_for_old_side
    FAIL: test_no_trailing_newline_keeps_marker_and_order
    FAIL: test_randomized_roundtrip_and_shortest
    FAIL: test_replace_block_renders_all_deletes_before_inserts
    FAIL: test_roundtrip_varied_contexts

判断：差异跨了 textdiff/merge.py、textdiff/patch.py，不是一处适配问题，需要逐个对齐语义后重新验收。

切换前必须满足：

1. 42 条验收用例全部通过，测试文件作为对照基准不得修改。
2. 切换后这些既有承诺不能被破坏（旧实现里也是这么做的）：
   - `apply(a, unified(a, b)) == b`，含 CRLF 混排、无结尾换行、空文件这些边界；
   - 同一输入多次生成的补丁完全一致，与 difflib 在唯一行文本上逐字节一致；
   - 上下文不匹配、行号越界、hunk 计数与正文不符、补丁结构非法一律抛 `PatchError`，带 hunk 序号与期望/实际内容；
   - 近相似大文本仍要在原来的量级完成，首尾公共前后缀归并不要去掉。
3. 每处差异补一条回归用例，把「为什么这么判定」写进 README，避免下次切换再对不上。
4. 交付：`textdiff/patch.py`、`textdiff/merge.py`、`textdiff/myers.py`、`test_textdiff.py`、`README.md`；注释与报错保持中文，对外接口签名不变。
