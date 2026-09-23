在当前仓库用 Python 标准库实现一个「倒排索引与 BM25 检索」库，包名 `invindex`，不引入任何第三方依赖。

功能要求：
1. 分词：`tokenize(text, *, casefold=True, ngram=0, stopwords=()) -> list[str]`。按 Unicode 词边界切分（用 `str.isalnum()` 判定，ASCII 字母数字连成整词），`casefold=True` 时统一小写；CJK 字符每个字符算一个词（不做词典切分）；`ngram=2` 时对英文词额外生成相邻 2-gram（CJK 仍按单字），`ngram` 只允许 0 或 2；停用词表里的词被丢弃（比较前同样 casefold）。README 要给出分词示例与不做的语言学处理（无词干还原、无同义词）。
2. 索引：`Index(*, k1=1.2, b=0.75, ngram=0, stopwords=())`；`index.add_document(doc_id, text, *, fields=None) -> int`（返回文档长度，单位是词条数）；`index.remove_document(doc_id)`（不存在时幂等）；`index.update_document(doc_id, text)`（等价于删除再添加，`doc_id` 的文档长度与词频都要更新）；`doc_id` 非空字符串，`text` 是字符串，空文档允许（长度 0，不会被任何词查询命中）。重复 `add_document` 同一个 `doc_id` 时抛 `invindex.errors.DocumentExistsError`。
3. 倒排表与统计：索引内部必须保存**位置信息**（词项 → `doc_id` → 位置列表），用于短语查询与高亮；`index.doc_count`、`index.term_count`、`index.postings_count`（所有 (词项, 文档) 对数）、`index.avg_doc_length`。README 说明位置表的存储结构与内存占用估计。
4. 查询：`index.search(query, *, top_k=10, mode="and", phrase=False) -> list[SearchHit]`。
   - 查询文本按同一分词规则切分；词项之间按 `mode="and"`（全部命中）或 `"or"`（任一命中）组合；`-词` 表示排除包含该词的文档；`field:词` 表示只在指定字段里匹配（`fields` 是 `{字段名: 文本}` 时按字段分别建倒排表，未指定字段的查询在所有字段里匹配）。
   - `"带引号的短语"` 必须按位置做精确匹配（相邻位置、顺序一致）；`phrase=True` 时把所有相邻词项当成一个短语处理。
   - 排序用 BM25（`k1`、`b` 可配置，默认 1.2 / 0.75），**分数降序，分数相同时按 `doc_id` 字典序**；`SearchHit` 提供 `doc_id`、`score`、`matched_terms`（命中的词项，按字典序）、`positions`（每行短语的起始位置，按升序）。`top_k=0` 返回空列表。
5. 高亮：`index.highlight(doc_id, query, *, left="<<", right=">>") -> str`，先按查询命中的位置合并区间（重叠或相邻区间要合并）再插入标记，嵌套命中不允许重复插标记，插入过程要处理「插标记导致后续位置偏移」的问题；文档不存在时抛 `UnknownDocumentError`。
6. 持久化：`index.save(path)` 把索引写成目录：`seg-000001.json`（确定性 JSON：词项按字典序，posting 的位置列表用「差值 + varint」编码后 base64，非 ASCII 不转义）与 `manifest.json`（段列表、`doc_count`、`term_count`、每个段的校验和）；`Index.load(path)` 校验和失败抛 `invindex.errors.IndexCorruptError`；`index.compact()` 把多个段合并成一个；保存再加载后的查询结果（含分数与顺序）必须与保存前完全一致。
7. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：给 10 万个文档（平均 200 词条）建索引的耗时与峰值内存；1000 次两词 `AND` 查询的平均耗时；`save` 与 `load` 同一份索引的耗时与目录大小；`compact` 的耗时。
8. 边界与健壮性：空文档、重复 `doc_id`、删除后再查（不再返回）、词项大小写与中文查询、短语查询里词项顺序颠倒不应命中、`-词` 把所有结果排除后返回空列表、`top_k=0`、1 MB 的单文档、`ngram=2` 时短语查询的语义（README 说明 2-gram 下短语匹配的近似性）、索引目录不存在时 `save` 自动创建、段文件被破坏后用 `load` 报错、`compact` 前后查询结果等价（要有测试）。以上都要写进 README 并有测试。

交付物：
- `invindex/` 包：`__init__.py`（对外只暴露 `Index`、`SearchHit`、`tokenize` 与 `invindex.errors` 里的自定义异常名）、`tokenizer.py`（分词与 n-gram）、`postings.py`（倒排表与位置表、差值 varint 编解码）、`bm25.py`（打分）、`storage.py`（段文件、manifest、compact）、`errors.py`（自定义异常）。
- `test_invindex.py`：标准库 `unittest`，必须覆盖：分词（ASCII、CJK、大小写、停用词、ngram）、增删改文档后的统计正确、`AND`/`OR`/`-` 排除、`field:` 限定字段、短语查询的正反例、BM25 的确定性与同分排序、`matched_terms` 与 `positions`、`highlight` 的嵌套与合并、`top_k` 与 `top_k=0`、保存加载往返等价、`compact` 等价、损坏段文件报错、以及一组性能用例（1 万文档）。
- `bench.py`：构造 10 万文档，分别报告建索引、1000 次查询、保存、加载、压缩的耗时与峰值内存。
- `README.md`：分词规则与不做的事、倒排表与位置表结构、BM25 公式与参数含义、查询语法（AND/OR/排除/字段/短语）、高亮区间合并规则、段文件格式与压缩编码、复杂度分析、与常见搜索引擎（Lucene/SQLite FTS）的行为差异、本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
