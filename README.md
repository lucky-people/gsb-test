# lzpack

纯 Python 标准库实现的 LZ77 压缩库。不依赖 zlib / lzma / bz2 / gzip，
哈希链匹配、变长整数、CRC32 全部自己实现。

```python
import lzpack

blob = lzpack.compress(b"hello hello hello", level=6, window=32768)
data = lzpack.decompress(blob)

c = lzpack.Compressor(level=6, window=32768)   # 流式压缩
out = c.feed(b"hello ") + c.feed(b"hello ") + c.finish()

d = lzpack.Decompressor()                       # 流式解压
raw = d.feed(out[:5]) + d.feed(out[5:]) + d.finish()
```

- `compress(data, *, level=6, window=32768) -> bytes`
- `decompress(blob) -> bytes`
- `Compressor(level=6, window=32768)`：`.feed(chunk) -> bytes`，`.finish() -> bytes`
- `Decompressor()`：`.feed(chunk) -> bytes`，`.finish() -> bytes`
- 异常：`lzpack.errors.FormatError`（带 `offset` 与中文说明）、`lzpack.errors.ConfigError`

## 流格式

多字节整数均为小端。整体布局：**头部 + 数据块（token 序列）**，流结束即数据结束。

### 头部字段偏移表

| 偏移 | 长度 | 含义 |
|------|------|------|
| 0    | 4    | 魔数 `4C 5A 50 4B`（`"LZPK"`） |
| 4    | 1    | 版本号，当前为 `0x01` |
| 5    | 1    | 元数据：高 4 位 = `log2(window) - 10`，低 4 位 = `level` |
| 6    | 变长 | 原始数据长度，LEB128 变长整数（1~9 字节） |
| ...  | 1    | 头部校验字节 = `crc32(版本+元数据+长度字段) & 0xFF` |
| ...  | 4    | 原始数据的 CRC32，小端 |
| ...  | ...  | 数据块：token 序列 |

### 数据块编码

每个 token 以 1 字节标签开头：

| 标签 | 含义 |
|------|------|
| `0x00..0x7F` | 字面量块：长度 = 标签 + 1（1..128），随后是原样字节 |
| `0x80..0xFE` | 匹配：长度 = 3 + (标签 − 0x80)，即 3..129 |
| `0xFF`       | 长匹配：长度 = 130 + 变长整数 |

匹配标签之后跟一个变长整数：**偏移 − 1**。

明确上限：

- 匹配长度：`3 .. 16384`（`MIN_MATCH..MAX_MATCH`）
- 匹配偏移：`1 .. window`（window 最大 1 MB，偏移 − 1 的变长整数最多 3 字节）
- 变长整数：最多 9 字节，超长即 `FormatError`

### 为什么这样设计

- **头部校验字节**：魔数、版本、元数据、长度任何一个字段被改动都能在
  读完头部时立刻报 `FormatError`，而不是解压到一半才发现；
- **CRC32 校验完整解压结果**：数据块任何损坏（包括 token 边界错位导致的
  长度不符）都会在 `finish()` 时被拒绝，绝不静默返回半截数据；
- **字面量块原样存储**：不可压缩数据每 128 字节只有 1 字节开销（约 0.8%），
  保证随机数据膨胀率 < 2%；
- **变长整数**：短偏移（绝大多数）只占 1~2 字节，长偏移也不浪费；
- **元数据进头部**：解压端按头部声明的 window 校验偏移合法性，
  偏移越界即格式错误。

## 匹配查找策略与复杂度

- 3 字节乘积散列 + 哈希链：`head` 表指向最近位置，`prev` 是 window 大小
  的环形数组（window 为 2 的幂，用位与取模），内存 O(window)；
- 每个位置沿链向后找最长匹配，**level 决定最大链搜索深度**
  （level 1 → 4，level 9 → 1024），并有 “nice length” 提前终止；
- 匹配长度 ≥ 64 时跳过匹配内部位置的插入——长重复数据（日志、全 0）
  下避免逐字节维护哈希表。

复杂度：设链长上限为 c（有界常数），平均时间 O(n·c) = **O(n)**，
不会出现朴素实现的 O(n²)；空间 O(window + 输出缓冲)。

## level 与 window 的取舍

- `level`（1..9）：只影响**压缩端**的搜索深度与提前终止阈值。
  level 越高压缩率不劣于低 level（允许相等），代价是压缩更慢；
  解压耗时与 level 无关。
- `window`（1KB..1MB，2 的幂）：决定匹配可回溯的最大距离，也决定
  `prev` 数组内存（window × 4 字节）。重复间隔大于 window 的内容
  无法匹配；日志类数据 32KB 通常足够，大文件去重可开到 1MB。

## 与 gzip / zlib 的差异

- gzip/zlib 是 LZ77 + **霍夫曼编码**，lzpack 只做 LZ77 + 字节对齐的
  token 编码，不做熵编码——因此压缩率低于 gzip，但格式简单、
  可以逐字节解析，解压端无需维护码表；
- gzip 的 CRC32 在流尾，lzpack 放在头部（解压前就知道期望值），
  并额外加了头部校验字节；
- lzpack 的 `Compressor` 为保证与一次性 `compress()` **逐字节等价**
  （匹配可跨 feed 边界），内部缓冲全部输入、`finish()` 时一次编码；
  gzip 的流式压缩则是边喂边出。这是本库有意的取舍：牺牲流式内存，
  换取“分块喂入 == 一次性调用”的强保证。

## 边界行为（均有测试覆盖）

- 空输入：合法流，只有 12 字节头部，解压为 `b""`；
- 单字节 / 全 0 数据：正常往返，全 0 高度可压；
- 匹配长度上限 16384，超限拆成多个匹配；偏移超过 window 的重复不算匹配；
- 跨 feed 边界的匹配：流式与一次性输出逐字节相同；
- 偏移正好等于 window（如 32768）的匹配合法；
- CRC 字段被改成全 0 / 全 0xFF：`FormatError`；
- 重复调用 `finish()` 返回 `b""`；`finish()` 后再 `feed()` 抛 `ValueError`；
- 长度字段与实际不符、头部 4 字节不是魔数、任意截断：`FormatError`；
- 不可压缩数据：原样存储为字面量块，膨胀约 0.8%。

## 本机实测

环境：Python 3.14.4，Linux x86-64。耗时与内存分开测量
（tracemalloc 不进计时窗口），复现：`python3 bench.py`。

| 数据集 | 压缩耗时 | 解压耗时 | 压缩率 | 压缩峰值内存 | 解压峰值内存 |
|--------|---------:|---------:|-------:|------------:|------------:|
| 1 MB 随机数据   | 0.652 s | 0.100 s | 100.97% | 2.1 MB  | 3.2 MB  |
| 1 MB 重复数据   | 0.153 s | 0.093 s |   0.16% | 0.4 MB  | 3.0 MB  |
| 10 MB 日志文本  | 1.566 s | 0.898 s |   0.11% | 0.4 MB  | 30.8 MB |

说明：随机数据压缩率 > 100% 即字面量块开销（< 1%）；解压峰值内存
主要是已解压输出缓冲（匹配回引需要历史数据）。

## 运行测试

```bash
python3 -m unittest test_lzpack -v
```

## 文件结构

- `lzpack/__init__.py`：只暴露 `compress`、`decompress`、`Compressor`、`Decompressor`
- `lzpack/codec.py`：流格式、头部、CRC32、token 编解码、流式压缩/解压器
- `lzpack/lz77.py`：哈希链匹配查找（token 生成）
- `lzpack/varint.py`：LEB128 变长整数
- `lzpack/errors.py`：`FormatError` / `ConfigError`
- `test_lzpack.py`：unittest，覆盖验收基线与全部边界
- `bench.py`：性能与内存测量
