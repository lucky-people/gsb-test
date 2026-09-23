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


def build_sample():
    from digraph import DiGraph

    graph = DiGraph()
    for edge in (("build", "test"), ("test", "package"), ("package", "deploy"),
                 ("lint", "test"), ("docs", "package")):
        graph.add_edge(*edge)
    return graph


def main():
    banner("有向图数据结构与经典算法 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_digraph", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from digraph import DiGraph  # noqa: E402

    banner("2/5  构建与拓扑排序（确定性顺序）")
    graph = build_sample()
    show("节点", ", ".join(graph.nodes))
    show("边数", graph.edge_count)
    show("拓扑序", " -> ".join(graph.topological_sort()))
    show("自动创建", ", ".join(sorted(graph.auto_created)) or "(无)")
    cyclic = DiGraph()
    cyclic.add_edge("a", "b")
    cyclic.add_edge("b", "c")
    cyclic.add_edge("c", "a")
    try:
        cyclic.topological_sort()
        show("有环图拓扑排序", "没有抛错（不符合预期）")
    except Exception as exc:  # noqa: BLE001
        show("有环图拓扑排序", "{} · cycle={}".format(type(exc).__name__, getattr(exc, "cycle", None)))
    time.sleep(8)

    banner("3/5  环检测与强连通分量")
    show("find_cycle（无环图）", graph.find_cycle())
    show("find_cycle（有环图）", cyclic.find_cycle())
    components = DiGraph()
    for edge in (("a", "b"), ("b", "a"), ("b", "c"), ("c", "d"), ("d", "c"), ("e", "e")):
        components.add_edge(*edge)
    for index, component in enumerate(components.strongly_connected_components(), 1):
        show("SCC {}".format(index), ", ".join(component))
        time.sleep(1)
    del components
    time.sleep(6)

    banner("4/5  最短路径与单源距离")
    weighted = DiGraph()
    for src, dst, weight in (("s", "a", 1), ("s", "b", 1), ("a", "t", 3),
                             ("b", "t", 3), ("a", "b", 1), ("b", "c", 1), ("c", "t", 3)):
        weighted.add_edge(src, dst, weight)
    path, total = weighted.shortest_path("s", "t")
    show("最短路径", "{}（总权重 {}）".format(" -> ".join(path), total))
    show("等权时的确定性", "同权重路径取字典序最小")
    show("不可达", weighted.shortest_path("t", "s"))
    distances = weighted.distances_from("s")
    show("单源距离", ", ".join("{}={}".format(k, v) for k, v in sorted(distances.items())))
    try:
        bad = DiGraph()
        bad.add_edge("x", "y", -1)
        show("负权重", "没有抛错（不符合预期）")
    except Exception as exc:  # noqa: BLE001
        show("负权重", type(exc).__name__)
    time.sleep(8)

    banner("5/5  10 万节点 / 30 万边的性能")
    big = DiGraph()
    for index in range(100000):
        big.add_node("n{:06d}".format(index))
    for index in range(0, 100000, 3):
        for step in (1, 2, 3):
            if index + step < 100000:
                big.add_edge("n{:06d}".format(index), "n{:06d}".format(index + step), 1)
    show("规模", "{} 节点 / {} 边".format(big.node_count, big.edge_count))
    start = time.perf_counter()
    order = big.topological_sort()
    show("拓扑排序", "{:.3f} 秒，输出 {} 个节点".format(time.perf_counter() - start, len(order)))
    start = time.perf_counter()
    distances = big.distances_from("n000000")
    show("单源距离", "{:.3f} 秒，可达 {} 个节点".format(time.perf_counter() - start, len(distances)))
    start = time.perf_counter()
    chain = DiGraph()
    for index in range(100000):
        chain.add_edge("c{:06d}".format(index), "c{:06d}".format(index + 1))
    components = chain.strongly_connected_components()
    show("10 万节点链 SCC", "{:.3f} 秒，分量数 {}".format(time.perf_counter() - start, len(components)))
    time.sleep(9)

    banner("演示结束：拓扑序、环检测、SCC 与最短路均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
