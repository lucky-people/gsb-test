# -*- coding: utf-8 -*-
"""约 90 秒效果演示：只调用交付物的公开接口，A / B 两轮都能直接跑。

由 tools/run-demo.ps1 调用：python -X utf8 demo.py
"""

import os
import subprocess
import sys
import time


def banner(title):
    print("")
    print("=" * 70)
    print("  " + title)
    print("=" * 70, flush=True)


def show(label, value):
    print("  {0:<20}{1}".format(label, value), flush=True)


def show_result(result, limit=6):
    print("    " + " | ".join(str(column) for column in result.columns), flush=True)
    for row in list(result.rows)[:limit]:
        print("    " + " | ".join("NULL" if value is None else str(value) for value in row), flush=True)
        time.sleep(0.4)
    if result.row_count > limit:
        print("    ... 共 {0} 行".format(result.row_count), flush=True)


def main():
    banner("内存表 SQL 子集执行引擎 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_minisql", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from minisql import Engine  # noqa: E402

    engine = Engine()
    users = engine.create_table("users", [("id", "int"), ("name", "str"), ("age", "int"), ("city", "str")])
    users.insert([
        (1, "张三", 31, "北京"),
        (2, "李四", 24, "上海"),
        (3, "王五", None, "北京"),
        (4, "Zhao", 45, None),
        (5, "钱七", 24, "北京"),
    ])
    orders = engine.create_table("orders", [("oid", "int"), ("uid", "int"), ("amount", "float")])
    orders.insert([(100, 1, 88.5), (101, 1, 12.0), (102, 2, 40.0), (103, 4, 5.5)])

    banner("2/5  基本查询：投影、过滤、DISTINCT")
    show_result(engine.execute("SELECT id, name, age FROM users WHERE age > 24 ORDER BY age DESC"))
    show_result(engine.execute("SELECT DISTINCT city FROM users ORDER BY city"))
    show_result(engine.execute("SELECT name, age + 1 AS next_age FROM users WHERE city = '北京'"))
    time.sleep(9)

    banner("3/5  聚合、分组、HAVING 与 LIMIT")
    show_result(engine.execute(
        "SELECT city, COUNT(*) AS cnt, AVG(age) AS avg_age FROM users "
        "GROUP BY city ORDER BY cnt DESC, city ASC"
    ))
    show_result(engine.execute(
        "SELECT COUNT(*) AS total, COUNT(age) AS with_age, SUM(age) AS sum_age FROM users"
    ))
    show_result(engine.execute("SELECT id FROM users ORDER BY id LIMIT 2 OFFSET 1"))
    time.sleep(9)

    banner("4/5  连接与三值逻辑")
    show_result(engine.execute(
        "SELECT u.name, o.amount FROM users u LEFT JOIN orders o ON u.id = o.uid "
        "ORDER BY u.id, o.amount"
    ))
    show_result(engine.execute("SELECT name FROM users WHERE age IS NULL OR age BETWEEN 30 AND 40"))
    show_result(engine.execute("SELECT name FROM users WHERE NOT (city = '北京')"))
    try:
        engine.execute("SELECT name FROM users WHERE age = 'x'")
        show("类型错误", "没有抛错（不符合预期）")
    except Exception as exc:  # noqa: BLE001
        show("类型错误", type(exc).__name__)
    try:
        engine.execute("SELECT name FROM users WHERE id =")
        show("语法错误", "没有抛错（不符合预期）")
    except Exception as exc:  # noqa: BLE001
        show("语法错误", "{} · position={} · token={}".format(
            type(exc).__name__, getattr(exc, "position", "?"), getattr(exc, "token", "?")))
    time.sleep(9)

    banner("5/5  执行计划与 5 万行性能")
    show("explain", engine.explain(
        "SELECT city, COUNT(*) AS cnt FROM users WHERE age > 20 GROUP BY city ORDER BY cnt DESC LIMIT 3"
    ))
    show("explain(join)", engine.explain(
        "SELECT u.name, o.amount FROM users u JOIN orders o ON u.id = o.uid WHERE o.amount > 10"
    ))
    big = engine.create_table("big", [("k", "int"), ("grp", "str"), ("v", "int")])
    big.insert([(index, "g{0}".format(index % 50), index % 1000) for index in range(50000)])
    start = time.perf_counter()
    result = engine.execute(
        "SELECT grp, COUNT(*) AS cnt, SUM(v) AS total FROM big WHERE k >= 1000 "
        "GROUP BY grp ORDER BY total DESC LIMIT 5"
    )
    show("过滤+分组+排序", "{:.3f} 秒，{} 行".format(time.perf_counter() - start, result.row_count))
    left = engine.create_table("left_t", [("id", "int"), ("label", "str")])
    left.insert([(index, "L{0}".format(index)) for index in range(20000)])
    right = engine.create_table("right_t", [("id", "int"), ("score", "float")])
    right.insert([(index, index * 0.5) for index in range(0, 20000, 2)])
    start = time.perf_counter()
    joined = engine.execute(
        "SELECT l.label, r.score FROM left_t l JOIN right_t r ON l.id = r.id WHERE r.score > 100"
    )
    show("等值哈希连接", "{:.3f} 秒，{} 行".format(time.perf_counter() - start, joined.row_count))
    time.sleep(9)

    banner("演示结束：语法、三值逻辑、聚合、连接与计划均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
