在当前仓库用 Python 标准库实现一个「区间集合与区间索引」库，包名 `rangeset`，不引入任何第三方依赖。

功能要求：
1. 区间类型：`Interval(start: int, end: int)`，表示半开区间 `[start, end)`，只接受整数端点。`end <= start`（空区间或反向区间）必须抛 `rangeset.errors.IntervalError`，异常信息用中文并带上出错的 `start`、`end`。区间是不可变对象，支持 `==`、`<`（先比 `start` 再比 `end`）、`hash()`、`repr()`，并提供 `length` 属性与 `overlaps(other)`、`contains_point(x)`、`contains_interval(other)` 三个方法。
2. 区间集合：`RangeSet(intervals=()) -> RangeSet`。构造时必须规范化：排序、合并重叠区间、合并首尾相接的区间（`[1,3)` 与 `[3,5)` 合并成 `[1,5)`），结果用 `intervals` 属性暴露为升序、互不相交且互不相邻的元组。集合对象是不可变的：`add(interval)`、`remove(interval)`、`union(other)`、`intersection(other)`、`difference(other)`、`symmetric_difference(other)` 都返回新的 `RangeSet`，不得修改自身。`remove` 支持把区间从中间挖空（`[0,10)` 去掉 `[3,5)` 得 `[0,3)` 与 `[5,10)`）。另提供 `contains_point(x)`、`contains_interval(interval)`、`length`（覆盖的总长度，整数）、`is_empty`、`count_intervals`，以及 `to_text()`（例如 `[1,3) [5,8)`，空集合返回 `(empty)`）。
3. 序列化：`RangeSet.to_json() -> str` 与 `RangeSet.from_json(text) -> RangeSet` 必须确定性输出：形如 `{"intervals": [[1, 3], [5, 8]]}` 的单行 JSON，非 ASCII 不转义（本库没有非 ASCII 内容），输出以换行结尾；非法 JSON、结构不对、端点非整数时抛 `rangeset.errors.IntervalError`；`from_json(to_json(s))` 必须与原集合等价。
4. 区间索引：`IntervalIndex(intervals) -> IntervalIndex`，面向大量区间的重叠查询，允许输入区间彼此重叠（内部不做合并）。必须提供 `query_point(x) -> list[Interval]`（覆盖点 x 的所有区间）、`query_overlap(interval) -> list[Interval]`（与给定区间有交集的区间）、`query_within(interval) -> list[Interval]`（完全落在给定区间内的区间）、`count_point(x) -> int`。四个查询返回的区间都按 `(start, end)` 升序排列。索引构建为 O(n log n)，查询为 O(log n + k)，不允许每次查询都线性扫全部区间；README 要说明你用的具体结构（例如按起点排序的数组加最大端点前缀，或区间树）与复杂度推导。
5. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：用 10 万个随机区间构建 `IntervalIndex` 的耗时；在该索引上做 10 万次 `query_point` 与 10 万次 `query_overlap` 的耗时；把 10 万个区间塞进一个 `RangeSet` 做规范化合并（含大量重叠）的耗时。
6. 边界与健壮性：空集合与空索引、单个区间、`start` 为负数、`start` 与 `end` 相距很大（例如 `-10**18` 到 `10**18`）、整点相邻区间的合并、一个区间被另一个完全包含、两个集合完全不相交、`query_overlap` 正好只交在端点上（半开语义：`[1,3)` 与 `[3,5)` 不算相交）、同一批区间重复出现（`RangeSet` 去重、`IntervalIndex` 保留重复条目）、10 万个区间的 `length` 统计不溢出。以上行为都要写进 README。

交付物：
- `rangeset/` 包：`__init__.py`（对外只暴露 `Interval`、`RangeSet`、`IntervalIndex`）、`interval.py`（区间类型）、`normalize.py`（规范化与集合运算）、`index.py`（区间索引与查询）、`errors.py`（自定义异常）。
- `test_rangeset.py`：标准库 `unittest`，必须覆盖：区间构造校验与比较、规范化合并（重叠与相邻）、`add` / `remove` / 集合四则运算的不变性与结果、`remove` 挖空、`contains_point` 与 `contains_interval` 的半开语义、JSON 往返与非法输入、索引的四种查询（含端点相接不算相交、重复区间、空索引）、性能用例（1 万区间建索引并做 1000 次查询）。
- `bench.py`：构造 10 万个随机区间，分别报告 `RangeSet` 规范化、`IntervalIndex` 建索引、10 万次 `query_point`、10 万次 `query_overlap` 的耗时与峰值内存。
- `README.md`：区间语义（半开、相邻合并）、集合运算定义、索引结构与复杂度推导、边界取舍、本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
