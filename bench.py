"""dirsync 性能基准：耗时与峰值内存分开测量（tracemalloc 不进计时窗口）。

测量项：
1. 2000 文件 / 40 MiB 目录的 snapshot
2. 5 万条目清单的 diff（要求 1 秒内）
3. 2000 文件的 apply
"""

import hashlib
import os
import random
import shutil
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dirsync import Manifest, ManifestEntry, apply, diff_manifests, snapshot

N_FILES = 2000
TOTAL_BYTES = 40 * 1024 * 1024  # 40 MiB
N_DIFF_ENTRIES = 50000


def build_tree(root):
    """构造 2000 个文件、总计 40 MiB 的目录树。"""
    rng = random.Random(2024)
    per_file = TOTAL_BYTES // N_FILES
    for i in range(N_FILES):
        rel = os.path.join(root, f"dir{i % 50:03d}", f"file{i:05d}.bin")
        os.makedirs(os.path.dirname(rel), exist_ok=True)
        with open(rel, "wb") as f:
            f.write(rng.randbytes(per_file))


def build_manifests():
    """构造两份 5 万条目的清单：1% 修改、1000 新增、1000 删除。"""
    old_entries = []
    for i in range(N_DIFF_ENTRIES):
        old_entries.append(ManifestEntry(
            f"dir{i % 200:03d}/file{i:06d}.bin", "file", 20480,
            hashlib.sha256(f"old-{i}".encode()).hexdigest(), None,
        ))
    new_entries = []
    for i in range(1000, N_DIFF_ENTRIES):  # 删除前 1000 条
        sha = hashlib.sha256(
            f"{'new' if i % 100 == 0 else 'old'}-{i}".encode()
        ).hexdigest()
        new_entries.append(ManifestEntry(
            f"dir{i % 200:03d}/file{i:06d}.bin", "file", 20480, sha, None,
        ))
    for i in range(1000):  # 新增 1000 条
        new_entries.append(ManifestEntry(
            f"dir999/new{i:06d}.bin", "file", 20480,
            hashlib.sha256(f"new-{i}".encode()).hexdigest(), None,
        ))
    return Manifest(old_entries), Manifest(new_entries)


def time_it(fn):
    start = time.perf_counter()
    result = fn()
    return time.perf_counter() - start, result


def peak_memory(fn):
    """单独用 tracemalloc 测峰值内存，不影响计时窗口。"""
    tracemalloc.start()
    fn()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def main():
    tmp = tempfile.mkdtemp(prefix="dirsync-bench-")
    try:
        src = os.path.join(tmp, "src")
        dst = os.path.join(tmp, "dst")
        print(f"构造测试目录: {N_FILES} 文件 / {TOTAL_BYTES // 1024 // 1024} MiB ...")
        build_tree(src)

        # ---- 计时（不挂 tracemalloc）----
        t_snapshot, manifest = time_it(lambda: snapshot(src))
        old_m, new_m = build_manifests()
        t_diff, diff = time_it(lambda: diff_manifests(old_m, new_m))
        t_apply, report = time_it(lambda: apply(src, manifest, dst))

        # ---- 内存（独立运行，tracemalloc 不进计时窗口）----
        m_snapshot = peak_memory(lambda: snapshot(src))
        m_diff = peak_memory(lambda: diff_manifests(old_m, new_m))
        dst2 = os.path.join(tmp, "dst2")
        m_apply = peak_memory(lambda: apply(src, manifest, dst2))

        def fmt_mem(n):
            return f"{n / 1024 / 1024:.1f} MiB"

        print()
        print("===== 计时结果 =====")
        print(f"snapshot ({N_FILES} 文件 / 40 MiB) : {t_snapshot:.3f} s")
        print(f"diff     ({N_DIFF_ENTRIES} 条目清单)     : {t_diff:.3f} s"
              f"  ({'达标 <1s' if t_diff < 1.0 else '超标 >=1s'})")
        print(f"apply    ({N_FILES} 文件)           : {t_apply:.3f} s")
        print()
        print("===== 峰值内存 (tracemalloc) =====")
        print(f"snapshot : {fmt_mem(m_snapshot)}")
        print(f"diff     : {fmt_mem(m_diff)}")
        print(f"apply    : {fmt_mem(m_apply)}")
        print()
        print(f"apply 正确性: created={report.created_count} "
              f"(应为 {N_FILES + 50}), verify 略")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
