您好，我们线上日志脱敏这条链路用的就是贵组的 miniregex（纯标准库那个实现），升级到这版之后有四类结果不对，麻烦看下。

第一类是反向引用。我们的规则里有一条类似 `(\w)\1` 的写法，配 `case_sensitive=False` 用，本意是「同一个字符重复两次，忽略大小写」。现在 `Aa`、`aA` 这类既不算命中也不算报错，静默漏掉了；实际上只要两侧字节完全相同才认，等于 `case_sensitive=False` 在反向引用这里没生效。

第二类是 `\w`。我们的票据号是 `a_1` 这种格式，`\w+` 现在只能吃到字母，数字和下划线被截断，于是匹配出来的片段短了一截，后面按长度切字段全错位。`\d`、`\s` 这两个我们没发现问题。

第三类是「`.` 与量词后面的 `?`」。我们模板里有 `<.*?>` 这种非贪婪写法，现在它变成了贪婪，`<a><b>` 这一整串都被吃掉了，本该只吃到 `<a>`。同级还有一个 `.*` 的贪婪用例也一起变了，说明不是 `?` 没被解析，而是两种量词的去向反了。

第四类是锚点。我们开了 `multiline=True` 之后按行处理，`^` 现在只在整段文本的最开头认，第二行、第三行都匹配不上；`$` 那边暂时看不出规律。

本地复现（在仓库根目录）：

    python3 -m unittest test_miniregex -v

现在 61 条里红 5 条：

    ERROR: test_backref_case_insensitive
    ERROR: test_anchors_multiline
    FAIL:  test_predefined_classes
    FAIL:  test_lazy
    FAIL:  test_lazy_vs_greedy_search

麻烦按这四条改：

1. 四类症状对应四处独立成因，逐一定位修掉，61 条测试全部恢复通过。测试文件是验收基线，不许改动或删除其中任何断言。
2. 语义必须和 README 的「语义表」逐条对齐：反向引用在 `case_sensitive=False` 下按 casefold 比较；`. ` 默认不匹配 `\n`、`dot_all=True` 才匹配；`^`/`$` 在 `multiline=True` 下匹配每行行首行尾（以 `\n` 为界）；量词默认贪婪、后缀 `?` 变懒惰，且 `a{1,3}?` 这类有界量词的懒惰同样要生效。
3. 已有的防护不要削弱：`(a*)*` 这类可空子表达式不能死循环，`(a+)+b` 这类模式仍必须抛 `MatchLimitError` 而不是卡死，`MatchLimitError` 的步数预算仍是每个起始位置独立计算。
4. 四处根因各补一条回归测试，并把 README 语义表里对应行补上「忽略大小写」「按行」这类容易被漏掉的限定词。

交付：`miniregex/engine.py`（如需可动 `miniregex/parser.py`、`miniregex/classes.py`）、`test_miniregex.py`、`README.md`。注释与报错保持中文，`compile_pattern` / `Regex` / `Match` 的公开行为与属性名不要变。
