在当前仓库用 Python 标准库实现一个「语义化版本与范围约束」库，包名 `semverrange`，不引入任何第三方依赖。

功能要求：
1. 版本解析：`Version.parse(text) -> Version`，严格按 SemVer 2.0.0：`MAJOR.MINOR.PATCH` 三段十进制数字（不允许前导零，`0` 本身除外），可选 `-` 预发布段（点分标识符，数字标识符不允许前导零）与 `+` 构建元数据（点分标识符，允许前导零），标识符只允许 `[0-9A-Za-z-]`。缺段、多余段、空标识符、非法字符、非字符串输入一律抛 `semverrange.errors.VersionError`，异常带 `value`、`position`（出错位置，0 基）与中文说明。
2. 版本对象：`Version` 提供 `major`、`minor`、`patch`、`prerelease`（元组，空元组表示正式版）、`build`（元组）、`is_prerelease`，支持 `str()`（规范化输出，保留构建元数据）、`repr()`、`==`、`<`、`hash()`，并提供 `bump(kind)`（`major` / `minor` / `patch` / `prerelease`，返回新对象，`bump("major")` 会清空预发布与构建元数据）。
3. 比较规则必须严格符合 SemVer 的优先级：先比三段数字；数字相同再看预发布——没有预发布段的版本**大于**有预发布段的版本；两段预发布逐标识符比较，数字标识符按数值比、且**永远小于**字母数字标识符，字母数字标识符按 ASCII 字典序比，前缀相同时段数少的小（`alpha` < `alpha.1` < `alpha.beta` < `beta` < `beta.2` < `beta.11` < `rc.1` < 正式版）；构建元数据**不参与**比较，`1.0.0+a` 与 `1.0.0+b` 视为相等。
4. 范围表达式：`parse_range(text) -> Range`，支持 `1.2.3`（等价 `=1.2.3`）、`=1.2.3`、`>1.2.3`、`>=`、`<`、`<=`、`^1.2.3`、`~1.2.3`、通配 `1.2.x` / `1.x` / `*`、连字符范围 `1.2.3 - 2.0.0`、AND（空格或逗号分隔）、OR（`||`）。语义按 npm semver 的通行定义：`^` 允许同一主版本（`^0.2.3` 只允许 `0.2.x`，`^0.0.3` 只允许 `0.0.3`；`^1.2.3` 允许 `>=1.2.3 <2.0.0`），`~1.2.3` 允许 `>=1.2.3 <1.3.0`，`~1.2` 等价 `~1.2.0`，`1.2.x` 等价 `>=1.2.0 <1.3.0`，`1.x` 等价 `>=1.0.0 <2.0.0`，`1.2.3 - 2.0.0` 含两端点。范围文本非法（例如 `>=`、`1.2.3 -`、`^`、`>1`、空串、`||`）抛 `semverrange.errors.RangeError`，带 `value` 与 `position`。
5. 判定与查询：`Range` 提供 `text`（原始文本）、`satisfies(version) -> bool`、`min_version() -> Version | None`（范围内最小正式版本，无法确定时返回 `None` 并在 README 说明）；模块级提供 `satisfies(version, range_text) -> bool`、`max_satisfying(versions, range_text) -> Version | None`、`min_satisfying(versions, range_text) -> Version | None`、`sort_versions(versions, reverse=False) -> list[Version]`（稳定排序，输入可以是字符串或 `Version`，返回 `Version` 列表）。
6. 预发布规则（必须写进 README 并给例子）：默认情况下预发布版本**不满足**任何范围，除非范围里比较的那一项自己就带预发布段且主次修订号相同——例如 `>=1.2.3-alpha.1 <1.2.3` 能匹配 `1.2.3-beta`，而 `^1.2.3` 不匹配 `1.3.0-alpha`。`max_satisfying` 同样遵守这条规则。
7. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：解析 10 万个版本字符串并排序的耗时；用 200 个不同范围各判定 1 万个版本（共 200 万次判定）的耗时。`satisfies` 不允许每次都重新解析范围（README 说明缓存策略）。
8. 边界与健壮性：`0.0.0`、超长数字段（`1.0.0` 里放 30 位数字）、前导零（`01.2.3` 非法）、`1.2` 非法但与 `1.2.x` 合法并存、构建元数据不参与比较、预发布标识符里的连字符与点、`v1.2.3` 前导 `v` 是否接受（要有确定答案并写进 README）、范围里的空格与制表符、`*` 与 `x` 混用、`>=1.2.3 <2.0.0 || >=3.0.0` 这种混合、以及空版本列表传给 `max_satisfying` 返回 `None`。以上都要写进 README 并有测试。

交付物：
- `semverrange/` 包：`__init__.py`（对外只暴露 `Version`、`Range`、`parse_range`、`satisfies`、`max_satisfying`、`min_satisfying`、`sort_versions`）、`version.py`（版本解析与对象）、`compare.py`（比较与预发布规则）、`range.py`（范围解析与判定）、`errors.py`（自定义异常）。
- `test_semverrange.py`：标准库 `unittest`，必须覆盖：版本解析的合法与非法输入、预发布比较链、构建元数据不参与比较、`bump` 四种取值、`^`/`~`/`x`/`*`/连字符/AND/OR 的边界（含 `^0.2.3`、`^0.0.3`、`~1.2`）、预发布默认排除与显式匹配两种情况、`max_satisfying` 与 `sort_versions`、错误对象的 `value`/`position`、以及一组性能用例。
- `bench.py`：构造 10 万个版本与 200 个范围，分别报告解析+排序、批量 `satisfies`、`max_satisfying` 的耗时与峰值内存。
- `README.md`：SemVer 优先级规则、范围语法表与语义（`^`/`~`/通配/连字符/OR）、预发布规则、`v` 前导与宽松解析的取舍、缓存与复杂度分析、与 npm semver 的行为差异、本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
