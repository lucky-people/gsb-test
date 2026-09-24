"""性能基准：10 万行近似文本上的 diff / unified / apply / merge。

直接运行：python bench.py
可选参数：
    --repeat N        每项计时重复次数（默认 5）
    --out FILE        把结构化结果写入 JSON
    --baseline FILE   与既有 JSON 基线对比，任一项耗时慢 20% 以上则退出码为 1

测量口径（与旧版 bench.py 不同，数字不可直接对比）：
    * 计时轮：确认 tracemalloc 未开启（开着会直接报错退出），每项先预热 1 次，
      再重复 N 次取中位数 / 最小 / 最大；每次重复都真实调用目标函数，不缓存结果。
    * 内存轮：单独一轮开启 tracemalloc 统计 Python 层分配峰值。
    开启内存追踪会让同段代码慢数倍，因此耗时与内存必须分开测。

只用标准库；Windows / Linux / macOS 均可直接运行。
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from datetime import datetime, timezone

from textdiff import apply, diff, merge, unified

N_LINES = 100_000
N_CHANGES = 40  # 几十处差异

# 回归判定阈值：任一项中位耗时比基线慢超过该比例即判失败
REGRESSION_TOLERANCE = 0.20

CASE_ORDER = ("diff", "unified", "apply", "merge")


def build_texts():
    """构造两份 10 万行、只差几十处的近似文本。

    差异包括修改、插入、删除三种；三方合并的两侧改动互不相邻。
    """
    base = [f"line-{i:06d}\n" for i in range(N_LINES)]

    changed = base.copy()
    for k in range(N_CHANGES // 3):
        idx = 1000 + k * 1500
        changed[idx] = f"modified-{idx}\n"
    for k in range(N_CHANGES // 3):
        idx = 2000 + k * 1700
        changed.insert(idx, f"inserted-{idx}\n")
    for k in range(N_CHANGES - 2 * (N_CHANGES // 3)):
        idx = 3000 + k * 1900
        if idx < len(changed):
            changed.pop(idx)

    # ours 改前半段、theirs 改后半段，保证是干净合并
    mid = N_LINES // 2
    ours = base.copy()
    for idx in range(500, 10_000, 300):
        ours[idx] = f"ours-{idx}\n"
    theirs = base.copy()
    for idx in range(mid + 500, mid + 10_000, 300):
        theirs[idx] = f"theirs-{idx}\n"

    return ("".join(base), "".join(changed), "".join(ours), "".join(theirs))


def build_cases():
    """构造四个基准用例；返回 (用例字典, 自检数据)。"""
    base, changed, ours, theirs = build_texts()
    patch = unified(base, changed)
    cases = {
        "diff": lambda: diff(base, changed),
        "unified": lambda: unified(base, changed),
        "apply": lambda: apply(base, patch),
        "merge": lambda: merge(base, ours, theirs),
    }
    selfcheck = {"base": base, "changed": changed, "patch": patch,
                 "ours": ours, "theirs": theirs}
    return cases, selfcheck


def run_selfcheck(cases, selfcheck):
    """正确性自检：apply 往返一致、merge 无冲突。失败直接抛 AssertionError。"""
    edits = cases["diff"]()
    restored = apply(selfcheck["base"], selfcheck["patch"])
    result = cases["merge"]()
    assert restored == selfcheck["changed"], "apply 往返不一致"
    assert not result.has_conflicts, "基准合并应当无冲突"
    return len(edits), len(result.text.splitlines())


def cpu_model():
    """尽力获取 CPU 型号；跨平台、只用标准库，拿不到就返回“未知”。"""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass
    elif sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, check=True)
            return out.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    elif sys.platform.startswith("win"):
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except (OSError, ImportError):
            pass
    return platform.processor() or "未知"


def environment_info():
    """收集测量环境信息。"""
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "cpu": cpu_model(),
        "logical_cpus": os.cpu_count(),
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"),
    }


def measure_time(name, func, repeat):
    """计时轮：先预热 1 次，再重复 repeat 次，返回各次耗时列表（秒）。

    计时期间严禁开启 tracemalloc；每次重复都真实调用 func，不复用上次结果。
    """
    if tracemalloc.is_tracing():
        raise SystemExit(
            f"错误：计时轮检测到 tracemalloc 正在追踪（用例 {name}）。\n"
            "内存追踪会让同段代码慢数倍，计时必须在未开启追踪的状态下进行。")
    func()  # 预热，排除首次导入 / 缓存等一次性开销
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        func()
        samples.append(time.perf_counter() - start)
    return samples


def measure_memory(func):
    """内存轮：单独开启 tracemalloc，返回峰值（字节）。"""
    tracemalloc.start()
    try:
        func()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak


def print_environment(env):
    print("测量环境：")
    print(f"  Python    {env['implementation']} {env['python']}")
    print(f"  平台      {env['platform']}")
    print(f"  CPU       {env['cpu']}（{env['logical_cpus']} 逻辑核）")
    print(f"  时间戳    {env['timestamp']}")
    print("测量口径：耗时在未开启内存追踪的状态下测量（预热 1 次后取重复"
          "运行的中位数）；峰值内存为单独一轮开启 tracemalloc 的统计值。\n")


def print_results(results):
    header = f"{'阶段':<10}{'中位耗时':>10}{'最小':>10}{'最大':>10}{'峰值内存':>12}"
    print(header)
    print("-" * len(header.expandtabs()))
    for name in CASE_ORDER:
        r = results[name]
        print(f"{name:<10}{r['median_s']:>9.3f}s{r['min_s']:>9.3f}s"
              f"{r['max_s']:>9.3f}s{r['peak_mib']:>10.1f} MiB")


def compare_baseline(results, baseline_path):
    """与基线 JSON 对比；任一项中位耗时慢 20% 以上返回失败项列表。"""
    with open(baseline_path, encoding="utf-8") as f:
        baseline = json.load(f)
    base_results = baseline.get("results", {})
    failures = []
    print(f"\n与基线 {baseline_path} 对比（阈值：慢 {REGRESSION_TOLERANCE:.0%} 判回归）：")
    for name in CASE_ORDER:
        if name not in base_results:
            print(f"  {name:<10} 基线中无此项，跳过")
            continue
        cur = results[name]["median_s"]
        ref = base_results[name]["median_s"]
        ratio = cur / ref if ref > 0 else float("inf")
        mark = "OK" if ratio <= 1 + REGRESSION_TOLERANCE else "回归"
        print(f"  {name:<10} 基线 {ref:.3f}s → 本次 {cur:.3f}s"
              f"（{ratio:.2f}x）{mark}")
        if ratio > 1 + REGRESSION_TOLERANCE:
            failures.append(name)
    return failures


def main():
    parser = argparse.ArgumentParser(
        description="textdiff 性能基准（计时与内存分离测量）")
    parser.add_argument("--repeat", type=int, default=5,
                        help="每项计时重复次数（默认 5）")
    parser.add_argument("--out", metavar="FILE",
                        help="把结构化结果写入 JSON 文件")
    parser.add_argument("--baseline", metavar="FILE",
                        help="与既有 JSON 基线对比，回归则退出码为 1")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat 必须 >= 1")

    env = environment_info()
    print_environment(env)

    cases, selfcheck = build_cases()
    print(f"输入规模：{N_LINES} 行，差异约 {N_CHANGES} 处；"
          f"每项重复 {args.repeat} 次\n")

    n_edits, n_merged = run_selfcheck(cases, selfcheck)
    print(f"自检通过：编辑段数 {n_edits}，合并结果 {n_merged} 行（无冲突）\n")

    # 先计时（tracemalloc 全程关闭），再单独一轮测内存
    results = {}
    for name in CASE_ORDER:
        samples = measure_time(name, cases[name], args.repeat)
        results[name] = {
            "median_s": statistics.median(samples),
            "min_s": min(samples),
            "max_s": max(samples),
            "samples_s": samples,
        }
    for name in CASE_ORDER:
        results[name]["peak_mib"] = measure_memory(cases[name]) / 1024 / 1024

    print_results(results)

    payload = {
        "tool": "bench.py",
        "methodology": "计时未开启内存追踪（预热 1 次取中位数）；"
                       "峰值内存为单独一轮 tracemalloc 统计",
        "environment": env,
        "config": {"lines": N_LINES, "changes": N_CHANGES,
                   "repeat": args.repeat},
        "results": results,
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n结果已写入 {args.out}")

    if args.baseline:
        failures = compare_baseline(results, args.baseline)
        if failures:
            print(f"\n回归项：{', '.join(failures)}"
                  f"（中位耗时比基线慢超过 {REGRESSION_TOLERANCE:.0%}）")
            return 1
        print("\n所有项均在基线容差范围内")

    return 0


if __name__ == "__main__":
    sys.exit(main())
