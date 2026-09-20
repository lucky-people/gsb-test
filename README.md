# textdiff：文本差异与三方合并引擎

仅使用 Python 标准库实现的行级差异、unified diff、补丁精确套用与三方合并。
核心 Myers 差分算法完全自研，**不依赖、不调用 `difflib`，也不调用系统
`diff`/`patch`**。

## 安装与使用

无需安装任何第三方依赖，直接把 `textdiff/` 放进项目即可（需要 Python 3.10+，
仅因使用了 `slots=True` 的 dataclass）。

```python
import textdiff

textdiff.diff(a, b)          # -> list[Edit]，最短编辑脚本
textdiff.unified(a, b, 3)    # -> 标准 unified diff 文本
textdiff.apply(a, patch)     # -> 精确套用补丁后的新文本
textdiff.merge(base, ours, theirs)  # -> MergeResult（merged + conflicts）
```

对外只暴露 `diff` / `unified` / `apply` / `merge` 四个接口。
`Edit`、`Line`、`PatchError`、`MergeResult`、`Conflict` 等类型可从
对应子模块（`textdiff.myers`、`textdiff.errors`、`textdiff.merge`）导入。

## Edit 与四种操作

`Edit` 是不可变数据类，字段为：

- `tag`：`equal` / `delete` / `insert` / `replace`
- `a_start, a_end`：旧文本（a）中的半开行下标
- `b_start, b_end`：新文本（b）中的半开行下标

约定：

- `delete` 只占 a 区间，b 区间为空（`b_start == b_end`）；
- `insert` 只占 b 区间，a 区间为空；
- `replace` 两侧区间都非空，表示一段「先删除若干旧行、再插入若干新行」，
  **删除行始终排在插入行之前**；
- 所有编辑块首尾相接，恰好覆盖 a 与 b 的全部行（既是 a 的划分也是 b 的划分）。

## 算法说明（Myers 与 D、snake）

实现在 `textdiff/myers.py`。

把 a、b 看成编辑网格，节点 `(x, y)` 表示「已消费 a 的前 x 行、b 的前 y 行」：

- 向右走一步 = 删除一行 a；向下走一步 = 插入一行 b；二者都计 1 次编辑；
- 沿对角线 `k = x - y` 前进 = 匹配到一对相等行，不计编辑次数。

关键概念：

- **D**：当前路径使用的编辑次数（删除数 + 插入数）。算法按 `D = 0,1,2,…`
  逐层搜索，第一个到达终点 `(N, M)` 的 D 就是最短编辑距离。
- **snake（蛇形段）**：在某条 k 线上做完一次删除或插入后，连续匹配
  相等行而形成的零成本对角延伸。每个 `(D, k)` 只记录沿该 k 线能走到的
  最远点 `V[k] = x`。

前向递推：

```
若 k == -D：                 x = V[k+1]        # 只能从下方插入
若 k ==  D：                 x = V[k-1] + 1    # 只能从右侧删除
若 V[k-1] < V[k+1]：         x = V[k+1]        # 取插入步
否则：                       x = V[k-1] + 1    # 取删除步
再沿对角线吃 snake：while a[x] == b[y]: x++; y++
```

实现中为每条 `(D, k)` 同时记录前驱 k 线，到达终点后沿父指针回溯：
先按坐标差回退 snake（产出 `equal` 事件），再回退一条删除或插入边，
最终把逆序事件翻转，并用扫描游标折叠成 `equal/delete/insert/replace` 块。

### 公共前缀 / 后缀归并

进入 Myers 之前，先线性归并两份输入的公共前缀与公共后缀，只对中间差异段
运行算法。这对「10 万行、只改几十处」的真实文本至关重要：改动点两侧的
大段相同内容被整体跳过，中间段往往只有几十行。

## 复杂度分析

- 时间：Myers 为 **O((N+M)·D)**，其中 D 为最短编辑距离；
  公共前后缀归并为 O(N+M)；事件折叠与 hunk 构造均为线性。
- 空间：O((N+M)·D) 的历史 V 快照（实现中按 D 层保存字典），
  加上 O(N+M) 的行数组与编辑块。
- **不会退化成 O(N·M) 时间或内存**：不存在 N×M 的完整 DP 矩阵。
  近相似文本 D 很小（几十），实测见下节。
- 补丁套用 `apply` 为 O(原文行数 + 补丁行数) 的单次线性扫描，顺序套行。
- 三方合并运行两次 Myers，再做一次线性区间聚类，仍为近线性。

## 本机实测（bench.py）

运行 `python bench.py`。环境：Windows + CPython 3.12，10 万行、40 处
稀疏差异（含修改 / 插入 / 删除），文本约 4 MiB：

| 操作     | 耗时（秒） | 峰值内存（tracemalloc） |
|----------|-----------:|------------------------:|
| diff     | ~0.36       | ~40 MiB                 |
| unified  | ~0.85       | ~40 MiB                 |
| apply    | ~0.22       | ~27 MiB                 |
| merge    | ~0.82       | ~53 MiB                 |

其中 Myers 差分本身（行已切分、公共前后缀已归并）仅约 0.06–0.08 秒；
大部分时间花在 10 万行文本的切分与重建。墙钟时间在**不启用**
`tracemalloc` 时测量；峰值内存单独用一次带追踪的运行统计
（开启追踪会让同段代码慢数倍，因此两个数字分别测量）。
不同机器的绝对值会有差异，请以本机 `python bench.py` 输出为准。

## unified diff

`unified(a, b, context=3)` 生成标准 unified diff：

- 文件头固定为 `--- a` / `+++ b`（本引擎只处理文本内容，没有真实文件名）；
- hunk 头形如 `@@ -旧始,旧计 +新始,新计 @@`，起始号 1 基、计数为 1 时省略；
  纯插入 hunk 旧侧为 `0,0`，纯删除 hunk 新侧为 `0,0`；
- 每个 hunk 两端最多带 `context` 行上下文；两个改动之间放不下
  `2*context+1` 行公共上下文时合并为同一 hunk；
- replace 块内部夹着的相等行以上下文（空格前缀）按文档顺序穿插输出，
  真正替换处仍是先 `-` 后 `+`；
- 两份输入完全相同时返回**空字符串**；
- 末尾**没有换行**的行在 `-`/`+`/空格行之后输出
  `\ No newline at end of file` 标注。

## 补丁套用 apply

`apply(text, patch)` 对 unified diff 做**严格精确**套用：

- 按 hunk 头的旧侧起始号定位，随后逐行核对每条上下文/删除行的**完整内容
  （含行终止符）**；
- 上下文不匹配、行号越界、hunk 之间位置重叠、头计数与正文行数不符、
  补丁缺少合法文件头或 hunk 头等，一律抛 `textdiff.errors.PatchError`，
  **绝不「尽力猜」地静默套用**；
- 异常信息为中文，并带 `hunk_index`（从 1 起）、`line_no`、
  `expected`、`actual` 字段，便于定位；
- 空补丁表示不做任何修改，原样返回；
- 往返恒成立：`apply(a, unified(a, b)) == b`（含 CRLF、无结尾换行等情况）。

## 三方合并 merge

`merge(base, ours, theirs)` 分别计算 base→ours、base→theirs 两条最短
编辑脚本，以 base 行坐标为改动区间做线性聚类（区间相交，或插入点相同
`[p,p)` 相接，归为一簇）：

- 只有一侧改动：自动采用该侧结果；
- 两侧都改但合并区间内逐行渲染结果相同：视为双方一致，**不产生冲突**；
- 两侧改了同一处且结果不同：输出标准冲突标记
  ```
  <<<<<<< ours
  我们的内容
  =======
  对方的内容
  >>>>>>> theirs
  ```
- 相邻但不重叠的改动自动拼接；
- 返回 `MergeResult`：`merged`（合并文本）、`conflicts`（`Conflict` 列表）、
  `has_conflicts`；
- 每个 `Conflict` 带可定位回**共同祖先原文行号**的区间
  `base_start/base_end`（1 基半开；纯插入点冲突用插入点位置，0=文件开头、
  N=第 N 行之后），以及 `ours_lines` / `theirs_lines`（两侧完整行文本）、
  来源标签与 `source` 属性；
- 若冲突前最后一行没有换行，引擎会在冲突标记前补一个换行，
  保证 `<<<<<<<` 等标记始终另起一行、不与正文粘连。

## 边界与健壮性取舍

- **空串**：建模为 0 行。空 → 非空、非空 → 空都能正确生成 / 套用；
  空串 → 空串的 unified 结果为空串。
- **单行、无结尾换行**：作为 1 行且 `ending == ""` 保存；
  diff/unified/apply/merge 全程保留该状态，并正确输出「未结束」标注。
- **CRLF 与 LF 混用**：切分时用正则 `\r\n | \n | \r` 识别终止符，
  行内容与终止符分开存放，保证**不吞任何字符、也不把 `\r` 混进内容**；
  单独的 `\r`（经典 Mac 风格）也按行终止符处理。
- **行终止符是行身份的一部分**：仅结束符不同（`a\n` ↔ `a\r\n`）也算差异，
  引擎不会擅自规范化换行符；输出与套用严格逐字节保真。
- **超长行**：行是不透明字符串，长度无特殊限制，按整行比较。
- **大量重复行**：Myers 对重复内容仍是最短脚本；公共前后缀归并先吃掉
  两侧大段相同行，重复场景不会触发 N×M 矩阵。
- **两侧完全相同**：diff 得到单个 equal 块，unified 返回空串，
  apply 原样返回，merge 无冲突。
- **确定性**：相同输入多次调用得到完全一致的结果；同长度 k 线的
  tie-break 固定（优先删除步），删除始终排在插入之前。

## 与 difflib 的行为差异

- 本引擎实现的是 Myers 的**最短编辑脚本（插入+删除距离，D = N+M−2·LCS）**，
  保证编辑次数最少；`difflib.SequenceMatcher` 采用「启发式垃圾块剔除 +
  最长匹配」策略，**不保证**编辑脚本最短，在重复元素上甚至可能给出反直觉
  的对齐结果。
- 本引擎把连续的「删除段 + 插入段」显式折叠成语义化的 `replace` 块，
  且保证删除先于插入；`difflib` 只给 `replace/delete/insert/equal`
  opcode，不额外约束删除与插入的相对排列。
- 本引擎把行终止符作为行身份的一部分严格比较（LF↔CRLF 算差异），
  不做 `difflib` 那类可配置的「垃圾行 / 自动 junk」宽松匹配。
- 本引擎的 `apply` 是严格模式：任何不符即抛带 hunk 序号与期望/实际内容的
  `PatchError`；不存在 fuzz（模糊偏移套用）。
- 输出仅包含 `--- a` / `+++ b` 头与 hunk，不写时间戳、文件模式等
  git 扩展字段，聚焦纯文本内容。

## 目录结构

```
textdiff/
  __init__.py   对外只暴露 diff / unified / apply / merge
  myers.py      行切分、Line/Edit 类型、Myers 最短编辑脚本
  patch.py      unified diff 生成与补丁解析/精确套用
  merge.py      三方合并与冲突结构
  errors.py     PatchError 自定义异常
test_textdiff.py 标准库 unittest 测试（33 个用例）
bench.py        10 万行近似文本的耗时 / 峰值内存基准
```

运行测试：

```
python -m unittest test_textdiff -v
```

运行基准：

```
python bench.py
```
