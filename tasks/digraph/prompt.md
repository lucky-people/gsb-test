在当前仓库用 Python 标准库实现一个「有向图数据结构与经典算法」库，包名 `digraph`，不引入任何第三方依赖。

功能要求：
1. 数据结构：`DiGraph()`，节点名是任意非空字符串（允许非 ASCII）。提供 `add_node(name) -> None`、`add_edge(src, dst, weight: float = 1.0) -> None`、`remove_node(name)`、`remove_edge(src, dst)`、`has_node(name)`、`has_edge(src, dst)`、`nodes`（按字典序排序的列表）、`edges`（按 `(src, dst)` 排序的 `(src, dst, weight)` 列表）、`successors(name)`、`predecessors(name)`（都按字典序）、`weight(src, dst)`、`node_count`、`edge_count`、`__contains__`、`__len__`。`add_edge` 会自动创建缺失的节点，并把自动创建过的节点名记进 `auto_created` 集合；重复添加同一条边时**覆盖**权重（记进 `overridden_edges` 集合）。权重必须是有限的非负数字（允许 0 与浮点），否则抛 `digraph.errors.WeightError`。节点名不是非空字符串时抛 `digraph.errors.NodeError`。对不存在的节点调用 `successors`/`predecessors`/`weight`/`remove_edge` 抛 `digraph.errors.NodeNotFound` 或 `EdgeNotFound`。
2. 拓扑排序：`topological_sort() -> list[str]`，用 Kahn 算法，同一层（入度同时变 0 的候选）按字典序输出，保证结果确定；存在环时抛 `digraph.errors.CycleError`，异常带 `cycle`（一个从检测点出发的环，形如 `["a", "b", "c", "a"]`）。`find_cycle() -> list[str] | None` 返回图中的任意一个环（同样首尾相接），无环返回 `None`。
3. 强连通分量：`strongly_connected_components() -> list[list[str]]`，用 Tarjan 算法，**必须写成迭代版本**（不能在 10 万节点的链上递归爆栈）；分量内部按字典序、分量列表按「最小节点名」字典序排序。
4. 最短路径：`shortest_path(src, dst) -> tuple[list[str], float] | None`（Dijkstra + `heapq`，返回路径节点列表与总权重，不可达返回 `None`）；`distances_from(src) -> dict[str, float]`（单源到所有可达节点的最短距离）。`src` 或 `dst` 不存在时抛 `NodeNotFound`。路径相同时（总权重相同）返回节点序列字典序最小的那条，README 要说明这个确定性规则。
5. 序列化：`to_json() -> str` 与 `from_json(text) -> DiGraph`，输出确定性 JSON：形如 `{"nodes": ["a", "b"], "edges": [["a", "b", 1.0]]}`，节点按字典序、边按 `(src, dst)` 排序，非 ASCII 不转义，以换行结尾；非法 JSON、结构不对、权重非法时抛 `digraph.errors.GraphFormatError`；`from_json(to_json(g))` 必须与原图等价。另有 `to_dot() -> str` 输出确定性的 Graphviz DOT 文本（节点与边都按字典序，权重作为边的 `label`）。
6. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：构建一张 10 万节点、30 万条边的稀疏有向无环图的耗时；对该图做 `topological_sort()` 的耗时；在同一张图上做 `distances_from()` 的耗时；对一条 10 万节点的链做 `strongly_connected_components()` 的耗时（验证迭代实现不吃栈）。
7. 边界与健壮性：空图的拓扑排序返回空列表、自环（拓扑排序会报 `CycleError`）、平行边覆盖、权重为 0 的边、不可达节点、非 ASCII 节点名、`remove_node` 要连带删掉相关边、`from_json`/`to_json` 往返、两个节点间总权重相同但路径不同的确定性选择、以及 `edges`/`nodes` 的排序稳定性。以上都要写进 README 并有测试。

交付物：
- `digraph/` 包：`__init__.py`（对外只暴露 `DiGraph`、`topological_sort` 相关异常与 `digraph.errors` 里的自定义异常名）、`graph.py`（数据结构与增删改查）、`algorithms.py`（拓扑排序、环检测、Tarjan、Dijkstra）、`serialize.py`（JSON 与 DOT）、`errors.py`（自定义异常）。
- `test_digraph.py`：标准库 `unittest`，必须覆盖：节点与边的增删查、自动创建与平行边覆盖、字典序排序、拓扑排序的确定性输出、环检测（含自环与两节点环）、强连通分量（含单点、互相可达的环、链式图）、Dijkstra 的不可达与等权路径确定性、权重非法、JSON 与 DOT 往返、以及一组性能用例（5 万节点拓扑排序）。
- `bench.py`：构造 10 万节点、30 万条边的稀疏 DAG 与一条 10 万节点的链，分别报告构建、`topological_sort`、`distances_from`、`strongly_connected_components` 的耗时与峰值内存。
- `README.md`：数据结构与复杂度、拓扑排序/环检测/Tarjan/Dijkstra 的算法说明与复杂度推导、确定性与排序规则（含等权路径）、迭代式 Tarjan 的实现要点、JSON 与 DOT 格式说明、边界取舍、本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
