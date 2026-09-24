# 需求单：对齐 miniregex 的对外语义（miniregex-f06）

背景：我们把 miniregex 当成基础设施接进了业务链路（不使用 `re` 与任何第三方库、从零实现的迷你正则引擎（递归下降解析器 + 线性指令 + 带回溯栈的虚拟机））。接入测试发现它的实现与我们按 README 理解的语义不一致，先把不一致的地方列出来。

## 现象清单

| 编号 | 现象 |
|---|---|
| 1 | 反向引用指向未参与匹配的组时不再判失败，而是拿空串比较 |
| 2 | multiline=True 时 $ 的判定抄成了 ^ 的写法，行尾锚点错位 |
| 3 | \0 这个非法反向引用不再报 PatternError |

## 复现与失败用例

    python3 -m unittest test_miniregex -v

当前 6/61 条失败：

    ERROR: test_anchors_multiline
    FAIL: test_backref
    FAIL: test_backref_case_insensitive
    FAIL: test_backref_repeats_last_capture
    FAIL: test_backref_to_unmatched_group_fails
    FAIL: test_zero_backref

## 验收要求

1. 以上现象全部消除，61 条测试全绿；测试文件是验收基线，不允许修改或删除断言。
2. 实现必须满足下列硬性约束：
   - `(a*)*` 这类可空子表达式不能死循环，`(a+)+b` 这类模式必须抛 `MatchLimitError`，步数预算按起始位置独立计；
   - `PatternError` 要带 `pattern` / `position` / 中文说明，位置精确到出错的字符；
   - 捕获组编号、非捕获组、反向引用、捕获文本保留原文这些对外行为不能变；
   - 贪婪 / 懒惰、`^` `$` 在 `multiline` 下的语义必须与 README 的语义表一致。
3. 每条现象对应一处独立根因（预计分布在 miniregex/engine.py、miniregex/parser.py），请逐一定位；只改一处会有用例继续红。
4. 为每处根因补回归测试；README 里与本需求相关的语义说明要与实现一致。
5. 交付物：`miniregex/engine.py`、`miniregex/parser.py`、`miniregex/classes.py`、`test_miniregex.py`、`README.md`。注释与报错信息使用中文，不得修改公开 API。
