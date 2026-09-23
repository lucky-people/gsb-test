在当前仓库用 Python 标准库实现一个「gitignore 风格路径匹配」库，包名 `pathglob`，不引入任何第三方依赖。

功能要求：
1. 模式编译：`compile_pattern(pattern: str, *, case_sensitive: bool = False) -> Pattern`，语法按 gitignore 的约定：
   - `*` 匹配任意字符但**不跨**目录分隔符；`?` 匹配单个非分隔符字符；`**` 跨目录匹配（`**/x` 匹配任意层级下的 `x`，`x/**` 匹配 `x` 下的全部内容，`a/**/b` 匹配 `a` 与 `b` 之间任意层数）。
   - 字符类 `[abc]`、`[a-z]`、`[!a-z]`（或 `^` 取反）；`]` 作为首字符时按字面处理；转义用 `\`（`\*` 表示字面星号，`\\` 表示字面反斜杠），模式末尾单独的 `\` 抛错。
   - 前导 `/` 表示锚定到根（只从路径开头匹配）；结尾 `/` 表示只匹配目录；`!` 前缀表示取反规则；空模式、只有 `!`、未闭合的 `[` 抛 `pathglob.errors.PatternError`，异常带 `pattern`、`position`（出错位置，0 基）与中文说明。
   - `Pattern` 至少提供 `original`、`negated`、`directory_only`、`anchored`、`case_sensitive` 属性，以及 `matches(path: str, is_dir: bool = False) -> bool`。
2. 规则集合：`Matcher(rules)`，按顺序应用规则，**最后一条匹配的规则决定结果**：普通规则表示忽略，`!` 规则表示重新包含；`Matcher.ignores(path, is_dir=False) -> bool` 返回最终是否被忽略，`Matcher.match(path, is_dir=False) -> Pattern | None` 返回决定结果的那条规则（没有命中返回 `None`）。
3. 路径规范化：`normalize_path(path: str) -> str`，统一把 `\` 转成 `/`、折叠重复的 `/`、去掉 `./` 段。输入是绝对路径（以 `/` 开头、`X:/` 盘符形式）、含 `..` 段、空字符串时抛 `pathglob.errors.PathError`（带 `path` 与中文说明）。`Matcher` 与 `Pattern.matches` 内部必须先规范化再匹配，Windows 分隔符输入要能正常工作。
4. 大小写：默认 `case_sensitive=False`（Windows 习惯，匹配前把路径与模式都按 `casefold()` 归一）；显式传 `case_sensitive=True` 时按原样比较。README 要写明这一点以及它与真实 gitignore 的差异。
5. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：用 200 条规则构建 `Matcher` 的耗时；用该 `Matcher` 判定 10 万条路径（其中约三成命中）的耗时；以及单条 `**/node_modules/**` 模式在 10 万条路径上匹配的耗时。实现不允许对每条路径逐条跑 `fnmatch` 全量回溯（README 说明你用的结构，例如把模式编译成锚定正则或按前缀分桶）。
6. 边界与健壮性：`*` 不跨目录而 `**` 跨目录（`a/*/b` 不匹配 `a/x/y/b`，`a/**/b` 匹配）、`**` 出现在模式中间与首尾的差异、`a/**` 是否匹配 `a` 自身（要有确定答案并写进 README）、字符类取反、`]` 作首字符、转义星号与转义反斜杠、只匹配目录的规则对 `is_dir=False` 的行为、末尾斜杠在规范化后的处理、非 ASCII 与带空格的文件名、超长路径（4096 字符）、大小写不敏感模式下的非 ASCII 折叠、以及 `!` 规则在没有任何前置规则时的结果。以上都要写进 README 并有测试。

交付物：
- `pathglob/` 包：`__init__.py`（对外只暴露 `Pattern`、`Matcher`、`compile_pattern`、`normalize_path`）、`pattern.py`（模式编译与匹配）、`translate.py`（模式到匹配器的翻译）、`matcher.py`（规则集合与前缀分桶）、`errors.py`（自定义异常）。
- `test_pathglob.py`：标准库 `unittest`，必须覆盖：`*` 与 `**` 的差异、锚定与前导斜杠、目录规则、字符类与取反、转义、`!` 重新包含与最后匹配优先、路径规范化与非法路径、大小写模式、非 ASCII 与空格、超长路径、以及一组性能用例（500 条路径 × 50 条规则）。
- `bench.py`：构造 200 条规则与 10 万条路径（约三成命中），分别报告构建 `Matcher`、批量判定、单条 `**` 模式匹配的耗时与峰值内存。
- `README.md`：模式语法表、规范化规则、大小写策略、匹配算法与复杂度（含前缀分桶/正则编译的说明）、与真实 gitignore 的行为差异（逐条列出）、边界取舍、本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
