# textdiff：纯标准库文本差异与三方合并引擎

只用 Python 标准库实现的行级 diff、unified diff 生成/套用、三方合并。
核心最短编辑脚本为自研 Myers 算法，**不 import `difflib`，也不调用任何外部
`diff`/`patch` 程序**。

## 对外接口

```python
from textdiff import diff, unified, apply, merge
```

- `diff(a: str, b: str) -> list[Edit]`：返回 `equal / delete / insert / replace`
  四类编辑操作组成的最短编辑脚本。
- `unified(a, b, context=3) -> str`：标准 unified diff 文本；`a == b` 时返回空串。
- `apply(text, patch) -> str`：严格套用补丁；任何对不上的情况抛 `textdiff.errors.PatchError`。
- `merge(base, ours, theirs) -> MergeResult`：`MergeResult.text` 为合并结果，
  `MergeResult.conflicts` 为冲突块元组，`MergeResult.has_conflicts` 表示是否有冲突。

`Edit` 字段：`op`、`start_a/end_a`、`start_b/end_b`（0 基半开区间）、
`lines_a/lines_b`（实际行，含行尾分隔符）。

## 算法说明

### D 与 snake 的含义

Myers 把编辑过程看成在编辑网格上从 `(0,0)` 走到 `(N,M)`：向右走一格表示删除
`a` 的一行（d 加 1），向下走一格表示插入 `b` 的一行（d 加 1），沿对角线走表示
保留一对相同的行（d 不变）。

- **D（编辑距离层）**：脚本中删除数 + 插入数。替换一行 = 删一行 + 插一行，
  因此算 2 层。D 最小的脚本就是最短编辑脚本（SES）。
- **snake（蛇形线）**：做完一次删除或插入后，沿对角线连续走过的、行内容两两相等
  的那段路径。算法在每个 D 层枚举所有可能的 k 对角线，维护 `V[k] = x`（在该对角
  线上能走到的最远 x 坐标），每走一步后沿 snake 尽量延伸。
- 前向搜索保存每一层的 `V` 快照（trace），到达 `(N,M)` 后从终点按相同的
  选路规则回溯，得到确定的单步路径，再归并成语义化的 `Edit` 序列。

### 公共前缀 / 后缀归并

调用 Myers 之前先剥离两侧相同的公共前缀与公共后缀，只对中间片段建网格：
近似文本的中间片段长度与“差异规模”成正比，避免在大段相同内容上做无用功。
前缀、后缀各作为一个 `equal` 编辑段返回。

### 操作规范化

回溯路径中的单步删除/插入会做两次规范化：

1. 同类相邻步骤合并（连续删除、连续插入、连续相等）；
2. 作用于同一处的删除与插入合并成一个 `replace`，并保证**删除侧排在插入侧之前**；
   对“先插后删”的等价最短路径（中间可能隔着对角线对齐）同样会配对成 `replace`。

选路规则（当两条路径代价相同时）在搜索与回溯中完全一致，因此同一对输入多次调用
结果逐字节相同。

### 复杂度

设两侧行数为 N、M，编辑距离为 D：

- 时间：最坏上界 `O((N+M)·D)`；经过前后缀归并后，近似文本（D 很小）实际只在
  差异区域附近工作。
- 搜索用一维 `V` 数组（O(D)），trace 保存 D 层快照，回溯存储为 O(D²)；
  D 很小时内存开销可忽略。10 万行只差几十处时，D 只有几十，trace 极小。

### unified diff 与补丁套用

- hunk 按“两个相邻改动之间的上下文间隙是否超过 `2*context`”决定是否合并；
  hunk 行列数遵循标准规则：行数 1 省略 `,1`，空区间用 `0` 与 `,0`，
  空文件插入起点为 `0`。
- 文件最后一行没有换行时，在该行之后输出 `\ No newline at end of file`。
- `apply` **严格按 hunk 头声明的行号对位**，逐行核对上下文与删除内容；
  行号越界、内容不符、补丁格式错误都会抛 `PatchError`，信息包含 hunk 序号以及
  期望/实际内容，绝不做模糊搜索或“尽力猜”式套用。

### 三方合并

分别求 `base→ours`、`base→theirs` 的最短编辑脚本，把非 `equal` 的相邻编辑归并成
若干“改动区间”，再用并查集把触碰同一处 base 区域的两侧改动分组：

- 只出现在一侧的改动 → 直接采用；
- 两侧改动区域互不相交 → 各自落地（含不同插入点的插入）；
- 两侧在同一区域改成完全相同的内容（含在同一插入点插入相同内容）→ 采用一份，
  不算冲突，且不会重复插入；
- 两侧在同一区域改成不同内容 → 输出
  `<<<<<<< ours` / `=======` / `>>>>>>> theirs` 冲突标记，并记录 `ConflictBlock`。

`ConflictBlock.base_start/base_end` 是 0 基半开区间，可直接定位回 base 原文：
替换/删除冲突为被覆盖的行区间；同一插入点的纯插入冲突为空区间
（`base_start == base_end`），值表示插入位置（在该行之前）。

## 边界行为（确定行为）

| 情况 | 行为 |
| --- | --- |
| 两个空串 | `diff` 返回 `[]`；`unified` 返回 `""`；`apply` 原样返回 |
| `a` 变成空串 | 单个 `delete`；hunk 头为 `@@ -1,n +0,0 @@` |
| 空串变成 `a` | 单个 `insert`；hunk 头为 `@@ -0,0 +1,n @@` |
| 无结尾换行 | 行对象 `sep=""`；unified 输出 `\ No newline at end of file`；往返保持无换行 |
| CRLF / LF 混用 | `\r\n` 与 `\n` 分别完整保留；行内容不含 `\r`；切分不吞任何字符 |
| 单独的 `\r` | 视为行内容（只有 `\r\n` 才被识别为行尾），与 Git 的默认行为一致 |
| 超长行 | 按整行比较，不做行内差异 |
| 大量重复行 | 由 Myers 的确定选路规则给出固定的最短脚本 |
| 两侧完全相同 | `diff` 只有一个 `equal`；`unified` 为空补丁；`merge` 直接采用 |
| 行尾变化 | 行内容相同但行尾（LF/CRLF/无）不同也算差异，保证 `apply` 往返后字节一致 |

切分函数 `split_lines` 满足恒等式 `join_lines(split_lines(s)) == s`。

## 与 difflib 的行为差异

- `difflib.unified_diff` 基于 SequenceMatcher 的启发式最长块匹配，**不保证
  最短编辑脚本**；本实现给出 Myers 意义下的最短脚本，替换表达为删除+插入
  （脚本代价计 2）。
- SequenceMatcher 在重复行场景会丢弃它认为“无趣”的匹配，结果依赖自动 junk
  启发式；本实现不丢弃任何匹配，选路规则固定，同输入严格同输出。
- 本实现把行尾差异（LF 与 CRLF 与无换行）视为行差异，天然支持 CRLF/LF 混用
  与无结尾换行的精确往返；`difflib` 把换行交给调用方处理，不提供无换行标记。
- 本实现的 `apply` 只按声明行号严格对位，没有模糊匹配（fuzz）与偏移搜索。
- hunk 合并依据是上下文间隙 `2*context`，与 GNU diff 的行为一致。

## 性能实测

基准脚本 `bench.py`：两份 10 万行文本（`line-000000`…`line-099999`），其中一侧
有约 40 处修改/插入/删除。

实测环境：AMD Ryzen 7 7735H（16 逻辑核）、CPython 3.14.4、
Linux（WSL2，内核 6.18）。每项预热 1 次后默认重复 5 次，耗时取中位数，
并给出最小–最大区间；峰值内存为 `tracemalloc` 统计的 Python 层分配峰值
（含输入文本与结果）：

| 阶段 | 中位耗时 | 最小–最大 | 峰值内存 |
| --- | --- | --- | --- |
| diff | 0.13 s | 0.10–0.15 s | 约 35 MiB |
| unified（含一次 diff） | 0.10 s | 0.09–0.12 s | 约 35 MiB |
| apply | 0.05 s | 0.04–0.05 s | 约 20 MiB |
| merge（两侧各 32 处不相邻改动，两次 diff） | 0.17 s | 0.17–0.19 s | 约 46 MiB |

测量口径（重要）：**计时轮与内存轮严格分开**。计时轮断言
`tracemalloc.is_tracing()` 为 `False`，真开着就直接报错退出，每项先预热 1 次
再重复 N 次；峰值内存由**单独一轮**开启 `tracemalloc` 统计。
**开启内存追踪会让同段代码慢数倍**——旧版 `bench.py` 先 `tracemalloc.start()`
再开始计时，把追踪开销算进了耗时，曾得出 diff 1.5 s / merge 3.7–4.5 s 量级的
数字，与新口径（diff 约 0.13 s / merge 约 0.17 s）相差一个数量级。
因此两份实现的性能数字**必须按同一口径比较**（耗时与内存是否分开测、
预热与重复次数、硬件环境），跨口径对比会得出数倍的假象差距。

近似文本不会退化为 O(N·M)：公共前后缀归并后只对 D 量级的中间片段建网格，
10 万行只差几十处时网格规模与几十处差异相关，而不是 10 万的平方。
可用 `python bench.py` 在本机复现：`--repeat N` 调整重复次数（计时轮总步数
随 N 线性增长，每次都真实调用，不复用上一轮结果），
`--out bench-result.json` 落盘结构化结果（含环境、口径、每次样本），
`--baseline bench-result.json` 与基线逐项对比（任一项中位耗时慢 20% 以上
即以非零退出码结束并指出是哪一项），
`python render_bench.py bench-result.json` 把结果渲染成 Markdown 表格。
脚本只用标准库，Windows 与 Linux 下均可直接运行。

## 目录结构

```
textdiff/
  __init__.py   包入口，对外只暴露 diff/unified/apply/merge
  myers.py      行切分与自研 Myers 最短编辑脚本
  patch.py      unified diff 生成与严格套用
  merge.py      三方合并与冲突块
  errors.py     PatchError 等自定义异常
test_textdiff.py 标准库 unittest 测试
bench.py        10 万行性能基准（计时/内存分离，可重复统计与基线对比）
render_bench.py 把 bench.py 的 JSON 结果渲染成 Markdown 表格
```

## 运行测试与基准

```bash
python -m unittest test_textdiff -v   # 42 个用例
python bench.py                        # 默认每项预热 1 次、计时 5 次
python bench.py --repeat 9 --out bench-result.json
python bench.py --baseline bench-result.json   # 回归检测（慢 20% 以上退出码为 1）
python render_bench.py bench-result.json       # 渲染 Markdown 表格
```
