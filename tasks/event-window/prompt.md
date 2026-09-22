在当前仓库用 Python 标准库实现一个「乱序事件流的窗口聚合」库，包名 `eventwin`，不引入任何第三方依赖。

功能要求：
1. 事件与窗口定义：`Event(ts: int, value: float, key: str = "default", id: str | None = None)`，`ts` 是毫秒时间戳，可以是任意整数。`WindowSpec(kind, size, slide=None, gap=None, origin=0, allowed_lateness=0, dedup="first", on_late="drop", emit_empty=False)`：
   - `kind="tumbling"`：滚动窗口，窗口起点为 `origin + k*size`（k 为整数），事件落在 `[start, end)` 归属该窗口；`size` 必须为正整数，否则抛 `eventwin.errors.WindowConfigError`。
   - `kind="sliding"`：滑动窗口，`slide` 必须为正整数且 `slide <= size`，窗口起点为 `origin + k*slide`，一个事件会同时落在多个窗口里；`slide > size` 或 `slide <= 0` 抛错。
   - `kind="session"`：会话窗口，两个相邻事件的时间差超过 `gap` 就断开成两个会话，`gap` 必须为正整数；会话窗口忽略 `origin`。
2. 去重：相同 `id` 的事件只保留一条（`id=None` 的事件不参与去重）。`dedup="first"` 保留输入顺序里第一条，`dedup="last"` 保留最后一条；其它取值抛 `WindowConfigError`。被去重掉的事件数量要能从结果里读到。
3. 迟到与水位线：`allowed_lateness` 表示允许的迟到范围。对每个 key，把「已处理事件的最大 ts」当作水位线，事件若满足 `ts < watermark - allowed_lateness` 就视为迟到：`on_late="drop"` 时丢弃并记录到结果的迟到列表，`on_late="include"` 时仍参与聚合（默认 `drop`）；其它取值抛 `WindowConfigError`。README 要写清水位线的更新时机与判定公式。
4. 聚合与结果：`aggregate(events, spec, *, start=None, end=None) -> AggregateResult`。按 `key` 分组，每个 key 内部各自算窗口与水位线；`start` / `end` 给定时只聚合 `[start, end)` 内的事件（边界同样半开）。`AggregateResult` 必须提供 `windows`（窗口结果列表）、`late_dropped`（被丢弃的迟到事件列表）、`duplicates_dropped`（被去重的事件数量）、`processed_count`。`WindowResult` 提供 `key`、`start`、`end`、`count`、`sum`、`min`、`max`、`avg` 七个属性，`avg` 用 `sum / count` 精确计算，空窗口的 `avg` 为 `None`；`emit_empty=False` 时没有事件的窗口不出现在结果里，`emit_empty=True` 时在有事件的区间内补齐空窗口（`count=0`、`sum=0`、`min`/`max`/`avg` 为 `None`）。`windows` 按 `(key, start, end)` 升序排列。
5. 窗口分配：`assign_windows(ts, spec) -> list[tuple[int, int]]`，返回该时间点会落进的所有窗口区间，按 `start` 升序；会话窗口因为依赖上下文，这个方法对 `kind="session"` 抛 `WindowConfigError`。同一输入多次调用结果必须完全一致（确定性），输入列表不得被修改。
6. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：100 万个事件（5 个 key，滑动窗口 `size=60000`、`slide=10000`）的 `aggregate` 耗时；100 万次 `assign_windows` 的耗时。实现必须在事件时间上有序推进，不允许对每个窗口重扫全部事件。
7. 边界与健壮性：空输入、只有一个事件、恰好落在窗口边界上的事件（半开语义归右边那个窗口）、同一时间戳的多个事件、`ts` 为负数、严重乱序（迟到丢弃计数与 `late_dropped` 一致）、`gap=1` 的会话窗口、`emit_empty=True` 时结果里的空窗口数量正确、`allowed_lateness=0` 时严格按水位线丢弃、`start`/`end` 过滤与窗口起点不对齐时的行为。以上行为都要写进 README。

交付物：
- `eventwin/` 包：`__init__.py`（对外只暴露 `Event`、`WindowSpec`、`aggregate`、`assign_windows` 与 `AggregateResult` / `WindowResult`）、`spec.py`（窗口配置与校验）、`windows.py`（窗口划分与 `assign_windows`）、`dedup.py`（去重与迟到判定）、`aggregate.py`（聚合与结果对象）、`errors.py`（自定义异常）。
- `test_eventwin.py`：标准库 `unittest`，必须覆盖：三种窗口的划分、边界半开归属、滑动窗口多归属、会话断开、去重两种策略、迟到丢弃与 `late_dropped` 一致、水位线按 key 独立、`emit_empty` 补齐、`start`/`end` 过滤、配置校验（size/slide/gap/dedup/on_late 非法值）、`assign_windows` 与会话窗口抛错、确定性、以及一组性能用例。
- `bench.py`：构造 100 万事件（5 个 key，含少量乱序与重复 id），报告 `aggregate`（滑动窗口）与 `assign_windows` 的耗时与峰值内存。
- `README.md`：窗口语义与半开区间约定、水位线与迟到判定公式、去重策略、`emit_empty` 语义、算法（怎么按事件时间推进）与复杂度分析、边界取舍、本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
