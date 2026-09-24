"""性能基准：分别测量耗时与峰值内存。

耗时与内存分两轮独立运行：tracemalloc 只在内存轮开启，其追踪开销不计入
耗时轮的计时窗口。稀疏表达式（每年一次）取 10 万个触发时刻会跨越约 10 万
年，远超 datetime 的 9999 年上限，因此稀疏场景直接在内部 (年,月,日,时,分)
五元组上推进（历法使用纯整数算术）；高频“每分钟”只跨约 69 天，正常返回
datetime 列表。
"""

import tracemalloc

from cronspec import parse
from cronspec.engine import next_tuple
from datetime import datetime


COUNT = 100_000


def generate_tuples(schedule, start, count):
    year, month, day = start.year, start.month, start.day
    hour, minute = start.hour, start.minute
    result = []
    for _ in range(count):
        year, month, day, hour, minute = next_tuple(
            schedule, year, month, day, hour, minute
        )
        result.append((year, month, day, hour, minute))
    return result


def generate_datetimes(schedule, start, count):
    return schedule.next_n(start, count)


def measure(name, generator):
    # 第一轮：只测耗时，不开启 tracemalloc。
    elapsed_result = generator()
    start_clock = _perf_now()
    timed_result = generator()
    elapsed_ms = (_perf_now() - start_clock) * 1000

    # 第二轮：只测峰值内存；计时不与追踪窗口重叠。
    del elapsed_result, timed_result
    tracemalloc.start()
    memory_result = generator()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(
        "%-28s %8d 个  耗时 %8.2f ms   峰值内存 %8.2f MiB   末项 %s"
        % (name, COUNT, elapsed_ms, peak / 1024 / 1024, memory_result[-1])
    )


def _perf_now():
    from time import perf_counter

    return perf_counter()


def main():
    yearly = parse("0 0 1 1 *")
    leap = parse("0 0 29 2 *")
    every_minute = parse("* * * * *")

    print("每个场景独立运行两轮（一轮纯计时、一轮 tracemalloc 测内存）：\n")
    measure(
        "稀疏：每年 1 月 1 日（五元组）",
        lambda: generate_tuples(yearly, datetime(2020, 1, 1), COUNT),
    )
    measure(
        "稀疏：闰年 2 月 29 日（五元组）",
        lambda: generate_tuples(leap, datetime(2020, 1, 1), COUNT),
    )
    measure(
        "高频：每分钟（datetime）",
        lambda: generate_datetimes(
            every_minute, datetime(2020, 1, 1), COUNT
        ),
    )


if __name__ == "__main__":
    main()
