【缺陷报告】pathglob：三处语义同时坏了，58 条里挂了 10 条

仓库里的 pathglob 现在有 10 条测试红，分属三组成因：

    FAIL: test_default_case_insensitive / test_matcher_mixed_case_rules / test_casefold_non_ascii
    FAIL: test_directory_rule_matches_contents / test_anchored_directory_rule
    FAIL: test_double_star_crosses_directories / test_consecutive_double_star_collapses
    FAIL: test_escape_in_anchored_rule / test_escape_in_directory_rule / test_batch_500x50

复现：

    python3 -m unittest test_pathglob -v

三组症状：

1. 默认变成大小写敏感了：`compile_pattern("*.LOG")` 不再匹配 `a.log`，而 README 写明默认 `case_sensitive=False`（模式与路径都按 casefold 比较）。
2. 目录规则的子树语义丢了：`compile_pattern("build/")` 不再匹配 `build/out.bin`，只有 `is_dir=True` 的目录自身命中。
3. `**` 的层级语义错了：`**/x` 只能匹配「至少一层目录下的 x」，顶层的 `x` 不命中；`a/**/b` 也不匹配 `a/b`。

要求（每条都要有测试，README 把三条语义写清）：

1. 恢复默认大小写不敏感：`case_sensitive=False` 时模式与路径都按 casefold 比较，`case_sensitive=True` 时按原样比较；不得影响显式大小写敏感的模式。
2. 目录规则（以 `/` 结尾）必须匹配「该目录自身（is_dir=True）」以及「其下任意层级的内容」；`is_dir=False` 时目录自身不算命中，但其下的文件必须命中。
3. `**` 作为完整路径段时匹配零层或多层目录：`**/x` 匹配 `x` 与 `a/b/x`；`a/**/b` 匹配 `a/b`、`a/x/b`、`a/x/y/b`；结尾 `a/**` 匹配 `a` 自身与其下所有内容；连续 `**/**` 折叠为一个。
4. 转义规则（`\*`、`\ `、`\[`）在锚定规则与目录规则里同样生效，并且 `Pattern.matches`、`Matcher.ignores`、`Matcher.match` 三个入口对同一规则同一路径结论必须一致——把这条写成不变量测试。
5. 原有 58 条测试全部恢复通过；不许改测试；不许把性能退化成逐条正则全量扫描（`test_batch_500x50` 必须恢复通过，README 的吞吐量级不变）。
6. 补回归测试覆盖上面三组，并核对 README 的「与 gitignore 的差异」一节与实现一致。

交付：改 `pathglob/translate.py`、`pathglob/pattern.py`（含 `matcher.py` 里复用匹配的路径）、`test_pathglob.py`；中文注释与报错；不动公开 API 签名。
