# -*- coding: utf-8 -*-
"""90 秒效果演示：只调用交付物的公开接口，A / B 两轮都能直接跑。

由 tools/record-demo.ps1 调用：python -X utf8 demo.py
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
    print("  {0:<12}{1}".format(label, value), flush=True)


def describe(item):
    data = getattr(item, "__dict__", None)
    if data:
        return "、".join("{0}={1!r}".format(k, v) for k, v in data.items())
    return repr(item)


def merged_text(result):
    for name in ("text", "merged", "result"):
        value = getattr(result, name, None)
        if value is not None:
            return value
    return str(result)


def main():
    banner("文本差异与三方合并引擎 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_textdiff", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from textdiff import apply, diff, merge, unified  # noqa: E402

    banner("2/5  行级差异 diff(a, b)")
    text_a = "alpha\nbeta\ngamma\ndelta\n"
    text_b = "alpha\nBETA\ngamma\nepsilon\n"
    show("a", repr(text_a))
    show("b", repr(text_b))
    print("", flush=True)
    for item in diff(text_a, text_b):
        print("    " + describe(item), flush=True)
        time.sleep(1.2)
    time.sleep(5)

    banner("3/5  unified diff 输出")
    patch = unified(text_a, text_b)
    for line in patch.rstrip("\n").splitlines():
        print("  " + line, flush=True)
    time.sleep(9)

    banner("4/5  补丁往返 apply(a, unified(a, b)) == b")
    show("往返一致", apply(text_a, patch) == text_b)
    time.sleep(7)

    banner("5/5  三方合并：只改一侧自动采用")
    base = "1\n2\n3\n4\n5\n"
    ours = "1\n2\n3\n4\n5\nLOCAL\n"
    theirs = "1\n2\n3\n4\n5\nREMOTE\n"
    result = merge(base, ours, theirs)
    for line in str(merged_text(result)).rstrip("\n").splitlines():
        print("  " + line, flush=True)
    conflicts = getattr(result, "conflicts", None)
    if conflicts is not None:
        show("冲突块", len(conflicts))
    time.sleep(8)

    banner("5/5  三方合并：同一处双侧修改 → 冲突标记")
    base2 = "配置A\n配置B\n配置C\n"
    ours2 = "配置A\n本地改B\n配置C\n"
    theirs2 = "配置A\n远端改B\n配置C\n"
    result2 = merge(base2, ours2, theirs2)
    for line in str(merged_text(result2)).rstrip("\n").splitlines():
        print("  " + line, flush=True)
    conflicts2 = getattr(result2, "conflicts", None)
    if conflicts2 is not None:
        show("冲突块", len(conflicts2))
    time.sleep(8)

    banner("性能：10 万行近似文本（bench.py）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "bench.py"],
        capture_output=True, text=True,
    )
    bench = (proc.stdout or "") + (proc.stderr or "")
    for line in [l for l in bench.splitlines() if l.strip()][-8:]:
        print("  " + line, flush=True)
    time.sleep(9)

    banner("演示结束：标准库实现、自研 Myers、测试与基准均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
