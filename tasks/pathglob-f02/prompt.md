迁移验收单：把批处理链路从旧实现切到 pathglob（pathglob-f02）

我们准备用 pathglob（gitignore 风格相对路径匹配库（模式翻译成正则 + 字面量分桶加速，默认大小写不敏感））替换现在的旧实现。灰度阶段按老实现的结果做对照，验收用例跑出 13/56 条不一致，切换因此卡在这里。

对照中暴露的差异：

- 中间含斜杠的模式不再锚定到仓库根
- ignores() 把 ! 规则当成了普通忽略规则，结论整个反过来

验收命令（仓库根目录）：

    python3 -m unittest test_pathglob -v

不一致的用例：

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
    FAIL: test_middle_slash_anchors_to_root
    FAIL: test_negation_reincludes
    FAIL: test_negation_without_prior_rule

判断：差异跨了 pathglob/matcher.py、pathglob/pattern.py，不是一处适配问题，需要逐个对齐语义后重新验收。

切换前必须满足：

1. 56 条验收用例全部通过，测试文件作为对照基准不得修改。
2. 切换后这些既有承诺不能被破坏（旧实现里也是这么做的）：
   - 同一条规则、同一个路径，`Pattern.matches`、`Matcher.match`、`Matcher.ignores` 三个入口结论必须一致；
   - `Matcher` 的求值顺序仍是「最后命中的规则说了算」，`!` 规则可以重新包含；
   - `normalize_path` 要转分隔符、折叠重复斜杠、去掉 `.` 段与结尾 `/`，并对绝对路径、盘符、`..` 抛 `PathError`；
   - 性能不许退化：`test_batch_500x50` 必须保持通过，字面量规则仍走分桶快查。
3. 每处差异补一条回归用例，把「为什么这么判定」写进 README，避免下次切换再对不上。
4. 交付：`pathglob/translate.py`、`pathglob/pattern.py`、`pathglob/matcher.py`、`test_pathglob.py`、`README.md`；注释与报错保持中文，对外接口签名不变。
