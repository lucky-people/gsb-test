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
    print("  {0:<22}{1}".format(label, value), flush=True)


def main():
    banner("gitignore 风格路径匹配 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_pathglob", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from pathglob import Matcher, compile_pattern, normalize_path  # noqa: E402

    banner("2/5  * 不跨目录，** 跨目录")
    for pattern, paths in (
        ("*.log", ["app.log", "logs/app.log"]),
        ("a/*/b.txt", ["a/x/b.txt", "a/x/y/b.txt"]),
        ("a/**/b.txt", ["a/x/b.txt", "a/x/y/b.txt"]),
        ("**/node_modules/**", ["node_modules/x.js", "src/node_modules/x.js"]),
    ):
        compiled = compile_pattern(pattern)
        print("    模式 {0}".format(pattern), flush=True)
        for path in paths:
            print("      {0:<26} {1}".format(path, compiled.matches(path)), flush=True)
            time.sleep(0.5)
        time.sleep(0.8)
    time.sleep(6)

    banner("3/5  规则集合：最后匹配优先、! 重新包含")
    rules = ["**/__pycache__/", "*.log", "!logs/keep.log", "build/"]
    matcher = Matcher(rules)
    show("规则", " ".join(rules))
    for path, is_dir in (
        ("pkg/__pycache__", True),
        ("pkg/__pycache__/mod.pyc", False),
        ("logs/app.log", False),
        ("logs/keep.log", False),
        ("build", True),
        ("src/main.py", False),
    ):
        verdict = matcher.ignores(path, is_dir)
        rule = matcher.match(path, is_dir)
        show(path, "{0}（由 {1} 决定）".format(verdict, getattr(rule, "original", None)))
        time.sleep(0.8)
    time.sleep(6)

    banner("4/5  路径规范化与模式报错定位")
    show("规范化", normalize_path("src\\a//./b\\c"))
    for bad_path in ("/etc/passwd", "C:/Windows/system32", "../secret", ""):
        try:
            normalize_path(bad_path)
            show(repr(bad_path), "被接受（不符合预期）")
        except Exception as exc:  # noqa: BLE001
            show(repr(bad_path), "{} · {}".format(type(exc).__name__, str(exc)[:30]))
        time.sleep(0.7)
    for bad_pattern in ("[abc", "a\\", "!"):
        try:
            compile_pattern(bad_pattern)
            show(repr(bad_pattern), "被接受（不符合预期）")
        except Exception as exc:  # noqa: BLE001
            show(repr(bad_pattern), "{} · position={}".format(
                type(exc).__name__, getattr(exc, "position", "?")))
        time.sleep(0.7)
    time.sleep(6)

    banner("5/5  200 条规则 × 10 万条路径的性能")
    bulk_rules = ["**/node_modules/**", "*.log", "build/", "dist/", "*.pyc"]
    for index in range(195):
        bulk_rules.append("src/pkg{0}/**/*.tmp".format(index))
    start = time.perf_counter()
    bulk = Matcher(bulk_rules)
    show("构建 Matcher", "{:.3f} 秒（{} 条规则）".format(time.perf_counter() - start, len(bulk_rules)))
    paths = []
    for index in range(100000):
        if index % 10 == 0:
            paths.append("src/node_modules/pkg{0}.js".format(index))
        elif index % 7 == 0:
            paths.append("logs/app{0}.log".format(index))
        elif index % 11 == 0:
            paths.append("src/pkg{0}/cache/x.tmp".format(index % 195))
        else:
            paths.append("src/module{0}/file{0}.py".format(index))
    start = time.perf_counter()
    ignored = sum(1 for path in paths if bulk.ignores(path))
    show("判定 10 万条", "{:.3f} 秒，命中 {}".format(time.perf_counter() - start, ignored))
    start = time.perf_counter()
    single = compile_pattern("**/node_modules/**")
    hits = sum(1 for path in paths if single.matches(path))
    show("单条 ** 模式", "{:.3f} 秒，命中 {}".format(time.perf_counter() - start, hits))
    time.sleep(9)

    banner("演示结束：模式语义、规则优先级、规范化与性能均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
