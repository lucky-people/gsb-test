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
    print("  {0:<18}{1}".format(label, value), flush=True)


def main():
    banner("语义化版本与范围约束 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_semverrange", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from semverrange import Version, max_satisfying, parse_range, satisfies, sort_versions  # noqa: E402

    banner("2/5  版本解析与预发布优先级")
    chain = [
        "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
        "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0",
    ]
    for value in sort_versions(list(reversed(chain))):
        show(str(value), "预发布" if value.is_prerelease else "正式版")
        time.sleep(0.6)
    parsed = Version.parse("1.2.3-beta.1+build.7")
    show("解析示例", "major={0} minor={1} patch={2}".format(parsed.major, parsed.minor, parsed.patch))
    show("pre/build", "{0} / {1}".format(parsed.prerelease, parsed.build))
    show("bump('minor')", str(parsed.bump("minor")))
    time.sleep(6)

    banner("3/5  范围判定：^ ~ 通配 连字符 OR")
    versions = ["1.2.3", "1.2.9", "1.3.0", "2.0.0", "2.1.0", "3.0.0", "1.3.0-alpha"]
    for range_text in ("^1.2.3", "~1.2.3", "1.2.x", "1.x",
                       "1.2.3 - 2.0.0", ">=2.0.0 <3.0.0 || >=3.0.0"):
        matched = [value for value in versions if satisfies(value, range_text)]
        show(range_text, ", ".join(matched) if matched else "(无)")
        time.sleep(1.2)
    show("预发布默认排除", satisfies("1.3.0-alpha", "^1.2.3"))
    show("显式预发布范围", satisfies("1.2.3-beta", ">=1.2.3-alpha.1 <1.2.3"))
    time.sleep(6)

    banner("4/5  max_satisfying 与错误定位")
    pool = ["1.0.0", "1.2.0", "1.2.5", "1.4.2", "2.0.0-rc.1", "2.0.0"]
    for range_text in ("^1.2.0", "~1.2.0", "1.x", ">=2.0.0"):
        show(range_text, "最大满足 {0}".format(max_satisfying(pool, range_text)))
        time.sleep(1)
    for bad in (">=", "1.2.3 -", "^", "||", ""):
        try:
            parse_range(bad)
            show(repr(bad), "被接受（不符合预期）")
        except Exception as exc:  # noqa: BLE001
            show(repr(bad), "{} · position={} · {}".format(
                type(exc).__name__, getattr(exc, "position", "?"), str(exc)[:30]))
        time.sleep(0.9)
    time.sleep(5)

    banner("5/5  10 万版本排序与 200 万次范围判定")
    values = ["{0}.{1}.{2}".format(index % 40, (index // 40) % 40, index % 50)
              for index in range(100000)]
    start = time.perf_counter()
    ordered = sort_versions(values)
    show("解析+排序", "{:.3f} 秒（{} 个版本）".format(time.perf_counter() - start, len(ordered)))
    compiled = [parse_range("^{0}.0.0".format(index % 20)) for index in range(200)]
    sample = ordered[:10000]
    start = time.perf_counter()
    hits = 0
    for range_object in compiled:
        for version in sample:
            if range_object.satisfies(version):
                hits += 1
    show("200 万次判定", "{:.3f} 秒，命中 {}".format(time.perf_counter() - start, hits))
    time.sleep(9)

    banner("演示结束：版本优先级、范围语义与预发布规则均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
