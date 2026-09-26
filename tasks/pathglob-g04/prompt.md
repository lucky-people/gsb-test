[CI] pathglob 流水线红灯 · job: unittest-test_pathglob · pathglob-g04

step 1/2  checkout ................................ 成功
step 2/2  python3 -m unittest test_pathglob -v ...... 失败（5/56）

日志尾部：

    FAIL: test_collapses_repeated_slashes_and_dot
    FAIL: test_consecutive_double_star_collapses
    FAIL: test_double_star_crosses_directories
    FAIL: test_strips_trailing_slash
    FAIL: test_trailing_double_star_matches_self

构建机结论：本次改动之后基线不再全绿，需要修复后重新触发流水线。

失败分布提示（本地复跑时确认过，症状互不相关）：

- 结尾的 /** 要求必须再有一层，规则匹配不到目录自身
- 中间的 /**/ 要求至少一层目录，a/**/b 匹配不到 a/b
- 路径规范化不再折叠多余的斜杠，a//b 与 a/b 结论不一致

受影响文件：pathglob/pattern.py、pathglob/translate.py

解这个 job 的要求：

1. 让 `python3 -m unittest test_pathglob -v` 在干净检出后全绿；不允许改动测试文件，也不允许用跳过（skip）或放宽断言的方式让流水线变绿。
2. 流水线里其它 job 依赖的行为不能退化：
   - 同一条规则、同一个路径，`Pattern.matches`、`Matcher.match`、`Matcher.ignores` 三个入口结论必须一致；
   - `Matcher` 的求值顺序仍是「最后命中的规则说了算」，`!` 规则可以重新包含；
   - `normalize_path` 要转分隔符、折叠重复斜杠、去掉 `.` 段与结尾 `/`，并对绝对路径、盘符、`..` 抛 `PathError`；
   - 性能不许退化：`test_batch_500x50` 必须保持通过，字面量规则仍走分桶快查。
3. 每处根因补回归测试；README 的相应章节需要同步更新，否则文档 job 下一轮还会红。
4. 改动范围：`pathglob/translate.py`、`pathglob/pattern.py`、`pathglob/matcher.py`、`test_pathglob.py`、`README.md`。中文注释与中文报错。
