# 需求单：对齐 pathglob 的对外语义（pathglob-f07）

背景：我们把 pathglob 当成基础设施接进了业务链路（gitignore 风格相对路径匹配库（模式翻译成正则 + 字面量分桶加速，默认大小写不敏感））。接入测试发现它的实现与我们按 README 理解的语义不一致，先把不一致的地方列出来。

## 现象清单

| 编号 | 现象 |
|---|---|
| 1 | 锚定前缀被无条件加上，带前导/中间斜杠的规则照样匹配任意层级 |
| 2 | 目录规则在 is_dir=False 时把自己也算命中，语义放宽 |
| 3 | 结尾的 /** 要求必须再有一层，规则匹配不到目录自身 |

## 复现与失败用例

    python3 -m unittest test_pathglob -v

当前 8/56 条失败：

    FAIL: test_anchored_directory_rule
    FAIL: test_directory_rule_requires_dir_flag_for_exact_match
    FAIL: test_escape_in_anchored_rule
    FAIL: test_escape_in_directory_rule
    FAIL: test_leading_slash_anchors_to_root
    FAIL: test_middle_slash_anchors_to_root
    FAIL: test_trailing_double_star_matches_self
    FAIL: test_trailing_slash_is_directory_only

## 验收要求

1. 以上现象全部消除，56 条测试全绿；测试文件是验收基线，不允许修改或删除断言。
2. 实现必须满足下列硬性约束：
   - 同一条规则、同一个路径，`Pattern.matches`、`Matcher.match`、`Matcher.ignores` 三个入口结论必须一致；
   - `Matcher` 的求值顺序仍是「最后命中的规则说了算」，`!` 规则可以重新包含；
   - `normalize_path` 要转分隔符、折叠重复斜杠、去掉 `.` 段与结尾 `/`，并对绝对路径、盘符、`..` 抛 `PathError`；
   - 性能不许退化：`test_batch_500x50` 必须保持通过，字面量规则仍走分桶快查。
3. 每条现象对应一处独立根因（预计分布在 pathglob/pattern.py、pathglob/translate.py），请逐一定位；只改一处会有用例继续红。
4. 为每处根因补回归测试；README 里与本需求相关的语义说明要与实现一致。
5. 交付物：`pathglob/translate.py`、`pathglob/pattern.py`、`pathglob/matcher.py`、`test_pathglob.py`、`README.md`。注释与报错信息使用中文，不得修改公开 API。
