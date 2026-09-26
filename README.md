# pathglob

gitignore 风格的相对路径匹配库。用于在同步/打包工具里复用一套与
gitignore 兼容的忽略规则：判断某个相对路径是否被忽略，并支持 `!`
重新包含。只做匹配与规则求值——不做文件遍历、不读真实的
`.gitignore` 文件、不处理 git 的缓存与索引。仅依赖 Python 标准库。

## 接口

```python
from pathglob import Pattern, Matcher, compile_pattern, normalize_path

p = compile_pattern("build/", case_sensitive=False)  # case_sensitive 默认 False
p.original, p.negated, p.directory_only, p.anchored, p.case_sensitive
p.matches("build/out.o")            # -> True
p.matches("build", is_dir=True)     # -> True

m = Matcher(["*.txt", "!keep.txt"])  # 元素也可以是已编译的 Pattern
m.ignores("a.txt")                   # -> True
m.ignores("keep.txt")                # -> False（! 重新包含）
m.match("keep.txt")                  # -> Pattern('!keep.txt')；未命中返回 None

normalize_path("src\\main.py")       # -> 'src/main.py'
```

`pathglob.errors` 提供 `PathError`（含 `path`、`reason`）与
`PatternError`（含 `pattern`、`position`、`reason`），错误信息为中文。

## 语法表

| 语法 | 含义 | 示例 |
| --- | --- | --- |
| `*` | 任意个非 `/` 字符（不跨目录） | `a/*/b` 匹配 `a/x/b`，**不**匹配 `a/x/y/b` |
| `?` | 单个非 `/` 字符 | `a?c` 匹配 `abc`，不匹配 `ac`、`a/c` |
| `**` | 作为完整路径段时跨目录 | `a/**/b` 匹配 `a/b`、`a/x/b`、`a/x/y/b` |
| `a/**` | 匹配 `a` **自身**及其下所有内容（本库的明确约定） | `a/**` 匹配 `a`、`a/x/y` |
| `**`（单独） | 匹配一切 | `**` 匹配任意路径 |
| `[abc]` | 字符类 | `[abc].txt` 匹配 `a.txt` |
| `[a-z]` | 字符区间 | `[a-z]` 匹配 `b` |
| `[!a-z]` / `[^a-z]` | 取反字符类（同样不匹配 `/`） | `[!a-z]` 匹配 `A`、`0` |
| `[]a]` | `]` 作首字符按字面处理 | 匹配 `]` 或 `a` |
| `\x` | 转义下一个字符 | `\*` 字面星号；`\\` 字面反斜杠 |
| `/` 前缀 | 锚定到根 | `/foo` 匹配 `foo`，不匹配 `a/foo` |
| 中间含 `/` | 同样锚定到根 | `doc/*.md` 不匹配 `x/doc/a.md` |
| `/` 后缀 | 只匹配目录 | `build/` 在 `is_dir=False` 时不匹配 `build` 本身 |
| `!` 前缀 | 取反规则（重新包含） | `!keep.txt` |
| `\!` / `\#` 前缀 | 字面的 `!` / `#` 开头 | `\!important` 匹配 `!important` |

补充约定：

- 段内的连续星号（如 `a**b`）按单个 `*` 处理；连续的 `**` 段
  （如 `a/**/**/b`）折叠为一个 `**`。
- 目录规则（`foo/`）匹配该目录自身（需 `is_dir=True`）**以及其下所有
  内容**（`foo/bar` 任意 `is_dir` 都命中），与 gitignore 的目录忽略
  语义一致。
- 模式末尾单独的 `\` 抛 `PatternError`；未闭合的 `[` 抛
  `PatternError`；空模式、只有 `!`、只有 `/` 抛 `PatternError`。

## 路径规范化（normalize_path）

`Pattern.matches` 与 `Matcher` 内部都会先调用 `normalize_path`：

- `\` 统一转为 `/`（Windows 分隔符输入可直接使用）；
- 折叠重复的 `/`；去掉 `.` 段与结尾的 `/`；
- 以下输入抛 `pathglob.errors.PathError`：绝对路径（`/x`）、盘符路径
  （`C:/x`、`C:x`）、含 `..` 段、空字符串、规范化后为空、非字符串。

## 规则求值（Matcher）

- 规则按顺序求值，**最后命中的规则决定结果**；
- `ignores(path, is_dir=False)`：最后命中的是普通规则则为 `True`，
  是 `!` 取反规则则为 `False`；
- `!` 规则没有任何前置规则时：`match` 返回该规则本身（确实命中），
  但 `ignores` 结果为 `False`；
- `match` 在没有任何规则命中时返回 `None`。

## 大小写策略

- 默认 `case_sensitive=False`：编译模式时先对模式做 `casefold`，
  匹配前再对路径做 `casefold`，因此对 ASCII 与非 ASCII（如德语
  `ß`/`STRASSE`）都按 Unicode casefold 归一比较；
- 显式 `case_sensitive=True`：模式与路径都按原样逐字符比较；
- **与真实 gitignore 的差异**：git 的忽略匹配默认区分大小写
  （`core.ignorecase` 只影响工作区文件名的折叠，不影响 `.gitignore`
  规则匹配）。本库为了“忽略构建产物”这一主要场景选择默认不敏感，
  需要与 git 完全一致的行为时请逐条传 `case_sensitive=True`。

## 算法与复杂度

不做“每条路径 × 每条规则跑 fnmatch”的全量回溯，采用
**编译成正则 + 字面量分桶** 的组合结构：

1. **编译期**：每条模式一次性翻译成锚定正则（`^...$`），
   `**` 翻译为 `(?:.*/)?` / `(?:/.*)?`，`*` 翻译为 `[^/]*`，
   字符类直接映射为正则字符类。翻译结果是 `re.compile` 后的
   自动机，匹配单条路径为 O(路径长)，无指数回溯。
2. **字面量分桶**：不含任何通配符的模式按
   （锚定？目录？大小写敏感？）分进 4 组字典。查询时：
   - 非锚定文件字面量 → 按 basename 查 1 次；
   - 非锚定目录字面量 → 按每个路径段查（O(深度) 次）；
   - 锚定文件字面量 → 按完整路径查 1 次；
   - 锚定目录字面量 → 按每个前缀查（O(深度) 次）。
3. **通配符规则**：剩余的才逐条跑预编译正则，并用“已命中的最大
   规则下标”剪枝。

复杂度（R 条规则、P 条路径、路径深度 D、通配符规则数 W ≤ R）：

- 构建：O(R × 模式长)；
- 单条路径查询：O(D) 次字典查找 + O(W × 路径长)，
  字面量规则不占逐条扫描时间；
- 批量 P 条：O(P × (D + W × 路径长))；当规则以字面量为主时
  接近 O(P × D)。

## 与真实 gitignore 的逐条差异

| 方面 | gitignore | pathglob |
| --- | --- | --- |
| 大小写 | 规则匹配区分大小写 | 默认不敏感（casefold），可逐条改 |
| 注释 | `#` 开头是注释 | 不读文件、无注释概念，`#` 按字面（`\#` 同 git 转义） |
| 行尾空格 | 未转义的行尾空格被忽略 | 原样保留，空格即字面空格 |
| 父目录已排除 | 父目录被排除后无法重新包含其子项 | 允许 `!` 重新包含（纯规则求值，不做 git 的遍历剪枝） |
| 相对基准 | 相对于所在 `.gitignore` 的目录 | 只认“根相对”路径，目录层级由调用方拼好 |
| `a/**` | 文档只承诺匹配 `a` 的内容 | 明确约定同时匹配 `a` 自身 |
| 连续 `**` / 段内 `**` | 未定义行为 | 折叠连续 `**`；段内 `a**b` 按 `a*b` 处理 |
| 花括号 | 不支持 `{}` 展开 | 同样不支持（非目标） |

含转义的规则（如 `\*`、`\?`、`\ `、`\[`）在两个入口行为一致：
`Pattern.matches` 与 `Matcher.ignores` / `Matcher.match` 都按反转义后
的字面文本判定，Matcher 的字面量分桶使用的也是反转义后的文本，
不会出现单条判定命中、放进规则集却漏配的情况。

## 边界取舍

- 路径中的 `\` 一律视为分隔符，因此**文件名里无法表达字面反斜杠**
  （模式里的 `\\` 可编译但永不命中）；
- 路径含 `..`、绝对路径、盘符路径直接报错，不做“尽力解析”；
- 取反字符类 `[!...]` 永不匹配 `/`，与 `FNM_PATHNAME` 语义一致；
- 字符类中的 `-` 原样保留以支持区间，极个别把 `-` 当字面又放在
  两字符中间的写法会被解释成区间；
- 不处理文件系统编码问题，输入必须是已解码的 `str`。

## 本机实测

环境：AMD Ryzen 7 7735H / WSL2 / Python 3.14.4，`python3 bench.py`
（200 条规则：100 个字面量目录 + 60 个锚定字面量文件 + 30 个通配符
后缀 + 10 个常见语义规则；10 万条路径，实测命中 30.0%）：

| 指标 | 实测 |
| --- | --- |
| 构建 Matcher（200 条规则） | ≈ 8.8 ms |
| 批量判定 10 万路径 | ≈ 1.17 s（约 8.5 万路径/秒） |
| 峰值内存（tracemalloc 单独一轮，含路径列表） | ≈ 7.2 MiB |
| 单条 `**/node_modules/**` × 10 万路径 | ≈ 0.08 s |

耗时与内存分开测量：`tracemalloc` 只在单独的内存轮开启，不进
计时窗口。

## 测试

```bash
python3 -m unittest test_pathglob -v   # 59 个用例
python3 bench.py                        # 性能基准
```

覆盖：`*` 与 `**` 差异、锚定、目录规则、字符类与取反、转义、
`!` 重新包含与最后匹配优先、路径规范化与非法路径、大小写模式、
非 ASCII 与空格文件名、4096 字符超长路径、`!` 规则无前置规则、
以及 500 路径 × 50 规则的性能用例。
