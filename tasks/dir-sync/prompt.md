在当前仓库用 Python 标准库实现一个「目录快照与增量同步引擎」，包名 `dirsync`，不引入任何第三方依赖，也不允许调用 `robocopy` / `xcopy` / `rsync` / `cp` / `diff` 等外部命令来完成核心功能。

功能要求：
1. 生成清单：`snapshot(root, ignore=(), follow_symlinks=False) -> Manifest`。递归遍历 `root`，产出确定性的清单，条目按 POSIX 风格相对路径排序（与 `sorted()` 一致）。每个条目记录：`path`（相对路径，统一用 `/` 分隔）、`kind`（`file` / `dir` / `symlink`）、`size`（文件字节数；目录与符号链接为 0）、`sha256`（文件内容哈希，十六进制小写；目录与符号链接为 `None`）、`target`（符号链接的目标原文，其他类型为 `None`）。文件内容必须分块读取（块大小 1 MiB）后计算哈希，不允许一次性把整个文件读进内存。目录必须出现在清单里，空目录也要保留。默认不跟随符号链接；`follow_symlinks=True` 时把符号链接当普通文件/目录处理，并在 README 说明这一模式的风险。
2. 清单序列化：`Manifest.to_json() -> str` 与 `Manifest.from_json(text) -> Manifest`。JSON 必须是确定性输出：字段顺序固定为 `path`、`kind`、`size`、`sha256`、`target`，条目顺序与清单一致，非 ASCII 字符不转义，字符串使用 UTF-8，输出以换行结尾；`from_json(to_json(m))` 必须与原清单等价。非法 JSON、缺字段、未知 `kind`、路径非法时抛自定义异常 `dirsync.errors.ManifestError`。
3. 清单比较：`diff_manifests(old, new) -> DiffResult`，给出 `added` / `removed` / `modified` / `unchanged` 四个路径列表，全部按字典序排序。修改判定只看内容：文件按 `sha256`（大小变化也算），符号链接按 `target`，`file` 与 `dir` 之间来回切换算 `modified`；路径只在旧清单里是 `removed`，只在新清单里是 `added`。比较必须用哈希表而不是双重循环，5 万条目的清单也要在一秒内比完。
4. 增量落地：`apply(source_root, manifest, target_root, dry_run=False, prune=True) -> ApplyReport`。把 `source_root` 的内容同步成 `manifest` 描述的样子：新文件写入、内容不同的文件覆盖、`prune=True` 时删除目标里多出来的条目、按清单创建目录（含空目录）、创建符号链接。写入必须是原子的：先写同目录下的临时文件再 `os.replace`，失败时不允许留下半个文件。返回报告对象，含 `created` / `updated` / `deleted` / `unchanged` 四个路径列表与对应的计数属性。`dry_run=True` 时只计算报告，磁盘一个字节都不能改。连续两次 `apply` 必须幂等：第二次报告里 `created`、`updated`、`deleted` 均为空且内容不变。
5. 完整性校验：`verify(root, manifest) -> list[str]`，返回与清单不符的路径列表（缺失、内容或大小不符、`kind` 不符、清单外多出来的条目），全部按字典序排序；完全一致时返回空列表。
6. 忽略规则：`ignore` 是可迭代的字符串规则，按顺序应用，最后匹配的规则决定结果；普通规则用 `fnmatch` 语义匹配相对路径（`*` 不跨 `/`，`**` 可以跨目录），以 `/` 结尾的规则表示忽略该目录及其整棵子树，`!` 前缀表示重新包含。默认不忽略任何东西。README 必须给出规则优先级与几个具体例子。
7. 安全约束：清单里的路径必须是相对 POSIX 路径，绝对路径、盘符、`..` 段、空路径、重复路径一律抛 `ManifestError`；`apply` 必须在动手前先把整个清单校验完，并检查 `source_root` 里每个待写入文件的 `size` 与 `sha256` 是否与清单一致，不一致就抛 `ManifestError` 且不修改任何文件（不允许做到一半失败）。`target_root` 里通过符号链接指向外部的路径不允许被覆写。
8. 性能与内存：README 给出本机实测的耗时与峰值内存，并且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少要报告：对一棵约 2000 个文件、合计约 40 MiB 的目录树做 `snapshot` 的耗时；对两份 5 万条目清单做 `diff_manifests` 的耗时；把上述 2000 文件树 `apply` 到一个空目录的耗时。
9. 边界与健壮性：空目录树（清单为空）、只有空目录的树、深层嵌套（至少 20 层）、非 ASCII 与带空格的文件名、文件名大小写不同的两个文件、0 字节文件、大于 8 MiB 的文件（验证分块哈希）、`prune=False` 时保留目标多余条目、目标目录不存在时自动创建、源文件在 `snapshot` 与 `apply` 之间被改动时抛错而不是写出错误内容。以上行为都要写进 README。

交付物：
- `dirsync/` 包：`__init__.py`（对外只暴露 `snapshot`、`diff_manifests`、`apply`、`verify` 与 `Manifest` / `Entry` / `DiffResult` / `ApplyReport` 类型）、`manifest.py`（遍历与哈希）、`diff.py`（清单比较）、`apply.py`（落地变更）、`paths.py`（路径规范化与安全校验）、`errors.py`（自定义异常）。
- `test_dirsync.py`：标准库 `unittest`，必须覆盖：清单确定性与 JSON 往返、分块哈希（含 0 字节与大于 8 MiB 的文件）、空目录保留、非 ASCII 与空格文件名、忽略规则的顺序与 `!` 重新包含、非法清单路径（绝对路径、`..`、重复路径）、`diff_manifests` 四类结果、`apply` 的原子写与幂等、`prune=True/False`、`dry_run` 不改盘、源文件被改动时抛 `ManifestError`、`verify` 能检出内容篡改与多余条目、以及一组性能用例。
- `bench.py`：构造约 2000 个文件、合计约 40 MiB 的目录树与两份 5 万条目的清单，分别报告 `snapshot` / `diff_manifests` / `apply` 的耗时与峰值内存。
- `README.md`：清单格式与 JSON 约定、忽略规则语义与例子、路径安全约束、原子写与幂等策略、复杂度分析、与 `robocopy` / `rsync` 的行为差异，以及本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
