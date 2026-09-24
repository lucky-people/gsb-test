"""性能基准：10 万行近似文本上的 diff / unified / apply / merge。

直接运行：python bench.py
可选参数：
    --repeat N        每项计时重复次数（默认 5）
    --out FILE        把结构化结果写入 JSON
    --baseline FILE   与既有 JSON 基线对比，任一项中位耗时慢 20% 以上
                      则以非零退出码结束

测量口径（与旧版 bench.py 不同，新旧数字不可直接对比）：
    * 计时轮与内存轮严格分开。计时轮断言 tracemalloc.is_tracing() 为 False，
      真开着就直接报错退出；每项先做 1 次预热（不计入），再真实重复 N 次，
      报告中位数与最小 / 最大值。
    * 内存轮单独开启一次 tracemalloc，统计该轮的 Python 层分配峰值。
    * 计时轮的总步数随 --repeat N 线性增长：每项共 N+1 次真实调用
      （1 次预热 + N 次计时），每次调用都重新执行目标函数，
      且计时结束后校验返回值是“全新对象且内容正确”，杜绝复用上一轮结果。

开启内存追踪会让同段代码慢数倍，因此耗时与内存必须分开测；
两份实现的性能数字也只有在同一口径下才可以比较。

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
N_CHANGES = 40  # 约 40 处差异（修改 / 插入 / 删除混合）
DEFAULT_REPEAT = 5
# 回归判定阈值：任一项中位耗时比基线慢出该比例即判回归
REGRESSION_TOLERANCE = 0.20
CASE_ORDER = ("diff", "unified", "apply", "merge")


def build_texts():
    """构造两份 10 万行、只差约 40 处的近似文本。

    差异包括修改、插入、删除三种；三方合并的两侧改动互不相邻，保证干净合并。
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
    """构造四个基准用例。

    返回 (用例列表, 自检数据)。用例为 (名称, 无参可调用对象, 期望结果) 三元组；
    apply 所需的补丁在这里构造一次（属于计时之外的输入准备，不纳入任何测量）。
    期望结果用于每一轮调用后的正确性校验。
    """
    base, changed, ours, theirs = build_texts()
    patch = unified(base, changed)

    expected_diff = diff(base, changed)
    expected_patch = patch
    expected_restored = changed
    expected_merge = merge(base, ours, theirs)

    cases = [
        ("diff", lambda: diff(base, changed), expected_diff),
        ("unified", lambda: unified(base, changed), expected_patch),
        ("apply", lambda: apply(base, patch), expected_restored),
        ("merge", lambda: merge(base, ours, theirs), expected_merge),
    ]
    selfcheck = {
        "n_edits": len(expected_diff),
        "restored": expected_restored,
        "changed": changed,
        "merged_lines": len(expected_merge.text.splitlines()),
        "has_conflicts": expected_merge.has_conflicts,
    }
    return cases, selfcheck


def run_selfcheck(selfcheck):
    """正确性自检：apply 往返一致、merge 无冲突。失败直接抛 AssertionError。"""
    assert selfcheck["restored"] == selfcheck["changed"], "apply 往返不一致"
    assert not selfcheck["has_conflicts"], "基准合并应当无冲突"


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
    """收集测量环境：Python 版本、平台、CPU、逻辑核数、测量时间戳。"""
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "cpu": cpu_model(),
        "logical_cpus": os.cpu_count(),
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"),
    }


def measure_time(name, func, repeat, expected):
    """计时轮：先预热 1 次（不计入），再真实重复 repeat 次。

    * 进入时断言 tracemalloc 未开启——内存追踪会让同段代码慢数倍，
      开着就直接报错退出，拒绝产出不可比的耗时数字。
    * 每一轮都重新调用 func()，总步数随 repeat 线性增长。
    * 计时结束后校验本轮返回值是全新对象、且与期望结果逐字节相等，
      防止把上一轮的循环结果缓存进答案（校验发生在停表之后，不污染耗时）。
    """
    if tracemalloc.is_tracing():
        raise SystemExit(
            f"错误：计时轮（用例 {name}）检测到 tracemalloc 正在追踪。\n"
            "内存追踪会让同段代码慢数倍，耗时必须在未开启追踪的状态下测量；\n"
            "请停止外层 tracemalloc 后重跑（本脚本只会在内存轮自行短开追踪）。")

    warmed = func()  # 预热：导入、内部缓存等一次性成本不计入统计
    if warmed != expected:
        raise AssertionError(f"预热结果与期望不一致（用例 {name}）")

    previous = warmed
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        result = func()
        samples.append(time.perf_counter() - start)
        if result is previous:
            raise AssertionError(
                f"用例 {name} 返回了上一轮的同一对象，疑似结果被缓存")
        if result != expected:
            raise AssertionError(f"计时轮结果与期望不一致（用例 {name}）")
        previous = result
    return samples


def measure_memory(name, func):
    """内存轮：单独开启 tracemalloc 跑一次，返回 Python 层峰值（字节）。"""
    if tracemalloc.is_tracing():
        raise SystemExit(
            f"错误：内存轮（用例 {name}）开始前 tracemalloc 已处于开启状态，"
            "无法取得干净的峰值基线。")
    tracemalloc.start()
    try:
        result = func()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    if tracemalloc.is_tracing():
        raise SystemExit(f"错误：内存轮（用例 {name}）结束后 tracemalloc 仍未停止。")
    return peak


def print_environment(env):
    print("测量环境：")
    print(f"  Python    {env['implementation']} {env['python']}")
    print(f"  平台      {env['platform']}")
    print(f"  CPU       {env['cpu']}（{env['logical_cpus']} 逻辑核）")
    print(f"  时间戳    {env['timestamp']}")
    print("测量口径：耗时在未开启内存追踪的状态下测量（每项预热 1 次后"
          "重复运行取中位数）；峰值内存在单独一轮开启 tracemalloc 统计，"
          "两轮互不干扰。\n")


def print_results(results, repeat):
    header = f"{'阶段':<10}{'中位耗时':>10}{'最小':>10}{'最大':>10}{'峰值内存':>12}"
    print(header)
    print("-" * len(header))
    for name in CASE_ORDER:
        r = results[name]
        print(f"{name:<10}{r['median_s']:>9.3f}s{r['min_s']:>9.3f}s"
              f"{r['max_s']:>9.3f}s{r['peak_mib']:>10.1f} MiB")
    print(f"\n统计口径：每项预热 1 次、计时 {repeat} 次（共 "
          f"{len(CASE_ORDER) * (repeat + 1)} 次真实调用），"
          f"内存轮每项另行调用 1 次。")


def compare_baseline(results, baseline_path):
    """与基线 JSON 逐项对比；任一项中位耗时慢 20% 以上则返回失败项列表。"""
    try:
        with open(baseline_path, encoding="utf-8") as f:
            baseline = json.load(f)
    except OSError as exc:
        raise SystemExit(f"错误：无法读取基线文件 {baseline_path}：{exc}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"错误：基线文件不是合法 JSON：{exc}")

    base_results = baseline.get("results")
    if not isinstance(base_results, dict):
        raise SystemExit("错误：基线文件缺少 results 结构，无法对比")

    base_env = baseline.get("environment", {})
    if base_env:
        print("基线环境："
              f"{base_env.get('implementation', '?')} "
              f"{base_env.get('python', '?')}，{base_env.get('platform', '?')}，"
              f"{base_env.get('cpu', '?')}")
        if base_env.get("cpu") != environment_info()["cpu"]:
            print("提示：基线与本次测量的 CPU / 平台不同，"
                  "跨硬件对比请结合硬件差异解读。")
    print(f"\n与基线 {baseline_path} 对比"
          f"（阈值：中位耗时慢 {REGRESSION_TOLERANCE:.0%} 判回归）：")

    failures = []
    for name in CASE_ORDER:
        if name not in base_results or "median_s" not in base_results[name]:
            print(f"  {name:<10} 基线中无此项，跳过")
            continue
        current = results[name]["median_s"]
        reference = float(base_results[name]["median_s"])
        ratio = current / reference if reference > 0 else float("inf")
        if ratio > 1 + REGRESSION_TOLERANCE:
            mark = "回归"
            failures.append((name, reference, current, ratio))
        else:
            mark = "OK"
        print(f"  {name:<10} 基线 {reference:7.3f}s → 本次 {current:7.3f}s"
              f"（{ratio:5.2f}x）{mark}")
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="textdiff 性能基准（计时与内存严格分离测量）")
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT,
                        help=f"每项计时重复次数（默认 {DEFAULT_REPEAT}）")
    parser.add_argument("--out", metavar="FILE",
                        help="把结构化结果写入 JSON 文件")
    parser.add_argument("--baseline", metavar="FILE",
                        help="与既有 JSON 基线对比，任一项慢 20%% 以上则退出码为 1")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat 必须为不小于 1 的整数")

    env = environment_info()
    print_environment(env)

    cases, selfcheck = build_cases()
    run_selfcheck(selfcheck)
    print(f"输入规模：{N_LINES} 行，差异约 {N_CHANGES} 处；"
          f"每项计时重复 {args.repeat} 次")
    print(f"自检通过：编辑段数 {selfcheck['n_edits']}，"
          f"合并结果 {selfcheck['merged_lines']} 行（无冲突）\n")

    # 计时轮：tracemalloc 全程关闭
    results = {}
    for name, func, expected in cases:
        samples = measure_time(name, func, args.repeat, expected)
        results[name] = {
            "median_s": statistics.median(samples),
            "min_s": min(samples),
            "max_s": max(samples),
            "samples_s": samples,
        }

    # 内存轮：每项单独短开一次 tracemalloc
    for name, func, _ in cases:
        results[name]["peak_bytes"] = measure_memory(name, func)
        results[name]["peak_mib"] = results[name]["peak_bytes"] / 1024 / 1024

    print_results(results, args.repeat)

    payload = {
        "tool": "bench.py",
        "version": 1,
        "methodology": "计时轮未开启内存追踪（每项预热 1 次、重复 N 次取中位数）；"
                       "峰值内存在单独一轮开启 tracemalloc 统计",
        "environment": env,
        "config": {"lines": N_LINES, "changes": N_CHANGES,
                   "repeat": args.repeat},
        "results": results,
    }
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            raise SystemExit(f"错误：无法写入结果文件 {args.out}：{exc}")
        print(f"\n结果已写入 {args.out}")

    if args.baseline:
        failures = compare_baseline(results, args.baseline)
        if failures:
            detail = "、".join(
                f"{name}（{reference:.3f}s → {current:.3f}s，{ratio:.2f}x）"
                for name, reference, current, ratio in failures)
            print(f"\n回归项：{detail}")
            print(f"以上项目中位耗时比基线慢超过 {REGRESSION_TOLERANCE:.0%}。")
            return 1
        print("\n所有项均在基线容差范围内（无超过 20% 的耗时回归）。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
