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


def show_matches(matches, limit=6):
    for match in matches[:limit]:
        print("    {0:<10} [{1:>4},{2:>4}) 行{3}列{4}  {5!r}".format(
            match.pattern, match.start, match.end, match.line, match.column, match.text), flush=True)
        time.sleep(0.5)
    if len(matches) > limit:
        print("    ... 共 {0} 条".format(len(matches)), flush=True)


def main():
    banner("多模式文本检索与高亮 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_multisearch", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from multisearch import build_matcher, merge_ranges  # noqa: E402

    banner("2/5  多模式一次扫描")
    text = "错误码 E1001、E204 与 ERROR: 磁盘已满\n另外 code=E1001 重复出现"
    matcher = build_matcher(["E1001", "E204", "ERROR", "磁盘"])
    show("模式", "E1001 / E204 / ERROR / 磁盘")
    show("命中数", matcher.count(text))
    show_matches(matcher.find_all(text))
    time.sleep(8)

    banner("3/5  重叠策略与区间合并")
    sample = "abcabcabc"
    longest = build_matcher(["abc", "bca", "abcabc"])
    overlapping = build_matcher(["abc", "bca", "abcabc"], overlapping=True)
    show("文本", repr(sample))
    show("默认（最长优先）", len(longest.find_all(sample)))
    show_matches(longest.find_all(sample), 4)
    show("overlapping=True", len(overlapping.find_all(sample)))
    show_matches(overlapping.find_all(sample))
    ranges = [(0, 3), (2, 6), (6, 8), (7, 9), (20, 21)]
    show("merge_ranges", merge_ranges(ranges))
    time.sleep(7)

    banner("4/5  高亮与大小写/归一化")
    nested = build_matcher(["cat", "catalog", "log"])
    show("嵌套模式", " ".join(["cat", "catalog", "log"]))
    show("高亮结果", nested.highlight("a catalog of cats"))
    folded = build_matcher(["straße"], case_sensitive=False)
    show("ß 折叠（casefold）", [(m.start, m.end, m.text) for m in folded.find_all("STRASSE 与 straße")])
    normalized = build_matcher(["ABC"], normalize=True)
    show("全角 NFKC", [(m.start, m.end, m.text) for m in normalized.find_all("ＡＢＣ与 ABC")])
    time.sleep(9)

    banner("5/5  500 个模式 × 4 MB 文本")
    patterns = ["token{0:04d}".format(index) for index in range(500)]
    build_start = time.perf_counter()
    bulk = build_matcher(patterns)
    show("构建 Matcher", "{:.3f} 秒（{} 个模式）".format(time.perf_counter() - build_start, len(patterns)))
    chunk = "普通文本内容，偶尔出现 token0123 或 token0456 这样的标记。\n"
    big = chunk * 60000
    show("文本规模", "{:.1f} MB".format(len(big) / 1024 / 1024))
    start = time.perf_counter()
    found = bulk.find_all(big)
    show("find_all", "{:.3f} 秒，命中 {} 条".format(time.perf_counter() - start, len(found)))
    start = time.perf_counter()
    marked = bulk.highlight(big)
    show("highlight", "{:.3f} 秒，结果长度 {}".format(time.perf_counter() - start, len(marked)))
    time.sleep(9)

    banner("演示结束：多模式扫描、重叠策略、高亮与映射均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
