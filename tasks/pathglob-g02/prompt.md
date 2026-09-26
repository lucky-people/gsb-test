对账对不上，想请你帮忙定位一下 pathglob（pathglob-g02）

我们把 pathglob（gitignore 风格相对路径匹配库（模式翻译成正则 + 字面量分桶加速，默认大小写不敏感））接进了批处理流程，上线前拿一批样本跟参考实现逐条比。抽了三轮，结论不一致的比例明显超出预期，人工核对之后归成下面几类：

- ignores() 把 ! 规则当成了普通忽略规则，结论整个反过来
- 段内的 * 变成可以跨目录，build/*.tmp 会命中 build/x/a.tmp

在仓库根目录可以直接复现：

    python3 -m unittest test_pathglob -v

现在是 13/56 条红：

    FAIL: test_4096_char_path
    FAIL: test_batch_500x50
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
    FAIL: test_star_does_not_cross_slash

我的判断是这几类来自不同地方——pathglob/matcher.py、pathglob/translate.py 里都有嫌疑，请分别定位。要求：

1. 56 条测试全部恢复通过。测试文件不动。
2. 修复过程中这些约束不能破：
   - 同一条规则、同一个路径，`Pattern.matches`、`Matcher.match`、`Matcher.ignores` 三个入口结论必须一致；
   - `Matcher` 的求值顺序仍是「最后命中的规则说了算」，`!` 规则可以重新包含；
   - `normalize_path` 要转分隔符、折叠重复斜杠、去掉 `.` 段与结尾 `/`，并对绝对路径、盘符、`..` 抛 `PathError`；
   - 性能不许退化：`test_batch_500x50` 必须保持通过，字面量规则仍走分桶快查。
3. 每类问题补一条针对性的回归测试（最好能直接复现对账时的那种输入），并在 README 里把判定口径写清楚。
4. 交付：`pathglob/translate.py`、`pathglob/pattern.py`、`pathglob/matcher.py`、`test_pathglob.py`、`README.md`。中文注释与中文报错，公开 API 不变。
