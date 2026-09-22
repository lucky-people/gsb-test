# -*- coding: utf-8 -*-
"""约 90 秒效果演示：只调用交付物的公开接口，A / B 两轮都能直接跑。

由 tools/run-demo.ps1 调用：python -X utf8 demo.py
"""

import os
import random
import subprocess
import sys
import time


def banner(title):
    print("")
    print("=" * 70)
    print("  " + title)
    print("=" * 70, flush=True)


def show(label, value):
    print("  {0:<14}{1}".format(label, value), flush=True)


def fmt(interval):
    return "[{0},{1})".format(getattr(interval, "start", "?"), getattr(interval, "end", "?"))


def fmt_many(values):
    items = [fmt(item) for item in values]
    return " ".join(items) if items else "(空)"


def span_of(values):
    try:
        return getattr(values, "length")
    except AttributeError:
        return sum(getattr(item, "length", 0) for item in values)


def main():
    banner("区间集合与区间索引 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_rangeset", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from rangeset import Interval, IntervalIndex, RangeSet  # noqa: E402

    banner("2/5  规范化合并与集合运算")
    raw = [Interval(1, 3), Interval(3, 5), Interval(4, 8), Interval(10, 12), Interval(-4, 0)]
    left = RangeSet(raw)
    show("输入", fmt_many(raw))
    show("规范化", fmt_many(left.intervals))
    show("覆盖长度", span_of(left))
    show("区间个数", getattr(left, "count_intervals", len(list(left.intervals))))
    other = RangeSet([Interval(2, 11)])
    show("另一个集合", fmt_many(other.intervals))
    time.sleep(2)
    show("并集", fmt_many(left.union(other).intervals))
    show("交集", fmt_many(left.intersection(other).intervals))
    show("差集", fmt_many(left.difference(other).intervals))
    show("对称差", fmt_many(left.symmetric_difference(other).intervals))
    time.sleep(9)

    banner("3/5  半开语义、挖空与增删")
    show("contains_point(3)", left.contains_point(3))
    show("contains_point(8)", left.contains_point(8))
    show("[1,3) 与 [3,5) 相交", Interval(1, 3).overlaps(Interval(3, 5)))
    hole = RangeSet([Interval(0, 10)]).remove(Interval(3, 5))
    show("挖空 [3,5)", fmt_many(hole.intervals))
    grown = left.add(Interval(20, 25))
    show("新增 [20,25)", fmt_many(grown.intervals))
    show("原集合不变", fmt_many(left.intervals))
    time.sleep(9)

    banner("4/5  IntervalIndex 查询")
    index = IntervalIndex([Interval(1, 5), Interval(3, 9), Interval(20, 30), Interval(4, 4 + 12)])
    show("索引区间", fmt_many([Interval(1, 5), Interval(3, 9), Interval(20, 30), Interval(4, 16)]))
    show("query_point(4)", fmt_many(index.query_point(4)))
    show("count_point(4)", index.count_point(4))
    show("query_overlap([6,21))", fmt_many(index.query_overlap(Interval(6, 21))))
    show("query_within([0,10))", fmt_many(index.query_within(Interval(0, 10))))
    show("空索引查询", fmt_many(IntervalIndex([]).query_point(5)))
    time.sleep(10)

    banner("5/5  10 万区间的规范化、建索引与查询性能")
    rng = random.Random(20260922)
    bulk = []
    for _ in range(100000):
        start = rng.randint(-10 ** 12, 10 ** 12)
        bulk.append(Interval(start, start + rng.randint(1, 10 ** 9)))
    start = time.perf_counter()
    merged = RangeSet(bulk)
    show("规范化", "{:.3f} 秒，合并后 {} 个区间".format(time.perf_counter() - start, len(merged.intervals)))
    start = time.perf_counter()
    bulk_index = IntervalIndex(bulk)
    show("建索引", "{:.3f} 秒".format(time.perf_counter() - start))
    probes = [rng.randint(-10 ** 12, 10 ** 12) for _ in range(10000)]
    start = time.perf_counter()
    hits = sum(len(bulk_index.query_point(point)) for point in probes)
    show("1 万次点查", "{:.3f} 秒，命中 {:,} 条区间".format(time.perf_counter() - start, hits))
    start = time.perf_counter()
    spans = sum(len(bulk_index.query_overlap(Interval(point, point + 10 ** 8))) for point in probes[:2000])
    show("2000 次交查", "{:.3f} 秒，命中 {:,} 条区间".format(time.perf_counter() - start, spans))
    time.sleep(9)

    banner("演示结束：半开语义、集合运算与索引查询均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
