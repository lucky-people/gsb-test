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


def window_line(window):
    def value(name, default="-"):
        item = getattr(window, name, default)
        if isinstance(item, float):
            return "{0:.3f}".format(item)
        return item

    return "{0} [{1},{2}) count={3} sum={4} min={5} max={6} avg={7}".format(
        value("key"), value("start"), value("end"), value("count"),
        value("sum"), value("min"), value("max"), value("avg"),
    )


def main():
    banner("乱序事件流的窗口聚合 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_eventwin", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from eventwin import Event, WindowSpec, aggregate, assign_windows  # noqa: E402

    banner("2/5  滚动窗口：半开归属与去重")
    events = [
        Event(0, 1.0, "sensor-a", "e1"),
        Event(1000, 2.0, "sensor-a", "e2"),
        Event(2000, 3.0, "sensor-a", "e3"),
        Event(2000, 9.9, "sensor-a", "e3"),
        Event(5000, 5.0, "sensor-a", "e5"),
    ]
    spec = WindowSpec(kind="tumbling", size=2000)
    result = aggregate(events, spec)
    for window in result.windows:
        print("    " + window_line(window), flush=True)
        time.sleep(1.2)
    show("去重数量", result.duplicates_dropped)
    show("处理条数", result.processed_count)
    time.sleep(7)

    banner("3/5  滑动窗口多归属与 assign_windows")
    sliding = WindowSpec(kind="sliding", size=4000, slide=2000)
    result = aggregate([Event(2500, 1.0, "s"), Event(4500, 2.0, "s")], sliding)
    for window in result.windows:
        print("    " + window_line(window), flush=True)
        time.sleep(1.2)
    for moment in (1999, 2000, 4000):
        spans = assign_windows(moment, sliding)
        show("ts={}".format(moment), "、".join("[{0},{1})".format(a, b) for a, b in spans) or "(无)")
        time.sleep(1.5)
    time.sleep(5)

    banner("4/5  会话窗口、乱序迟到与水位线")
    session = WindowSpec(kind="session", gap=3000, allowed_lateness=1000, on_late="drop", dedup="first")
    out_of_order = [
        Event(0, 1.0, "user-1"),
        Event(1000, 2.0, "user-1"),
        Event(5000, 3.0, "user-1"),
        Event(2000, 99.0, "user-1"),
        Event(6000, 4.0, "user-1", "dup"),
        Event(6000, 4.0, "user-1", "dup"),
    ]
    result = aggregate(out_of_order, session)
    for window in result.windows:
        print("    " + window_line(window), flush=True)
        time.sleep(1.2)
    show("迟到丢弃", len(result.late_dropped))
    show("去重数量", result.duplicates_dropped)
    show("处理条数", result.processed_count)
    time.sleep(8)

    banner("5/5  100 万事件性能（滑动窗口与窗口分配）")
    rng = random.Random(20260922)
    keys = ["k1", "k2", "k3", "k4", "k5"]
    bulk = []
    stamp = 0
    for index in range(200000):
        stamp += rng.randint(1, 60)
        bulk.append(Event(stamp, float(rng.randint(1, 100)), keys[index % len(keys)]))
    wide = WindowSpec(kind="sliding", size=60000, slide=10000)
    start = time.perf_counter()
    bulk_result = aggregate(bulk, wide)
    show("20 万事件", "{} 个窗口 {:.3f} 秒".format(len(bulk_result.windows), time.perf_counter() - start))
    start = time.perf_counter()
    for _ in range(20000):
        assign_windows(rng.randint(0, stamp), wide)
    show("2 万次分配", "{:.3f} 秒".format(time.perf_counter() - start))
    time.sleep(8)

    banner("演示结束：窗口划分、去重、迟到判定与聚合均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
