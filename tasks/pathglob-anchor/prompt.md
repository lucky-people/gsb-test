对账对不上了，想请你帮忙定位一下 pathglob。

我们把仓库里这套 gitignore 风格的匹配器接进了构建产物的过滤流程，上线前拿 500 个样本路径跟 `git check-ignore` 逐条比了一遍，结论不一致的有 37 个。抽查之后归成三类，都跟「锚定」和「路径规范化」有关：

    # 规则 /logs/*.log
    期望  logs/app.log      -> 忽略
           sub/logs/app.log -> 不忽略（模式前导斜杠表示只从仓库根算起）
    现状  sub/logs/app.log 也被忽略了

    # 规则 build/*.tmp
    期望  build/a.tmp      -> 忽略
           build/x/a.tmp    -> 不忽略（段内的 * 不跨目录）
    现状  build/x/a.tmp 也被忽略了

    # 规则 a/b  （调用方传进来的路径本身带了多余斜杠或结尾斜杠）
    期望  normalize_path("a//b/") == "a/b"
    现状  多余的斜杠被原样带进了规范化结果，于是同一条规则在 "a/b" 与 "a//b" 上给出不同结论

复现（仓库根目录）：

    python3 -m unittest test_pathglob -v

现在 56 条里红 7 条：

    FAIL: test_leading_slash_anchors_to_root
    FAIL: test_middle_slash_anchors_to_root
    FAIL: test_anchored_directory_rule
    FAIL: test_escape_in_anchored_rule
    FAIL: test_collapses_repeated_slashes_and_dot
    FAIL: test_strips_trailing_slash
    FAIL: test_star_does_not_cross_slash

要求：

1. 三组症状是三处独立成因，逐一修掉，让 56 条全部通过。不许改测试，也不许为了让某条用例过而给特定模式打补丁。
2. 语义细则（README 的「与 gitignore 的差异」一节要对得上）：模式中间含 `/`，或前导 `/`，都表示锚定到仓库根，不再匹配任意深度；不带 `/` 的模式才匹配任意层级下的同名段。段内的 `*` 与 `?` 不跨 `/`，只有作为完整路径段的 `**` 才跨目录。`normalize_path` 要把 `\` 转 `/`、折叠重复 `/`、去掉 `.` 段与结尾 `/`，并对绝对路径、盘符路径、含 `..` 的输入抛 `PathError`。
3. 不变量：同一条规则、同一个路径，`Pattern.matches`、`Matcher.match`、`Matcher.ignores` 三个入口的结论必须一致；`Matcher` 的求值顺序仍是「最后命中的规则说了算」，`!` 规则可以重新包含。
4. 性能不能退：`test_batch_500x50`（500 条规则 × 50 条路径）必须保持通过，字面量规则仍走分桶快查，不要退化成对每条路径全量跑一遍正则。
5. 三处根因各补一条回归测试，并在 README 里把「锚定」「规范化」两节补成带例子的对照表。

交付：`pathglob/translate.py`、`pathglob/pattern.py`、`pathglob/matcher.py`（如需）、`test_pathglob.py`、`README.md`。注释与报错保持中文，公开 API 与属性名不要变。
