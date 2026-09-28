"""miniregex 性能基准。

分别测量耗时与峰值内存（tracemalloc 不进计时窗口）。
运行：python3 bench.py
"""

import random
import string
import time
import tracemalloc

from miniregex import compile_pattern
from miniregex.errors import MatchLimitError


def make_text_1mb():
    """1 MB 随机文本（字母、数字、空格、短横线），固定种子保证可复现。"""
    rng = random.Random(42)
    alphabet = string.ascii_letters + string.digits + "   ---"
    body = "".join(rng.choice(alphabet) for _ in range(1024 * 1024 - 8))
    return body + "555-1234"  # 末尾埋一处目标，保证扫描整段文本


def bench_compile(repeat=2000):
    patterns = [
        r"\d{3}-\d{4}",
        r"(\w+)@(\w+)\.(com|cn|org)",
        r"^(?:[a-z0-9]+[-_]?)+$",
        r"(a|b)*abb",
    ]
    # 预热
    for p in patterns:
        compile_pattern(p)
    start = time.perf_counter()
    for _ in range(repeat):
        for p in patterns:
            compile_pattern(p)
    elapsed = time.perf_counter() - start
    total = repeat * len(patterns)
    print("编译：%d 个典型模式共 %.3f s，平均 %.1f us/个"
          % (total, elapsed, elapsed / total * 1e6))


def bench_search_1mb(text):
    regex = compile_pattern(r"\d{3}-\d{4}")
    regex.search(text)  # 预热
    start = time.perf_counter()
    m = regex.search(text)
    elapsed = time.perf_counter() - start
    print("search(r\"\\d{3}-\\d{4}\") 1 MB 文本：耗时 %.3f s（结果：%s）"
          % (elapsed, m.group(0) if m else "未匹配"))
    return regex, text


def bench_finditer():
    # 构造含 1 万处匹配的文本："abc123 " x 10000
    text = "abc123 " * 10000
    regex = compile_pattern(r"\d+")
    start = time.perf_counter()
    count = sum(1 for _ in regex.finditer(text))
    elapsed = time.perf_counter() - start
    print("finditer(r\"\\d+\") %d 处匹配（文本 %d 字符）：总耗时 %.3f s"
          % (count, len(text), elapsed))


def bench_redos():
    regex = compile_pattern("(a+)+b")
    text = "a" * 30 + "c"
    start = time.perf_counter()
    try:
        regex.match(text)
        result = "意外匹配成功"
    except MatchLimitError as e:
        result = "抛出 MatchLimitError（步数上限 %d）" % e.limit
    elapsed = time.perf_counter() - start
    print("ReDoS (a+)+b 于 'a'*30+'c'：%.3f s 后%s" % (elapsed, result))


def bench_memory(regex, text):
    # 单独测量峰值内存，tracemalloc 不进计时窗口
    tracemalloc.start()
    regex.search(text)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print("search 1 MB 峰值内存：%.1f KB（tracemalloc 单独测量）"
          % (peak / 1024))


def main():
    print("Python 性能基准（本机实测）")
    print("-" * 50)
    bench_compile()
    text = make_text_1mb()
    regex, text = bench_search_1mb(text)
    bench_finditer()
    bench_redos()
    bench_memory(regex, text)


if __name__ == "__main__":
    main()
