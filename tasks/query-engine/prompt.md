在当前仓库用 Python 标准库实现一个「内存表 SQL 子集执行引擎」，包名 `minisql`，不引入任何第三方依赖（禁止用 `sqlite3`、`re` 之外的解析捷径也请自己写词法与语法分析，`re` 只能用于词法切分）。

功能要求：
1. 建表与数据：`Engine()`；`engine.create_table(name, columns) -> Table`，`columns` 是 `[(列名, 类型), ...]`，类型只允许 `"int"`、`"float"`、`"str"`、`"bool"`；重名表或重名列抛 `minisql.errors.SchemaError`；列名允许中文，允许用反引号 `` ` `` 包裹以使用保留字。`table.insert(rows)` 接受列表的行或单行；类型不符抛 `minisql.errors.TypeMismatchError`（`int` 可以写入 `float` 列，反向不允许；`bool` 只接受 `True`/`False`）。
2. SQL 子集：`engine.execute(sql) -> ResultSet`，支持
   `SELECT [DISTINCT] 表达式 [AS 别名], ... FROM 表 [ [INNER|LEFT] JOIN 表 ON 条件 ] [WHERE 条件] [GROUP BY 表达式, ...] [HAVING 条件] [ORDER BY 表达式 [ASC|DESC], ...] [LIMIT n [OFFSET m]]`；
   `SELECT *`、表达式（`+ - * /`、`||` 字符串连接、比较运算符 `= != <> < <= > >=`、`AND`/`OR`/`NOT`、`IS NULL`/`IS NOT NULL`、`BETWEEN ... AND ...`、`IN (值, ...)`）、标量函数 `LOWER`、`UPPER`、`LENGTH`、`ABS`、`ROUND(x, n)`、`COALESCE(...)`、`CAST(x AS 类型)`、聚合 `COUNT(*)`、`COUNT(x)`、`SUM`、`AVG`、`MIN`、`MAX`。语句可以带结尾分号，关键字大小写不敏感，标识符大小写敏感。
3. NULL 三值逻辑：`NULL` 参与的比较结果为 `NULL`，`WHERE`/`HAVING` 只保留结果为 `TRUE` 的行；`NOT NULL` 仍是 `NULL`；`AND`/`OR` 按三值表计算（`FALSE AND NULL` 为 `FALSE`，`TRUE OR NULL` 为 `TRUE`，其余含 `NULL` 的组合为 `NULL`）；聚合忽略 `NULL`（`COUNT(x)` 忽略 `NULL`，`COUNT(*)` 计所有行），`SUM`/`AVG`/`MIN`/`MAX` 在全是 `NULL` 或没有行时返回 `NULL`，`AVG` 用 `sum/count` 精确计算。
4. 分组、排序与限制：`GROUP BY` 支持多列与表达式；没有 `GROUP BY` 时聚合整个表；`HAVING` 可以引用聚合与分组表达式；`ORDER BY` 支持列名、别名、表达式、以及位置序号（`ORDER BY 2 DESC`），`NULL` 值在升序与降序里都排在最后；排序必须稳定，"值相等时保持输入顺序"；`DISTINCT` 在投影之后去重，行相等按逐列值比较（`NULL` 视为相等）；`LIMIT`/`OFFSET` 在排序之后生效，`LIMIT 0` 返回空结果，`OFFSET` 超过行数返回空结果。
5. 连接：支持 `INNER JOIN` 与 `LEFT JOIN`。等值连接条件（`ON a.k = b.k`）必须走哈希连接（先建哈希表再探测），不允许 10 万 × 1 万行退化成嵌套循环；非等值条件可以走嵌套循环。`LEFT JOIN` 在右侧无匹配时用 `NULL` 补齐右表所有列。未加 `ON` 的连接、未知表、未知列分别抛 `minisql.errors.ParseError`、`UnknownTableError`、`UnknownColumnError`。
6. 错误定位：`ParseError` 必须带 `position`（SQL 文本里的 0 基下标）、`token`（出错的词）、`sql`（原文本）与中文说明；语法错误（缺 `FROM`、括号不匹配、聚合用错位置、`ORDER BY 3` 超出投影列数等）都要给出准确位置。类型错误（字符串与数字比较、除数为零）分别抛 `TypeMismatchError`、`DivisionByZeroError`。
7. 结果与计划：`ResultSet` 提供 `columns`（列名列表，别名为准）、`rows`（元组列表）、`row_count`、`to_text()`（对齐的纯文本表格，中文按显示宽度对齐）与 `to_json()`（确定性输出）。`engine.explain(sql) -> str` 输出确定性的执行计划，例如 `scan(users) -> filter(age > 30) -> group(age) -> sort(total DESC) -> limit(10)`，同一 SQL 每次输出一致；等值连接要显示为 `hash_join(...)`。
8. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：10 万行单表上「`WHERE` 等值过滤 + `GROUP BY` + `ORDER BY` + `LIMIT`」的耗时；10 万行与 1 万行的等值 `INNER JOIN` 的耗时；同一查询连续执行 1000 次（不含解析缓存）的耗时。
9. 边界与健壮性：空表、全 `NULL` 列、`COUNT(*)` 与 `COUNT(col)` 的差异、`GROUP BY` 多列、`HAVING` 引用聚合、`SELECT DISTINCT` 与 `ORDER BY` 组合、`LIMIT 0`、`OFFSET` 越界、`LEFT JOIN` 产生 `NULL` 行、中文列名与中文字符串、字符串按码点排序、保留字被反引号包裹、`IN ()` 空列表报错、以及同一条 SQL 连续执行结果完全一致。以上都要写进 README 并有测试。

交付物：
- `minisql/` 包：`__init__.py`（对外只暴露 `Engine`、`ResultSet` 与 `minisql.errors` 里的自定义异常名）、`lexer.py`（词法）、`parser.py`（语法分析与 AST）、`plan.py`（执行计划对象）、`executor.py`（执行器：扫描、过滤、连接、分组、排序、限制）、`functions.py`（标量函数与聚合）、`errors.py`（自定义异常）。
- `test_minisql.py`：标准库 `unittest`，必须覆盖：词法与语法错误的位置、每种比较与逻辑运算符、三值逻辑全部组合、`NULL` 聚合、`GROUP BY` 多列与 `HAVING`、`ORDER BY` 的别名/序号/`NULL` 末尾/稳定性、`DISTINCT` 与 `NULL`、`LIMIT`/`OFFSET`、`INNER`/`LEFT JOIN`（含非等值条件）、类型错误与除零、中文标识符与字符串、`explain` 的确定性、以及一组性能用例（1 万行过滤与分组）。
- `bench.py`：构造 10 万行与 1 万行两张表，分别报告过滤聚合排序、等值哈希连接、重复执行 1000 次的耗时与峰值内存。
- `README.md`：支持的语法清单与语义（含三值逻辑真值表、聚合与 `NULL` 规则、排序规则）、执行计划与算子说明、哈希连接的适用条件、词法/语法分析的实现方式与复杂度、与标准 SQL 的行为差异（逐条列出）、边界取舍、本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
