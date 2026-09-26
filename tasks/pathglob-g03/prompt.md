先跟你同步一下 pathglob 这摊事（pathglob-g03），我这边要交出去了。

情况是：pathglob 是gitignore 风格相对路径匹配库（模式翻译成正则 + 字面量分桶加速，默认大小写不敏感）。最近在真实输入上出了问题，我查了一半没查完，跑测试是红的：

    python3 -m unittest test_pathglob -v

10/56 条失败：

    ERROR: test_batch_500x50
    FAIL: test_bracket_as_first_char_is_literal
    FAIL: test_collapses_repeated_slashes_and_dot
    FAIL: test_directory_rule_requires_dir_flag_for_exact_match
    FAIL: test_escape_in_directory_rule
    ERROR: test_negated_class_both_forms
    ERROR: test_range_class
    ERROR: test_simple_class
    FAIL: test_strips_trailing_slash
    FAIL: test_trailing_slash_is_directory_only

我没查完的点，按我的笔记抄给你：

- 字符类里的 - 被转义，[a-z] 这类区间退化成三个字面字符
- 目录规则在 is_dir=False 时把自己也算命中，语义放宽
- 路径规范化不再折叠多余的斜杠，a//b 与 a/b 结论不一致

我已经排除的因素：跟环境、依赖没关系，纯标准库，装上就能跑；也不是测试写错。我怀疑是好几个地方一起坏了，pathglob/pattern.py、pathglob/translate.py 都得看。

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
