# dirsync

纯 Python 标准库实现的目录快照 / 差异 / 同步工具。不依赖任何第三方包，
也不调用 robocopy / xcopy / rsync / cp / diff 等外部命令。

## 功能概览

```python
import dirsync

# 1. 生成源目录快照
manifest = dirsync.snapshot("/data/src", ignore=["*.log", "build/", "!keep.log"])
text = manifest.to_json()                 # 可落盘、可传输

# 2. 差异比较
diff = dirsync.diff_manifests(old_manifest, new_manifest)
print(diff.added, diff.removed, diff.modified, diff.unchanged)

# 3. 按清单把目标目录同步成源目录状态
report = dirsync.apply("/data/src", manifest, "/data/dst")
print(report.created, report.updated, report.deleted, report.unchanged)

# 4. 校验目标目录是否与清单一致
bad = dirsync.verify("/data/dst", manifest)   # 完全一致时返回 []
```

## 清单格式（Manifest）

清单序列化为 UTF-8 JSON 文本，顶层结构：

```json
{
  "format": "dirsync-manifest",
  "version": 1,
  "entries": [
    {"path": "a.txt", "kind": "file", "size": 5, "sha256": "2cf2...", "target": null},
    {"path": "sub", "kind": "dir", "size": 0, "sha256": null, "target": null},
    {"path": "link", "kind": "symlink", "size": 0, "sha256": null, "target": "a.txt"}
  ]
}
```

- 每条记录的字段顺序固定为 `path`、`kind`、`size`、`sha256`、`target`；
- 非 ASCII 字符不转义（`ensure_ascii=False`），文本以换行结尾；
- `path` 为 POSIX 相对路径，`kind` 取 `file` / `dir` / `symlink`；
- 文件按 1 MiB 分块读取计算 sha256；空目录也会进入清单；
- 条目按路径排序（与 `sorted()` 一致），同一目录快照两次结果逐字节相同；
- `Manifest.to_json()` 与 `Manifest.from_json(text)` 往返等价；
- 非法 JSON、缺字段、未知 kind、非法路径一律抛 `dirsync.errors.ManifestError`。

## 忽略规则（ignore）

`snapshot(root, ignore=[...])` 按书写顺序逐条求值，**最后一条匹配的规则决定**是否忽略：

| 规则形式 | 语义 |
| --- | --- |
| `*.log` | fnmatch 语义，`*` / `?` 不跨 `/`；不含 `/` 的规则同时匹配完整路径与 basename |
| `**/temp.tmp` | `**` 可跨任意层目录 |
| `build/` | 以 `/` 结尾：忽略整棵子树（目录本身及其下所有内容） |
| `!keep.log` | `!` 前缀：重新包含（取消之前的忽略） |

文件与目录都参与判定：普通规则表示忽略，`!` 规则表示重新包含；
目录规则命中即剪掉整棵子树（不再递归进入），因此被忽略目录里的条目
无法靠后续的 `!` 规则复活（与 gitignore 一致）。

示例：

```python
ignore = ["*.log", "!keep.log"]   # 忽略所有 .log，但保留 keep.log
ignore = ["!keep.log", "*.log"]   # 顺序反过来：keep.log 也被忽略（最后匹配生效）
ignore = ["build/", "**/*.tmp"]   # 忽略 build 子树与所有 .tmp 文件
ignore = ["*.tmp", "**/cache/", "!cache/keep.tmp"]
# cache/ 子树被 "**/cache/" 整体剪掉，"!cache/keep.tmp" 不会生效
```

## 安全约束

- 清单路径必须是相对 POSIX 路径：绝对路径、盘符（`C:`）、`..`、空路径、
  重复路径一律抛 `ManifestError`，从根上杜绝目录穿越；
- `apply` 在修改任何文件**之前**先全量校验清单，并核对 source 里每个
  待写文件的 size 与 sha256，任一不一致即抛 `ApplyError`，此时磁盘零改动；
- 快照之后源文件被改动时，`apply` 在动手之前抛 `ApplyError`，目标目录保持原样；
- `dry_run=True` 时只计算并返回报告，不修改磁盘上的任何字节
  （目标目录的内容与 mtime 都保持不变）。

## 幂等与原子写策略

- **原子写**：文件先写入目标同目录下的临时文件（`.dirsync-*`），`fsync`
  后用 `os.replace` 原子替换，目标路径任意时刻要么是老内容要么是新内容，
  不会出现写了一半的文件；符号链接同样先建临时链接再 `os.replace`；
- **幂等**：`apply` 基于目标目录的实时快照计算差异，连续执行两次时，
  第二次的 `created` / `updated` / `deleted` 全部为空；
- `prune=True`（默认）删除目标里清单外的多余条目；`prune=False` 时保留。

## 复杂度

- `snapshot`：O(n) 次系统调用 + 全量内容哈希，IO  bound；
- `diff_manifests`：哈希表比较，时间 O(n)、空间 O(n)，5 万条目远低于 1 秒；
- `apply`：一次目标快照 + 一次 diff + 仅写入有差异的文件；
- `verify`：一次快照 + 一次 diff，O(n)。

## 与 robocopy / rsync 的差异

- **纯标准库、跨平台**：不调用外部进程，Windows / Linux / macOS 行为一致；
- **清单是一等公民**：快照可落盘、可传输、可审计，diff / verify 可脱离
  源目录单独执行；robocopy / rsync 的比较与传输耦合在一次运行里；
- **显式安全模型**：清单路径强校验 + 写前源文件哈希复核 + 原子替换；
- **不做的事**：不增量传输（无 rsync 的分块校验和协议）、不保留 ACL /
  扩展属性 / 硬链接，适合普通文件树的整目录同步场景。

## 本机实测

环境：Python 3.14.4，Linux x86-64。运行 `python3 bench.py` 复现。
耗时与内存分开测量（tracemalloc 不进计时窗口）：

| 项目 | 规模 | 耗时 | 峰值内存 |
| --- | --- | --- | --- |
| snapshot | 2000 文件 / 40 MiB | 0.066 s | 1.8 MiB |
| diff | 50000 条目清单 | 0.027 s（要求 < 1 s） | 4.6 MiB |
| apply | 2000 文件 | 0.262 s | 1.4 MiB |

## 测试

```bash
python3 -m unittest test_dirsync -v
```

覆盖：清单确定性、JSON 往返、分块哈希（0 字节与 >8 MiB）、空目录、
非 ASCII 与空格文件名、忽略规则顺序与 `!` 重新包含、非法路径、
diff 四类结果、apply 原子性与幂等、prune 开关、dry_run、
dry_run 下目标 mtime 与内容不变、源文件被改动时报错、
verify 检出篡改与多余条目。

## 模块结构

| 模块 | 职责 |
| --- | --- |
| `dirsync/manifest.py` | 快照生成、清单 JSON 序列化与校验 |
| `dirsync/diff.py` | 两份清单的哈希表差异计算 |
| `dirsync/apply.py` | 按清单同步目标目录、verify 校验 |
| `dirsync/paths.py` | 相对路径安全校验、忽略规则匹配 |
| `dirsync/errors.py` | 异常类型（`ManifestError` / `ApplyError`） |
