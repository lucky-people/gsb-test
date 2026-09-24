"""把 bench.py --out 生成的 JSON 结果渲染成 Markdown 表格，便于贴进 README。

用法：python render_bench.py bench-result.json
只用标准库；不重新测量，只做结果渲染。
"""

import json
import sys

CASE_ORDER = ("diff", "unified", "apply", "merge")


def render(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    env = data.get("environment", {})
    cfg = data.get("config", {})
    print(f"实测环境：{env.get('platform', '未知平台')}、"
          f"{env.get('cpu', '未知 CPU')}、"
          f"{env.get('implementation', 'Python')} {env.get('python', '?')}。"
          f"每项预热 1 次后重复 {cfg.get('repeat', '?')} 次，"
          "取中位数（最小–最大）：\n")
    print("| 阶段 | 中位耗时 | 最小–最大 | 峰值内存 |")
    print("| --- | --- | --- | --- |")
    for name in CASE_ORDER:
        r = data["results"][name]
        print(f"| {name} | {r['median_s']:.2f} s | "
              f"{r['min_s']:.2f}–{r['max_s']:.2f} s | "
              f"约 {r['peak_mib']:.0f} MiB |")


def main(argv):
    if len(argv) != 2:
        return "用法：python render_bench.py bench-result.json"
    render(argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
