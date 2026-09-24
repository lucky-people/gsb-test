# miniregex

纯 Python 标准库实现的迷你正则引擎。**不使用 `re` 或任何第三方库**，解析器与匹配器均从零实现。

## 目录结构

| 文件 | 职责 |
| --- | --- |
| `miniregex/__init__.py` | 只暴露 `compile_pattern`、`Regex`、`Match` |
| `miniregex/errors.py` | `PatternError`（带 pattern / position / 中文说明）、`MatchLimitError` |
| `miniregex/parser.py` | 递归下降解析器：模式串 → AST，中文报错带精确位置 |
| `miniregex/engine.py` | 编译器（AST → 指令序列）+ 回溯虚拟机 |
| `miniregex/classes.py` | `Regex` / `Match` / `compile_pattern` |
| `test_miniregex.py` | unittest，61 个用例覆盖全部语义与报错 |
| `bench.py` | 性能基准（耗时与内存分开测量） |

## 对外接口

```python
from miniregex import compile_pattern

r = compile_pattern(r"\d{3}-\d{4}", case_sensitive=True, dot_all=False, multiline=False)
r.match(text, pos=0)    # 从 pos 起必须匹配
r.fullmatch(text)       # 整串必须匹配
r.search(text, pos=0)   # 任意位置
r.finditer(text)        # 迭代所有不重叠匹配
r.findall(text)         # 每处整体匹配（组 0）的文本列表

m.group(i=0); m.groups(); m.start(i=0); m.end(i=0); m.text  # 原始输入文本
```

异常：`miniregex.errors.PatternError`（属性 `pattern` / `position` / `message`）、
`miniregex.errors.MatchLimitError`。

## 文法表

```
pattern     = alternation
alternation = concat ( "|" concat )*
concat      = repeat*
repeat      = atom quantifier?
quantifier  = "*" | "+" | "?" | "{" n ( "," m? )? "}"   每个量词后可跟 "?" 表示懒惰
atom        = literal | "." | escape | class | group | 锚点
escape      = "\" ( "d" | "D" | "w" | "W" | "s" | "S" | 数字 | 任意标点 )
class       = "[" "^"? item+ "]"     item = char | char "-" char
group       = "(" ( "?:" )? pattern ")"
锚点         = "^" | "$"
反向引用     = "\" 1..9
```

未列出的字符一律视为字面量（包括未跟在原子后的 `{`、`}`、类外的 `]`）。

## 语义表

| 条目 | 行为 |
| --- | --- |
| 字符类 | `-` 在首/尾按字面；`]` 作首字符按字面；`\` 可转义；`[z-a]` 等非法范围抛 `PatternError` |
| `.` | 默认不匹配 `\n`；`dot_all=True` 后匹配任意字符 |
| `^` / `$` | 默认只匹配整串开头/结尾；`multiline=True` 后匹配每行行首/行尾（以 `\n` 为界） |
| 量词 | 闭区间：`{n,m}` 最少 n 次、最多 m 次，`{n,}` 无上界，`{n}` 恰好 n 次；默认贪婪取尽（`a{1,3}` 在 `aaaa` 上匹配 `aaa`），加 `?` 变懒惰尽量少取（`a{1,3}?` 匹配 `a`，`a*?` 在 `aaa` 上 match 得空串） |
| 选择 | 分支从左到右尝试，`ab\|a` 在 `ab` 上匹配 `ab` |
| 分组 | 捕获组按左括号出现顺序从 1 编号，`(?:...)` 不占编号；`\n` 引用第 n 组实际捕获内容，引用不存在的组抛 `PatternError`（`position` 指向反斜杠）；`groups()` 只含捕获组，未参与的组为 `None`，`start(i)`/`end(i)` 对未参与的组返回 -1 |
| 回溯 | 分支回退时捕获槽恢复到进入该分支时的状态；重复结构中同一组多次匹配时，保留最后一次成功迭代的边界（`(a\|b)+c\1` 在 `abcb` 上 `\1` 引用 `b`） |
| 大小写 | `case_sensitive=False` 按 `str.casefold()` 比较，捕获文本保留原文 |
| 报错 | 量词前无原子、`{` 后非法计数、`{3,2}` 次序颠倒、括号/字符类未闭合、模式以 `\` 结尾，均抛带精确位置的 `PatternError` |

## 匹配算法与复杂度

**策略：回溯 + 步数上限**（为支持反向引用，未采用纯 Thompson NFA）。

1. 编译期：AST 展开为线性指令序列（`CHAR / ANY / CLASS / SPLIT / JMP / SAVE / BACKREF / GUARD / BOL / EOL / MATCH`）。
2. 运行期：显式栈回溯虚拟机逐条执行指令，不使用 Python 递归，长文本上的 `.*` 不会撑爆递归栈。
3. 安全阀：**每个起始位置的匹配尝试有独立步数预算**（默认 100 万步，`regex.match_limit` 可调），超限抛 `MatchLimitError`。
4. 捕获语义：回溯栈每帧保存捕获槽快照，分支回退即恢复；`SAVE` 原地覆盖，保证重复结构里留下的是最后一次成功迭代的边界。

复杂度：

- 常规模式：单起始位置 O(模式长 × 文本长) 步以内；`search` 整体 O(n·m)。
- 病态模式（如 `(a+)+b`）：理论指数级，但被步数上限截断为 O(上限)，**保证不爆炸**。
- 空循环防护：`GUARD` 指令检测无进展的重复（如 `(a*)*`），直接终止该分支。
- 内存：回溯栈每帧 O(组数)，无整文本复制；1 MB 文本上 search 峰值内存仅约 0.1 KB。

ReDoS 实测：`(a+)+b` 在 `"a"*30 + "c"` 上 **0.11 s 后抛 `MatchLimitError`**（若不设限，该输入需约 2³⁰ ≈ 10 亿条路径）。

## 实测数据（本机，Python 3.14.4，`python3 bench.py` 可复现）

| 项目 | 结果 |
| --- | --- |
| 编译典型模式（`\d{3}-\d{4}`、邮箱、锚定标识符、`(a\|b)*abb`） | 平均 **24 µs/个** |
| `search(r"\d{3}-\d{4}")`，1 MB 随机文本（目标埋在末尾） | **0.58 s** |
| `finditer(r"\d+")`，1 万处匹配（7 万字符） | **0.05 s** |
| ReDoS `(a+)+b` 于 `"a"*30+"c"` | **0.11 s** 后抛 `MatchLimitError` |
| search 1 MB 峰值内存（tracemalloc 单独测量，不进计时窗口） | **≈ 0.1 KB** |

## 与标准库 re 的行为差异

1. **`$` 语义**：本实现默认只匹配文本末尾；`re` 的 `$` 还匹配末尾 `\n` 之前。
2. **`findall`**：本实现恒返回整体匹配（组 0）列表；`re` 在有捕获组时返回分组内容。
3. ** `{` 处理**：本实现中 `{` 跟在原子后必须是合法量词，否则报错；`re` 对 `a{x}` 等按字面量处理。未跟在原子后的 `{` 本实现按字面量（与 `re` 一致）。
4. **转义集**：仅支持 `\d \D \w \W \s \S`、`\1`-`\9` 与标点转义；`\n \t \b \A \Z` 等及 `(?=...)`、`(?P<...>)` 等扩展语法不支持，报 `PatternError`。
5. **`\0`**：不是八进制转义，报 `PatternError`（`re` 支持八进制）。
6. **大小写不敏感**：按单字符 `casefold()` 比较；`ß` 这类 casefold 后变多字符的情形不与 `re` 完全等价（`re` 的 `ß` 可匹配 `SS`，本实现不行）。
7. **反向引用未参与匹配的组**：匹配失败（与 `re` 一致）；允许"向前引用"（如 `\1(a)`），运行时该组未捕获则匹配失败（`re` 直接编译报错）。
8. **量词计数上限**：`{n,m}` 最大 10000（展开为指令），展开后程序超过 20 万条指令报 `PatternError`。
9. **预定义类**：`\d` 用 `str.isdigit()`、`\w` 用 `isalnum()+'_'`、`\s` 用 `isspace()` 判定，与 `re` 的 Unicode 边界略有出入。
10. **Match 对象**：`m.text` 是原始输入文本（对应 `re` 的 `m.string`），另提供 `m.matched` 等价于 `group(0)`；`start/end` 对未参与的组返回 -1（与 `re` 一致）。

## 边界取舍

- 选"回溯 + 步数上限"而非 Thompson NFA：反向引用是回溯型引擎的原生能力，NFA 模拟无法直接支持；代价是病态模式靠上限兜底而非多项式保证。
- 步数预算按起始位置独立计数：保证 1 MB 文本上的正常 `search` 不会误触上限，同时单个位置的病态回溯仍被拦截。
- 量词展开而非计数器指令：实现简单、回溯语义直观；代价是 `{n}` 的 n 有上限（10000）。
- 解析器使用 Python 递归：嵌套过深的模式（约千层括号）会触发 `RecursionError`，视为超出设计边界。

## 运行

```bash
python3 -m unittest test_miniregex   # 61 个测试
python3 bench.py                     # 性能基准
```
