在当前仓库用 Python 标准库实现一个「多模式文本检索与高亮」库，包名 `multisearch`，不引入任何第三方依赖，核心匹配必须自己实现（禁止用 `str.find` 对每个模式各扫一遍、禁止用 `re` 做多模式匹配）。

功能要求：
1. 构建匹配器：`build_matcher(patterns, *, case_sensitive: bool = True, normalize: bool = False, overlapping: bool = False) -> Matcher`。必须用 Aho-Corasick（Trie + 失败指针）实现，构建复杂度 O(总模式长度)，扫描复杂度 O(文本长度 + 命中数)。模式列表为空时返回一个匹配不到任何东西的 `Matcher`；空字符串模式、非字符串模式抛 `multisearch.errors.PatternError`（带 `pattern` 与中文说明）。
2. 匹配结果：`Match` 提供 `pattern`（原始模式文本）、`start`、`end`（原文中的字符下标，含头不含尾）、`text`（命中的原文片段）、`line`（1 基行号）、`column`（1 基列号，按字符计）。`Matcher.find_all(text, *, limit=None) -> list[Match]` 返回全部结果，排序规则必须确定：先按 `start` 升序，`start` 相同按长度降序，再按 `pattern` 字典序；`limit` 只截取前 N 条。`Matcher.find_iter(text)` 是生成器版本，产出顺序与 `find_all` 一致。
3. 重叠策略：`overlapping=False`（默认）时按「最长优先、从左到右不回头」输出——同一位置有多个模式命中时只保留最长的那条，并且跳过已被上一个匹配覆盖的起点；`overlapping=True` 时报告所有出现（包括相互嵌套的模式）。README 必须用具体例子说明两种模式的区别。
4. 大小写与归一化：`case_sensitive=False` 时按 `str.casefold()` 比较；`normalize=True` 时先对文本与模式做 `unicodedata.normalize("NFKC", ...)` 再比较。两种情况下 `Match.start` / `Match.end` 都必须是**原文**下标：实现要维护折叠/归一化之后到原文的下标映射，映射规则是「若匹配区间落在某个原字符的映射区间内，则取该原字符的起止位置」。README 要写清这条映射规则，并给出 `ß`（casefold 后变 `ss`）与全角 `ＡＢＣ`（NFKC 后变 `ABC`）两个例子。
5. 区间合并与高亮：模块级 `merge_ranges(ranges) -> list[tuple[int, int]]` 把重叠或相邻的区间合并、去重并按起点排序；`Matcher.highlight(text, *, left="<<", right=">>") -> str` 先用 `overlapping=True` 的结果合并区间，再在合并后的区间两端插入标记——嵌套匹配不允许在内部重复插标记，插入过程要处理「先插标记会让后续位置偏移」的经典问题。`Matcher.count(text) -> int` 返回默认策略下的命中数。
6. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：用 1000 个模式（总长度约 2 万字符）构建 `Matcher` 的耗时与峰值内存；在 10 MB 文本（命中约 5 万处）上 `find_all` 的耗时；`highlight` 同一份文本的耗时。
7. 边界与健壮性：模式列表为空（`find_all` 返回空列表）、模式含换行、匹配跨越换行（`line`/`column` 取匹配起点所在行）、模式的重复项（去重后构建，但 `Match.pattern` 保持用户给的原文）、模式互为前缀（如 `ab` 与 `abc`）、多模式在同一位置命中且长度相同（按字典序稳定）、CJK 与 emoji（按 Python 字符计下标）、组合字符、文本末尾命中、`limit=0`、以及 `result.start/end` 与 `text[start:end]` 必须逐条一致。以上都要写进 README 并有测试。

交付物：
- `multisearch/` 包：`__init__.py`（对外只暴露 `Match`、`Matcher`、`build_matcher`、`merge_ranges`）、`automaton.py`（Trie、失败指针与输出链）、`matcher.py`（扫描、重叠策略、排序与限制）、`textmap.py`（casefold/NFKC 的下标映射）、`errors.py`（自定义异常）。
- `test_multisearch.py`：标准库 `unittest`，必须覆盖：基本多模式匹配与排序、互为前缀的模式、重叠与最长优先两种策略、`limit`、区间合并且相邻区间要合并、`highlight` 的嵌套场景与标记不重复、大小写折叠与 NFKC 的下标映射（含 `ß` 与全角例子）、跨行匹配的行列号、CJK 与 emoji、空模式列表与空模式报错、`(start, end, text)` 三者一致、以及一组性能用例（200 个模式 + 1 MB 文本）。
- `bench.py`：构造 1000 个模式与 10 MB 文本，分别报告构建、`find_all`、`highlight` 的耗时与峰值内存。
- `README.md`：Aho-Corasick 的构建与扫描流程（Trie、失败指针、输出链）、重叠策略定义、下标映射规则与例子、复杂度分析、与 `str.find` 循环和正则的差异、边界取舍、本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
