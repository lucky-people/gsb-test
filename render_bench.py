"""把 bench.py --out 生成的 JSON 结果渲染成 Markdown 表格，便于贴进 README。

用法：python render_bench.py bench-result.json
只用标准库。
"""

import json
import sys

CASE_ORDER = ("diff", "unified", "apply", "merge")


def render(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    env = data["environment"]
    cfg = data["config"]
    print(f"实测环境：{env['platform']}、{env['cpu']}、"
          f"{env['implementation']} {env['python']}。"
          f"每项预热 1 次后重复 {cfg['repeat']} 次，取中位数（最小–最大）：\n")
    print("| 阶段 | 中位耗时 | 最小–最大 | 峰值内存 |")
    print("| --- | --- | --- | --- |")
    for name in CASE_ORDER:
        r = data["results"][name]
        print(f"| {name} | {r['median_s']:.2f} s | "
              f"{r['min_s']:.2f}–{r['max_s']:.2f} s | "
              f"约 {r['peak_mib']:.0f} MiB |")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("用法：python render_bench.py bench-result.json")
    render(sys.argv[1])
