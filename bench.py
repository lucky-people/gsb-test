"""lzpack 性能测试：耗时与内存分开测量（tracemalloc 不进计时窗口）。

用法: python3 bench.py
"""

import random
import time
import tracemalloc

import lzpack


def make_datasets():
    rng = random.Random(20260924)
    random_1mb = rng.randbytes(1 << 20)
    repeated_1mb = (b"the quick brown fox jumps over the lazy dog. " * 24000)[:1 << 20]
    log_line = b"2026-09-24 12:00:00.123 INFO  [worker-3] 10.0.0.7 GET /api/v1/items 200 12ms\n"
    logs_10mb = log_line * (10 * 1024 * 1024 // len(log_line))
    return [
        ("1 MB 随机数据", random_1mb),
        ("1 MB 重复数据", repeated_1mb),
        ("10 MB 日志文本", logs_10mb),
    ]


def measure_time(data):
    t0 = time.perf_counter()
    blob = lzpack.compress(data)
    t1 = time.perf_counter()
    out = lzpack.decompress(blob)
    t2 = time.perf_counter()
    assert out == data
    return blob, t1 - t0, t2 - t1


def measure_memory(data):
    """单独跑一轮，用 tracemalloc 测压缩 / 解压各自的峰值内存。"""
    tracemalloc.start()
    blob = lzpack.compress(data)
    _, peak_c = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    tracemalloc.start()
    lzpack.decompress(blob)
    _, peak_d = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak_c, peak_d


def main():
    print("%-14s %10s %10s %10s %10s %10s" % (
        "数据集", "压缩(s)", "解压(s)", "压缩率", "压缩峰值", "解压峰值"))
    for name, data in make_datasets():
        blob, tc, td = measure_time(data)
        peak_c, peak_d = measure_memory(data)
        print("%-14s %10.3f %10.3f %9.2f%% %8.1fMB %8.1fMB" % (
            name, tc, td, len(blob) / len(data) * 100,
            peak_c / 1048576, peak_d / 1048576))


if __name__ == "__main__":
    main()
