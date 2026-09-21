在当前仓库用 Python 标准库实现一个「文本差异与三方合并引擎」，不引入任何第三方依赖，也不允许直接调用 difflib 或系统 diff 命令来完成核心算法。

功能要求：
1. 行级差异：diff(a: str, b: str) -> list[Edit]，用 equal / delete / insert / replace 四类操作描述，返回最短编辑脚本；公共前缀与后缀必须先归并，删除操作排在插入之前，同一对输入多次调用结果必须完全一致。
2. 算法自研：核心必须自己实现 Myers 差分算法（或等价的 O((N+M)·D) 最短编辑脚本算法），禁止 import difflib、禁止调用外部 diff/patch 程序。
3. unified 输出：unified(a, b, context=3) -> str 生成标准 unified diff 文本，--- / +++ 文件头、@@ -a,b +c,d @@ hunk 头、行号与计数都要准确；上下文行数可配；输入末尾没有换行时按 "\ No newline at end of file" 标注。
4. 补丁应用：apply(text, patch) -> str 精确套用 unified diff；上下文不匹配、hunk 行号越界、行内容与上下文不符时抛自定义异常 PatchError，异常信息要含 hunk 序号与期望/实际内容；禁止「尽力猜」地静默套用。往返必须成立：apply(a, unified(a, b)) == b。
5. 三方合并：merge(base, ours, theirs) -> MergeResult，给出合并后的文本、冲突块列表（每块带起止行与来源）；只有一侧修改的自动采用，两侧改成完全相同内容视为无冲突，两侧改了同一处且内容不同时产出 <<<<<<< / ======= / >>>>>>> 冲突标记；冲突块要能定位回原文行号。
6. 边界与健壮性：空串、单行无结尾换行、CRLF 与 LF 混用（切分不得吞字符、不得把 \r 混进行内容）、超长行、大量重复行、两侧完全相同、把 a 变成空、把空变成 a，都要有确定行为并写进 README。
7. 性能：两份 10 万行、只差几十处的近似文本做 diff，不能退化成 O(N·M) 的时间或内存；README 给出本机实测的耗时与峰值内存。

交付物：
- textdiff/ 包：__init__.py（对外只暴露 diff / unified / apply / merge）、myers.py、patch.py、merge.py、errors.py
- test_textdiff.py：标准库 unittest，必须覆盖：空串与无结尾换行、公共前后缀归并、CRLF 混用、重复行、unified 头行号正确性、apply 往返一致、apply 上下文不匹配抛 PatchError、三方合并的单侧修改 / 双侧同改 / 双侧冲突、冲突块数量与内容
- bench.py：构造 10 万行近似文本，报告 diff / unified / apply / merge 的耗时与峰值内存
- README.md：算法说明（D 与 snake 的含义）、复杂度分析、边界取舍、与 difflib 的行为差异

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本。
