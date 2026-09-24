先跟你同步一下 pathglob 这摊事（pathglob-f09），我这边要交出去了。

情况是：pathglob 是gitignore 风格相对路径匹配库（模式翻译成正则 + 字面量分桶加速，默认大小写不敏感）。最近在真实输入上出了问题，我查了一半没查完，跑测试是红的：

    python3 -m unittest test_pathglob -v

16/56 条失败：

    FAIL: test_4096_char_path
    FAIL: test_batch_500x50
    FAIL: test_directory_rule_requires_dir_flag_for_exact_match
    FAIL: test_escape_at_start_middle_and_end
    FAIL: test_escape_in_anchored_rule
    FAIL: test_escape_in_directory_rule
    FAIL: test_escaped_bang_and_hash_prefix_unchanged
    FAIL: test_escaped_star_question_space_brackets
    FAIL: test_last_match_wins
    FAIL: test_matcher_accepts_patterns_and_strings
    FAIL: test_matcher_mixed_case_rules
    FAIL: test_negated_class_never_matches_slash
    FAIL: test_negation_reincludes
    FAIL: test_negation_without_prior_rule
    FAIL: test_trailing_backslash_raises
    FAIL: test_trailing_slash_is_directory_only

我没查完的点，按我的笔记抄给你：

- ignores() 把 ! 规则当成了普通忽略规则，结论整个反过来
- 取反字符类开始匹配路径分隔符，[!x] 能吃下整条路径
- 模式末尾的孤立反斜杠不再报 PatternError，被当成字面反斜杠
- 目录规则在 is_dir=False 时把自己也算命中，语义放宽

我已经排除的因素：跟环境、依赖没关系，纯标准库，装上就能跑；也不是测试写错。我怀疑是好几个地方一起坏了，pathglob/matcher.py、pathglob/pattern.py、pathglob/translate.py 都得看。

拜托你做到：

1. 56 条测试全绿，别去改测试文件里的断言。
2. 这些约束别弄丢：
   - 同一条规则、同一个路径，`Pattern.matches`、`Matcher.match`、`Matcher.ignores` 三个入口结论必须一致；
   - `Matcher` 的求值顺序仍是「最后命中的规则说了算」，`!` 规则可以重新包含；
   - `normalize_path` 要转分隔符、折叠重复斜杠、去掉 `.` 段与结尾 `/`，并对绝对路径、盘符、`..` 抛 `PathError`；
   - 性能不许退化：`test_batch_500x50` 必须保持通过，字面量规则仍走分桶快查。
3. 每一处根因补一条回归测试，顺手把 README 里说得含糊或者跟实现不一致的地方改掉。
4. 交付：`pathglob/translate.py`、`pathglob/pattern.py`、`pathglob/matcher.py`、`test_pathglob.py`、`README.md`，注释和报错保持中文。

辛苦了。
