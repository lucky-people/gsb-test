"""性能基准：10 万行、只差几十处的近似文本。

分别测量 diff / unified / apply / merge 的墙钟耗时，
并用标准库 tracemalloc 统计 Python 层的峰值内存占用。
直接运行：``python bench.py``。
"""

from __future__ import annotations

import time
import tracemalloc

import textdiff


LINE_COUNT = 100_000
CHANGE_COUNT = 40


def build_texts() -> tuple[str, str, str, str]:
    """构造共同祖先 base、改版 ours/theirs 与目标 target。

    每行带稳定且唯一的 ID，三份改版都「按 ID 有序重建」，
    因此几十处插入/删除不会让其余行在位置上整体错位，
    其余行始终能按内容精确对齐——这正是真实代码小改动的形态。
    """
    base_lines = [f"id={index:06d} padding padding padding padding\n"
                  for index in range(LINE_COUNT)]
    rows = [1000 + index * 2400 for index in range(CHANGE_COUNT)]
    modify_rows = {row for index, row in enumerate(rows) if index % 3 == 0}
    insert_rows = {row for index, row in enumerate(rows) if index % 3 == 1}
    delete_rows = {row for index, row in enumerate(rows) if index % 3 == 2}

    def rebuild(repl, ins, dele):
        out = []
        append = out.append
        for index, line in enumerate(base_lines):
            if index in ins:
                append(ins[index])
            if index not in dele:
                append(repl.get(index, line))
        return out

    target = rebuild(
        {row: f"id={row:06d} TARGET-CHANGED\n" for row in modify_rows},
        {row: f"id=T{row:06d} TARGET-INSERT padding\n" for row in insert_rows},
        delete_rows)
    ours = rebuild(
        {row: f"id={row:06d} OUR-CHANGED\n" for row in modify_rows},
        {row: f"id=O{row:06d} OUR-INSERT padding\n" for row in insert_rows},
        set())
    theirs = rebuild(
        {row: f"id={row:06d} THEIR-CHANGED\n" for row in modify_rows},
        {},
        set())
    return ("".join(base_lines), "".join(target),
            "".join(ours), "".join(theirs))


def measure(label: str, func) -> None:
    """墙钟耗时在不追踪内存时测量，避免 tracemalloc 把速度拖慢数倍；
    峰值内存单独用一次带追踪的运行统计。"""
    result = func()  # 预热（含字节码/模块级缓存）

    start = time.perf_counter()
    result = func()
    elapsed = time.perf_counter() - start

    tracemalloc.start()
    func()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    size = len(result) if isinstance(result, str) else 0
    print(f"{label:<10} 耗时 {elapsed:8.3f} 秒   "
          f"峰值内存 {peak / 1024 / 1024:8.2f} MiB   结果 {size:>10} 字符")


def main() -> None:
    base, target, ours, theirs = build_texts()
    print(f"基准规模：{LINE_COUNT:,} 行，约 {CHANGE_COUNT} 处差异；"
          f"base 大小 {len(base) / 1024 / 1024:.2f} MiB\n")

    patch_text = ""

    def run_diff():
        return textdiff.diff(base, target)

    def run_unified():
        nonlocal patch_text
        patch_text = textdiff.unified(base, target)
        return patch_text

    def run_apply():
        return textdiff.apply(base, patch_text)

    def run_merge():
        return textdiff.merge(base, ours, theirs).merged

    run_diff()
    start = time.perf_counter()
    edits = run_diff()
    elapsed = time.perf_counter() - start
    tracemalloc.start()
    edits = run_diff()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"{'diff':<10} 耗时 {elapsed:8.3f} 秒   "
          f"峰值内存 {peak / 1024 / 1024:8.2f} MiB   "
          f"{len(edits):>6} 个编辑块")

    measure("unified", run_unified)
    measure("apply", run_apply)
    measure("merge", run_merge)

    # 正确性自检：往返必须成立。
    assert textdiff.apply(base, patch_text) == target, "apply 往返不一致"
    print("\n正确性自检通过：apply(base, unified(base, target)) == target")


if __name__ == "__main__":
    main()
