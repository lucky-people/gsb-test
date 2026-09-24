您好，反馈一个 pathglob 的问题（工单 pathglob-f06）

我们把这个包接进了生产的处理链路，最近运维那边报了几类异常，麻烦帮忙看下。我们不是专业审代码的，只能把现象描述清楚：

- 模式末尾的孤立反斜杠不再报 PatternError，被当成字面反斜杠
- ignores() 把 ! 规则当成了普通忽略规则，结论整个反过来
- 路径规范化不再折叠多余的斜杠，a//b 与 a/b 结论不一致

我们自己复现的方式就是在仓库根目录跑：

    python3 -m unittest test_pathglob -v

现在 56 条里红 15 条，红的名字如下：

    FAIL: test_4096_char_path
    FAIL: test_batch_500x50
    FAIL: test_collapses_repeated_slashes_and_dot
    FAIL: test_escape_at_start_middle_and_end
    FAIL: test_escape_in_anchored_rule
    FAIL: test_escape_in_directory_rule
    FAIL: test_escaped_bang_and_hash_prefix_unchanged
    FAIL: test_escaped_star_question_space_brackets
    FAIL: test_last_match_wins
    FAIL: test_matcher_accepts_patterns_and_strings
    FAIL: test_matcher_mixed_case_rules
    FAIL: test_negation_reincludes
    FAIL: test_negation_without_prior_rule
    FAIL: test_strips_trailing_slash
    FAIL: test_trailing_backslash_raises

期望的行为其实都写在 README 里了，我们照着 README 用的。麻烦：

1. 把上面这些现象逐条修掉，让 56 条测试全部通过。测试文件请不要改动，那是我们和你们约定的验收依据。
2. 修的过程中请守住这些约束：
   - 同一条规则、同一个路径，`Pattern.matches`、`Matcher.match`、`Matcher.ignores` 三个入口结论必须一致；
   - `Matcher` 的求值顺序仍是「最后命中的规则说了算」，`!` 规则可以重新包含；
   - `normalize_path` 要转分隔符、折叠重复斜杠、去掉 `.` 段与结尾 `/`，并对绝对路径、盘符、`..` 抛 `PathError`；
   - 性能不许退化：`test_batch_500x50` 必须保持通过，字面量规则仍走分桶快查。
3. 每个问题点都补一条回归测试，避免下次又回归；README 里描述不一致的地方也请一并改掉。
4. 需要交付的内容：`pathglob/translate.py`、`pathglob/pattern.py`、`pathglob/matcher.py`、`test_pathglob.py`、`README.md`。注释、报错信息请保持中文。
