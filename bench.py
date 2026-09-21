"""cronspec 性能基准：稀疏表达式与高频表达式各取 10 万个触发时刻。

计时与峰值内存分别独立测量，互不污染：
- 耗时：perf_counter 窗口内不启用 tracemalloc，避免追踪开销计入。
- 内存：单独在 tracemalloc 窗口内再跑一遍，只报告 tracemalloc 记录的
  Python 层峰值增量（测试框架自身的常驻对象不计入）。

稀疏表达式（每年 1 月 1 日、闰年 2 月 29 日）会推进到公元数万年，
远超 datetime 的年份上限（9999），因此这部分使用引擎内部的整数元组
迭代器（与公开 API 同一套按字段推进算法，只是不做 datetime 包装）；
高频表达式同时给出公开 datetime API 的数据作为对照。
"""

from __future__ import annotations

import tracemalloc
import time
from datetime import datetime

from cronspec import parse

N = 100_000


def _measure_time(expr: str, start_tuple) -> float:
    schedule = parse(expr)
    iterator = schedule._iter_tuples(start_tuple)
    start = time.perf_counter()
    count = 0
    for _ in iterator:
        count += 1
        if count == N:
            break
    return time.perf_counter() - start


def _measure_memory(expr: str, start_tuple) -> int:
    """返回取 N 个触发时刻期间的 Python 层峰值内存（字节）。"""
    schedule = parse(expr)
    tracemalloc.start()
    count = 0
    for value in schedule._iter_tuples(start_tuple):
        count += 1
        if count == N:
            break
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def _measure_time_datetime(expr: str, start_dt: datetime) -> float:
    schedule = parse(expr)
    start = time.perf_counter()
    schedule.next_n(start_dt, N)
    return time.perf_counter() - start


def _measure_memory_datetime(expr: str, start_dt: datetime) -> int:
    schedule = parse(expr)
    tracemalloc.start()
    schedule.next_n(start_dt, N)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def _human(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / 1024 / 1024:.2f} MiB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KiB"
    return f"{num_bytes} B"


def main() -> None:
    cases = (
        ("每年 1 月 1 日", "0 0 1 1 *", (2020, 1, 1, 0, 0)),
        ("闰年 2 月 29 日", "0 0 29 2 *", (2020, 1, 1, 0, 0)),
        ("每分钟（内部元组迭代器）", "* * * * *", (2020, 1, 1, 0, 0)),
    )

    print(f"每个表达式取 {N:,} 个触发时刻；计时与内存分开测量\n")
    for label, expr, start_tuple in cases:
        elapsed = _measure_time(expr, start_tuple)
        peak = _measure_memory(expr, start_tuple)
        print(f"[{label}]  {expr!r}")
        print(f"    耗时     : {elapsed:.4f} s（{N / elapsed:,.0f} 个/秒）")
        print(f"    峰值内存 : {_human(peak)}（仅保留结果列表的迭代过程）")
        print()

    # 高频表达式的公开 datetime API 对照（受 datetime 年份限制，可完整执行）
    elapsed = _measure_time_datetime("* * * * *", datetime(2020, 1, 1))
    peak = _measure_memory_datetime("* * * * *", datetime(2020, 1, 1))
    print("[每分钟（公开 datetime API 对照）]  '* * * * *'")
    print(f"    耗时     : {elapsed:.4f} s（{N / elapsed:,.0f} 个/秒）")
    print(f"    峰值内存 : {_human(peak)}（含 {N:,} 个 datetime 的结果列表）")


    # README 中引用的「连续取 1000 个」性能门（公开 datetime API）
    print()
    print("-- 公开 datetime API：从 2020-01-01 00:00 连续取 1000 个触发时刻 --")
    for label, expr in (
        ("每年 1 月 1 日", "0 0 1 1 *"),
        ("闰年 2 月 29 日", "0 0 29 2 *"),
    ):
        schedule = parse(expr)
        start = datetime(2020, 1, 1)
        begin = time.perf_counter()
        schedule.next_n(start, 1000)
        elapsed1k = time.perf_counter() - begin

        tracemalloc.start()
        schedule.next_n(start, 1000)
        _, peak1k = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"[{label}] {expr!r}  耗时 {elapsed1k * 1000:.2f} ms，"
              f"峰值内存 {_human(peak1k)}")


if __name__ == "__main__":
    main()
