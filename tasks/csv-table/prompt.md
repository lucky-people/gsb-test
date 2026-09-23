在当前仓库用 Python 标准库实现一个「CSV/TSV 严格解析与写出」库，包名 `csvtable`，不引入任何第三方依赖，也不允许用 `csv` 模块来替代核心解析逻辑（可以读它的文档对照行为，但解析与写出必须自己实现）。

功能要求：
1. 方言探测：`detect_dialect(sample: str) -> Dialect`。从候选分隔符（逗号、分号、制表符、竖线）里挑一个，依据是「按该分隔符切分后每行字段数一致且大于 1」的得分，平局时按候选顺序取靠前的。`Dialect` 是数据对象，至少有 `delimiter`、`quotechar`、`line_terminator`（`\r\n` / `\n` / `\r`）三个属性，并支持 `==` 与 `repr()`。
2. 解析：`parse(text: str, dialect: Dialect | None = None, *, strict: bool = True) -> Table`，字段规则严格按 RFC 4180：引号包裹的字段里可以出现分隔符、换行和成对的双引号（`""` 表示一个字面双引号）；引号只允许出现在字段开头；不加引号的字段里不允许出现裸双引号。`strict=True` 时遇到「引号不闭合」「引号后面还有非分隔符内容」「不加引号的字段里出现裸引号」「字段数与其他行不一致」都要抛 `csvtable.errors.CsvSyntaxError`，异常必须带 `line`（1 基行号）、`column`（1 基列号）、`offset`（原始文本里的 0 基偏移）和中文说明；`strict=False` 时宽容解析，把问题记进 `Table.warnings`（每条含 `line`、`message`）继续往下读。
3. 表格对象：`Table` 至少提供 `header`（第一行）、`rows`（其余行，每行是字符串列表）、`dialect`、`warnings`、`had_bom`（输入是否带 UTF-8 BOM）、`row_count`、`column_count`，以及 `to_text(dialect=None, quoting="minimal", with_bom=False) -> str` 与 `to_json() -> str`。`to_json()` 必须是确定性输出（字段顺序固定为 `header`、`rows`、`dialect`，非 ASCII 不转义，以换行结尾）。解析时要剥掉开头的 UTF-8 BOM 并置 `had_bom=True`。
4. 写出：`write_rows(rows, dialect=None, *, quoting="minimal", with_bom=False) -> str`。`quoting="minimal"` 只在字段含分隔符、引号或换行时才加引号，`"all"` 时全部加引号；字段内的双引号一律翻倍；行尾用 `dialect` 的 `line_terminator`（默认 `\r\n`）。必须满足往返：`parse(write_rows(rows))` 得到的 `rows` 与输入逐字段相等（包含字段内含换行、含引号、空字段、只有空格的字段）。
5. 流式解析：`StreamParser(dialect=None, *, strict=True)`，提供 `feed(chunk: str) -> list[list[str]]`（返回当前 chunk 里已经完整的行，跨 chunk 的半行与未闭合引号要缓存下来）与 `finish() -> list[list[str]]`（返回剩余内容，末尾未闭合的引号按 `strict` 规则处理）；再提供便捷函数 `iter_rows(text, dialect=None, chunk_size=65536)` 逐行产出。要求解析 20 MB 文本时内存不随行数线性膨胀（不允许先把整段文本切成行列表）。
6. 类型推断：`infer_types(column: list[str]) -> list[str]`，逐列返回每个单元格的推断类型，取值只允许 `empty`、`bool`、`int`、`float`、`date`、`str`；判定顺序为：空串（含只有空白）→ `empty`；`true`/`false`（大小写不敏感）→ `bool`；可选正负号的十进制整数（允许 `_` 千分位？不允许，只允许纯数字与正负号）→ `int`；一般浮点写法（含科学计数法）→ `float`；`YYYY-MM-DD` 形式的合法日期 → `date`；其余 → `str`。README 要写清这套判定顺序与反例。
7. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：解析一份约 50 万行、约 20 MB 的 CSV 的耗时与峰值内存；用 `write_rows` 写出同样规模数据的耗时；用 `StreamParser` 按 64 KB 分块喂入同一份文本的耗时。
8. 边界与健壮性：空输入、只有表头、只有一行数据、字段里有嵌入 `\r\n` 与裸 `\n`、字段里有连续多个引号、CRLF 与 LF 混用、行尾没有换行、空字段与只有空格的字段、字段数不一致、超长字段（1 MB 的单元格）、非 ASCII 与 emoji、带 UTF-8 BOM 的输入、纯 TSV、方言探测在引号包裹的字段内含分隔符时不能被误导。以上行为都要写进 README。

交付物：
- `csvtable/` 包：`__init__.py`（对外只暴露 `Dialect`、`Table`、`parse`、`write_rows`、`iter_rows`、`StreamParser`、`detect_dialect`、`infer_types`）、`parser.py`（核心解析与流式解析）、`dialect.py`（方言探测与默认方言）、`writer.py`（引号规则与写出）、`types.py`（类型推断）、`errors.py`（自定义异常）。
- `test_csvtable.py`：标准库 `unittest`，必须覆盖：方言探测（含引号内分隔符的干扰）、引号与转义、嵌入换行、CRLF/LF 混用、BOM 处理、`strict` 报错的行列偏移、`strict=False` 的 warnings、写出往返（含 `quoting="all"`）、流式解析跨 chunk 切分（把同一份文本按 1 字节、3 字节、整段三种方式喂入结果一致）、类型推断全部六种取值与边界、性能用例（1 万行解析）。
- `bench.py`：构造约 50 万行、约 20 MB 的 CSV（含引号字段、嵌入换行、非 ASCII），分别报告整段解析、流式分块解析、写出三者的耗时与峰值内存。
- `README.md`：字段语法与引号规则、方言探测算法、`strict` 两种模式的行为差异、流式缓冲策略与复杂度、类型推断规则、边界取舍、与标准库 `csv` 模块及 Excel 导出文件的行为差异，以及本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
