# 事故复盘：pathglob 相关链路异常（pathglob-f04）

事故简述：下游今天反馈，pathglob 在处理真实输入时结果不对，一部分直接抛异常炸在半路。我们内部先按最小复现跑了一遍，确认不是环境问题。

这个包是gitignore 风格相对路径匹配库（模式翻译成正则 + 字面量分桶加速，默认大小写不敏感），目前的问题集中在它的核心逻辑上。

初判的影响面，按严重程度排：

- 模式末尾的孤立反斜杠不再报 PatternError，被当成字面反斜杠
- 目录规则在 is_dir=False 时把自己也算命中，语义放宽
- 中间含斜杠的模式不再锚定到仓库根

复现命令（仓库根目录）：

    python3 -m unittest test_pathglob -v

现在 56 条里红 6 条：

    FAIL: test_directory_rule_requires_dir_flag_for_exact_match
    FAIL: test_escape_in_anchored_rule
    FAIL: test_escape_in_directory_rule
    FAIL: test_middle_slash_anchors_to_root
    FAIL: test_trailing_backslash_raises
    FAIL: test_trailing_slash_is_directory_only

我看下来这不像一处原因，至少分布在 pathglob/pattern.py、pathglob/translate.py 这几个文件里，修一处另一处仍会红。请你：

1. 定位并修掉全部根因，让 56 条测试全绿。不许改测试、删断言，也不许把校验放宽或注释掉来「让它过」。
2. 这些不变量必须继续成立：
   - 同一条规则、同一个路径，`Pattern.matches`、`Matcher.match`、`Matcher.ignores` 三个入口结论必须一致；
   - `Matcher` 的求值顺序仍是「最后命中的规则说了算」，`!` 规则可以重新包含；
   - `normalize_path` 要转分隔符、折叠重复斜杠、去掉 `.` 段与结尾 `/`，并对绝对路径、盘符、`..` 抛 `PathError`；
   - 性能不许退化：`test_batch_500x50` 必须保持通过，字面量规则仍走分桶快查。
3. 每处根因补至少一条回归测试；README 里与本次改动相关的小节要同步改到与实现一致。
4. 修完请用同一条命令复跑确认，并在 README 里写明本次修复涉及哪几条语义。

交付：`pathglob/translate.py`、`pathglob/pattern.py`、`pathglob/matcher.py`、`test_pathglob.py`、`README.md`。注释与报错信息保持中文，公开 API 与已有行为不要动。
