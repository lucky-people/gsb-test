在当前仓库用 Python 标准库实现一个「带 WAL 与崩溃恢复的事务型嵌入式键值存储」，包名 `walkv`，不引入任何第三方依赖，也不允许调用任何外部数据库或 `sqlite3` 来完成存储与事务。

磁盘布局固定（必须写进 README，并有字节级测试断言）：
- 存储目录里有 `wal.log`、`snapshot.json`、`manifest.json`、`LOCK` 四个文件。
- WAL 记录格式（全部小端）：`length(4 字节无符号) | crc32(4 字节无符号，对 payload 计算) | payload(length 字节)`。`payload` 是一段 UTF-8 的 JSON，**一个事务就是一条记录**，内容是 `{"sequence": int, "operations": [{"op": "put"|"delete", "key": str, "value": str}]}`。
- `snapshot.json` 是确定性快照：`{"sequence": int, "items": {"<key>": "<value>"}}`，键按字典序、非 ASCII 不转义、以换行结尾；`manifest.json` 记录 `{"snapshot_sequence": int, "snapshot_checksum": int, "wal_bytes": int}`，同样确定性输出。

功能要求：
1. 打开与关闭：`Store(path, *, sync=True, max_wal_bytes=64*1024*1024)`。目录不存在时自动创建；同目录被第二个 `Store` 或第二个进程打开时抛 `walkv.errors.StoreLockedError`（用 `LOCK` 文件实现，进程退出要能释放）。`store.close()` 后再次操作抛 `walkv.errors.StoreClosedError`。打开时自动恢复：重放快照之后 WAL 里所有**完整且校验通过**的事务。
2. 事务：`with store.transaction() as tx:` 块内 `tx.put(key, value)`、`tx.delete(key)`、`tx.get(key)`（能看到自己未提交的写；未写过的键看到事务开始时的快照值），正常退出时整批原子提交，抛出异常时整批回滚（磁盘与内存都不留痕迹）。也支持 `store.put` / `store.delete` 作为「单操作事务」的便捷写法。键与值都是 `str`（值允许空串），键不允许空串，键与值不允许超过 1 MiB，否则抛 `walkv.errors.ValueError`（自定义异常名 `KeyValueError`）。
3. 读取：`store.get(key) -> str | None`；`store.scan(prefix=None, start=None, end=None, reverse=False, limit=None)` 返回按键字典序（按 Unicode 码点）的 `(key, value)` 迭代器，区间语义是半开 `[start, end)`，`prefix` 与 `start`/`end` 同时给出时取交集，`reverse=True` 时逆序产出，`limit` 限制条数；`store.count() -> int`。事务进行中调用这些方法必须看到事务开始时的快照（快照读），不能看到未提交的改动。
4. 崩溃恢复：这是本题的重点。恢复时必须能处理下面每一种情况，并且恢复结果**恰好等于**「最后一条完整提交的事务」：
   - WAL 尾部被截断在记录中间（length 或 payload 不完整）；
   - 记录 CRC 不匹配（内容被篡改一个字节）；
   - length 字段比剩余字节还大；
   - payload 是半截 JSON；
   - WAL 为空但快照存在；
   - 存在 `snapshot.json` 但 `manifest.json` 缺失（这时要能从快照恢复，并把 `wal_bytes` 记为 0）；
   - `snapshot.json` 的校验和与 `manifest.json` 不符时抛 `walkv.errors.StoreCorruptError`，不允许静默丢数据。
   恢复过程要把「重放了几条事务、跳过了多少字节」记录下来，通过 `store.recovered_transactions` 与 `store.recovered_bytes` 暴露，README 说明恢复流程。
5. 压缩：`store.compact()` 把当前状态写成新的 `snapshot.json` 与 `manifest.json`，然后清空 `wal.log`（原子替换：先写临时文件再 `os.replace`，中途崩溃不能破坏原有可恢复状态）；返回本次合并的事务序号。WAL 超过 `max_wal_bytes` 时提交过程中自动触发一次压缩。压缩前后 `scan()` 的结果必须完全一致（要有测试）。
6. 并发与持久化：同一进程内多个线程并发 `get`/`scan` 必须安全（提交/压缩时加锁，读不阻塞）；`sync=True` 时每次提交都要 `os.fsync` WAL，README 说明它与性能的取舍。不允许跨进程并发写。
7. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：10 万次 `put`（每 100 条一个事务，`sync=False`）的耗时；10 万次 `get` 的耗时；对 10 万键做全量 `scan()` 的耗时；重新打开并恢复 10 万条事务的耗时。
8. 边界与健壮性：空值、1 MiB 的键与值、110 万字节的值报错、非 ASCII 键（含 emoji）的字典序、删除不存在的键（幂等）、同一事务里先 `put` 再 `delete` 同一键、一个事务里 10 万个操作、`scan` 的 `start`/`end`/`prefix` 各种组合、`reverse=True` 与 `limit` 组合、压缩之后 `wal.log` 归零、以及「压缩进行到一半崩溃」留下的临时文件不会让下次打开失败。以上都要写进 README 并有测试。

交付物：
- `walkv/` 包：`__init__.py`（对外只暴露 `Store` 与 `walkv.errors` 里的自定义异常名）、`wal.py`（记录编解码与重放）、`snapshot.py`（快照与 manifest 读写）、`store.py`（事务、锁、扫描、压缩）、`errors.py`（自定义异常）。
- `test_walkv.py`：标准库 `unittest`，必须覆盖：WAL 记录的字节级断言、事务原子性与回滚、快照读语义、`scan` 的区间与顺序、上面七种崩溃场景各一个用例（用真实文件、手工改写/截断 WAL 字节来构造）、压缩等价性与压缩中崩溃、锁文件冲突（同进程两次打开）、`sync=False` 下的批量写入、以及一组性能用例（1 万次 put）。
- `bench.py`：构造 10 万次 `put` 与 10 万次 `get`，分别报告写入、读取、全量扫描、崩溃恢复四种场景的耗时与峰值内存。
- `README.md`：磁盘格式（WAL 记录字段偏移表、快照与 manifest 的 JSON 结构）、恢复算法（重放到哪一条为止、怎么识别撕裂尾部）、事务与快照读语义、压缩与原子替换策略、锁与并发说明、复杂度、与 SQLite WAL 的差异、边界取舍、本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
