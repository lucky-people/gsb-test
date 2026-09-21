"""性能基准：10 万行近似文本上的 diff / unified / apply / merge。

直接运行：python bench.py
只用标准库；耗时用 time.perf_counter，峰值内存用 tracemalloc。
"""

import time
import tracemalloc

from textdiff import apply, diff, merge, unified

N_LINES = 100_000
N_CHANGES = 40  # 几十处差异


def build_texts():
    """构造两份 10 万行、只差几十处的近似文本。

    差异包括修改、插入、删除三种；三方合并的两侧改动互不相邻。
    """
    base = [f"line-{i:06d}\n" for i in range(N_LINES)]

    changed = base.copy()
    touched = set()
    mid = N_LINES // 2
    for k in range(N_CHANGES // 3):
        idx = 1000 + k * 1500
        changed[idx] = f"modified-{idx}\n"
        touched.add(idx)
    for k in range(N_CHANGES // 3):
        idx = 2000 + k * 1700
        changed.insert(idx, f"inserted-{idx}\n")
    for k in range(N_CHANGES - 2 * (N_CHANGES // 3)):
        idx = 3000 + k * 1900
        if idx < len(changed):
            changed.pop(idx)

    # ours 改前半段、theirs 改后半段，保证是干净合并
    ours = base.copy()
    for idx in range(500, 10_000, 300):
        ours[idx] = f"ours-{idx}\n"
    theirs = base.copy()
    for idx in range(mid + 500, mid + 10_000, 300):
        theirs[idx] = f"theirs-{idx}\n"

    return ("".join(base), "".join(changed), "".join(ours), "".join(theirs))


def measure(label, func):
    start = time.perf_counter()
    tracemalloc.start()
    result = func()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed = time.perf_counter() - start
    print(f"{label:<10} 耗时 {elapsed:8.3f} s   峰值内存 {peak / 1024 / 1024:8.1f} MiB")
    return result


def main():
    base, changed, ours, theirs = build_texts()
    print(f"输入规模：{N_LINES} 行，差异约 {N_CHANGES} 处\n")

    edits = measure("diff", lambda: diff(base, changed))
    patch = measure("unified", lambda: unified(base, changed))
    restored = measure("apply", lambda: apply(base, patch))
    result = measure("merge", lambda: merge(base, ours, theirs))

    assert restored == changed, "apply 往返不一致"
    assert not result.has_conflicts, "基准合并应当无冲突"
    print(f"\n校验通过：编辑段数 {len(edits)}，合并结果 {len(result.text.splitlines())} 行")


if __name__ == "__main__":
    main()
