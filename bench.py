"""pathglob 性能基准。

场景：
1. 200 条规则构建 Matcher 的耗时；
2. 10 万条路径（约三成命中）批量判定的耗时；
3. 同上的峰值内存（tracemalloc 单独一轮测量，不进计时窗口）；
4. 单条 `**/node_modules/**` 在 10 万条路径上匹配的耗时。

运行：python3 bench.py
"""

import random
import time
import tracemalloc

from pathglob import Matcher, compile_pattern

RULE_COUNT = 200
PATH_COUNT = 100_000


def make_rules():
    """200 条规则：字面量目录/文件 + 通配符 + 取反，模拟真实忽略文件。"""
    rules = []
    for i in range(100):
        rules.append(f"vendor/pkg{i}/")            # 非锚定字面量目录
    for i in range(60):
        rules.append(f"cache/dir{i}/file{i}.tmp")  # 锚定字面量文件
    for i in range(30):
        rules.append(f"*.{i}.bak")                 # 通配符后缀
    rules += [
        "node_modules/",
        "build/",
        "*.o",
        "*.log",
        "docs/**",
        "!docs/keep.md",
        "src/**/test_*.py",
        "**/*.min.js",
        "__pycache__/",
        "!src/keep.o",
    ]
    assert len(rules) == RULE_COUNT
    return rules


def make_paths(seed=42):
    """10 万条路径，约三成会被规则命中。"""
    rng = random.Random(seed)
    paths = []
    for i in range(PATH_COUNT):
        r = rng.random()
        if r < 0.12:
            paths.append(f"node_modules/pkg{rng.randrange(50)}/index.js")
        elif r < 0.20:
            paths.append(f"build/out{rng.randrange(500)}.o")
        elif r < 0.26:
            paths.append(f"docs/guide/{rng.randrange(100)}/page.md")
        elif r < 0.30:
            paths.append(f"src/mod{rng.randrange(80)}/test_case{rng.randrange(50)}.py")
        else:
            depth = rng.randrange(1, 5)
            parts = [f"dir{rng.randrange(1000)}" for _ in range(depth)]
            parts.append(f"file{rng.randrange(10000)}.py")
            paths.append("/".join(parts))
    return paths


def main():
    rules = make_rules()
    paths = make_paths()

    # 1. 构建耗时
    t0 = time.perf_counter()
    matcher = Matcher(rules)
    build_s = time.perf_counter() - t0

    # 2. 批量判定耗时（计时窗口内不开 tracemalloc）
    t0 = time.perf_counter()
    hits = sum(matcher.ignores(p) for p in paths)
    match_s = time.perf_counter() - t0

    # 3. 峰值内存：tracemalloc 单独跑一轮（含路径列表构建），不计时
    tracemalloc.start()
    mem_paths = make_paths()
    matcher2 = Matcher(rules)
    sum(matcher2.ignores(p) for p in mem_paths)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del mem_paths, matcher2

    # 4. 单条 **/node_modules/** 在 10 万路径上的耗时
    single = compile_pattern("**/node_modules/**")
    t0 = time.perf_counter()
    single_hits = sum(single.matches(p) for p in paths)
    single_s = time.perf_counter() - t0

    print(f"规则数 / 路径数            : {RULE_COUNT} / {PATH_COUNT}")
    print(f"构建 Matcher 耗时          : {build_s * 1000:.2f} ms")
    print(f"批量判定耗时               : {match_s:.3f} s"
          f"（{PATH_COUNT / match_s:,.0f} 路径/秒）")
    print(f"批量判定命中数             : {hits}（{hits / PATH_COUNT:.1%}）")
    print(f"峰值内存（含路径列表）     : {peak / 1024 / 1024:.2f} MiB"
          "（tracemalloc 单独一轮，不计时）")
    print(f"单条 **/node_modules/**    : {single_s:.3f} s，命中 {single_hits}")


if __name__ == "__main__":
    main()
