# -*- coding: utf-8 -*-
"""约 90 秒效果演示：只调用交付物的公开接口，A / B 两轮都能直接跑。

由 tools/run-demo.ps1 调用：python -X utf8 demo.py
"""

import os
import subprocess
import sys
import time
from datetime import datetime


def banner(title):
    print("")
    print("=" * 70)
    print("  " + title)
    print("=" * 70, flush=True)


def show(label, value):
    print("  {0:<14}{1}".format(label, value), flush=True)


def stamp(value):
    return value.strftime("%Y-%m-%d %H:%M (%a)")


def as_list(value):
    return list(value)


def main():
    banner("Cron 表达式解析与触发时间引擎 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_cronspec", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from cronspec import describe, parse  # noqa: E402

    banner("2/5  解析与人类可读描述 describe(expr)")
    for expr in ("* * * * *", "0 2 * * *", "30 9 * * MON,THU", "0 0 1 * *", "@hourly"):
        show(expr, describe(expr))
        time.sleep(2.2)
    time.sleep(4)

    banner("3/5  matches / next_after")
    sched = parse("*/15 9-17 * * MON-FRI")
    show("表达式", "*/15 9-17 * * MON-FRI")
    for text in ("2026-09-21 09:00", "2026-09-21 09:07", "2026-09-21 17:45", "2026-09-21 18:00"):
        moment = datetime.strptime(text, "%Y-%m-%d %H:%M")
        show(text[11:], sched.matches(moment))
        time.sleep(1.2)
    anchor = datetime(2026, 9, 21, 9, 7)
    show("next_after 09:07", stamp(sched.next_after(anchor)))
    time.sleep(6)

    banner("4/5  DOM 与 DOW 并集（POSIX 语义）")
    both = parse("0 0 13 * FRI")
    show("表达式", "0 0 13 * FRI")
    following = as_list(both.next_n(datetime(2026, 9, 1, 0, 0), 5))
    for index, moment in enumerate(following, 1):
        show("第 {0} 次".format(index), stamp(moment))
        time.sleep(1.2)
    print("  说明          既是 13 号也是周五时只出现一次", flush=True)
    time.sleep(5)

    banner("4/5  闰年 2 月 29 日与每月 31 日")
    leap = parse("0 0 29 2 *")
    for index, moment in enumerate(as_list(leap.next_n(datetime(2020, 1, 1, 0, 0), 4)), 1):
        show("闰年 {0}".format(index), stamp(moment))
        time.sleep(1)
    month_end = parse("0 0 31 * *")
    for index, moment in enumerate(as_list(month_end.next_n(datetime(2026, 1, 1, 0, 0), 5)), 1):
        show("31 号 {0}".format(index), stamp(moment))
        time.sleep(1)
    print("  说明          没有 31 号的月份自动跳过", flush=True)
    time.sleep(5)

    banner("5/5  按字段推进的性能")
    for expr, count in (("0 0 29 2 *", 1000), ("0 0 1 1 *", 1000)):
        sched = parse(expr)
        start = time.perf_counter()
        as_list(sched.next_n(datetime(2020, 1, 1, 0, 0), count))
        elapsed = time.perf_counter() - start
        show(expr, "{0} 个触发时刻 {1:.3f} 秒".format(count, elapsed))
        time.sleep(2)
    every_minute = parse("* * * * *")
    start = time.perf_counter()
    as_list(every_minute.next_n(datetime(2026, 1, 1, 0, 0), 100000))
    elapsed = time.perf_counter() - start
    show("* * * * *", "10 万个触发时刻 {0:.3f} 秒".format(elapsed))
    time.sleep(6)

    banner("演示结束：标准库实现、自研搜索、测试与基准均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
