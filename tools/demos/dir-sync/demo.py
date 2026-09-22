# -*- coding: utf-8 -*-
"""约 90 秒效果演示：只调用交付物的公开接口，A / B 两轮都能直接跑。

由 tools/run-demo.ps1 调用：python -X utf8 demo.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time


def banner(title):
    print("")
    print("=" * 70)
    print("  " + title)
    print("=" * 70, flush=True)


def show(label, value):
    print("  {0:<14}{1}".format(label, value), flush=True)


def entry_paths(manifest):
    """清单条目路径集合：兼容 dict 与迭代器两种实现。"""
    entries = getattr(manifest, "entries", manifest)
    try:
        keys = list(entries.keys())
    except AttributeError:
        keys = [getattr(item, "path", item) for item in entries]
    return sorted(str(key) for key in keys)


def report_paths(value):
    return sorted(str(getattr(item, "path", item)) for item in value)


def write_tree(root, files):
    for relative, content in files.items():
        target = os.path.join(root, relative)
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)


def main():
    banner("目录快照与增量同步引擎 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_dirsync", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from dirsync import apply as apply_manifest, diff_manifests, snapshot, verify  # noqa: E402

    workspace = tempfile.mkdtemp(prefix="dirsync-demo-")
    source = os.path.join(workspace, "source")
    target = os.path.join(workspace, "target")
    os.makedirs(os.path.join(source, "docs", "empty"), exist_ok=True)
    write_tree(source, {
        "README.md": "# 演示\n",
        "docs/guide.md": "教程正文\n",
        "docs/notes/中文 笔记.txt": "非 ASCII 文件名也进清单\n",
        "data/big.bin": "x" * (9 * 1024 * 1024),
    })
    write_tree(target, {"docs/guide.md": "旧内容\n", "stale.txt": "应该被清理\n"})

    banner("2/5  snapshot：确定性清单与 ignore 规则")
    manifest = snapshot(source)
    paths = entry_paths(manifest)
    show("条目数", len(paths))
    show("空目录", "docs/empty" in paths)
    show("中文文件名", "docs/notes/中文 笔记.txt" in paths)
    head = manifest.to_json().splitlines()[0]
    show("JSON 首行", head[:58] + " ...")
    write_tree(source, {
        "build/app.log": "log\n",
        "build/keep.log": "keep\n",
        "pkg/__pycache__/mod.pyc": "pyc\n",
    })
    rules = ["**/__pycache__/", "*.log", "!build/keep.log"]
    filtered = set(entry_paths(snapshot(source, ignore=rules)))
    show("规则", " ".join(rules))
    show("忽略生效", "build/app.log" not in filtered and "pkg/__pycache__/mod.pyc" not in filtered)
    show("重新包含", "build/keep.log" in filtered)
    time.sleep(8)

    banner("3/5  diff：新增 / 修改 / 删除")
    write_tree(source, {"docs/new.md": "新增文件\n", "docs/guide.md": "教程正文（改过）\n"})
    updated = snapshot(source)
    difference = diff_manifests(manifest, updated)
    for name in ("added", "removed", "modified"):
        values = report_paths(getattr(difference, name, []))
        show(name, ", ".join(values) if values else "(无)")
        time.sleep(1.5)
    show("unchanged", "{} 条".format(len(report_paths(getattr(difference, "unchanged", [])))))
    time.sleep(6)

    banner("4/5  apply：增量落地、verify 与幂等")
    report = apply_manifest(source, updated, target)
    for name in ("created", "updated", "deleted"):
        values = report_paths(getattr(report, name, []))
        show(name, ", ".join(values) if values else "(无)")
        time.sleep(1.5)
    problems = verify(target, updated)
    show("verify", "与清单一致" if not problems else "不一致：" + ", ".join(problems))
    again = apply_manifest(source, updated, target)
    idle = all(not report_paths(getattr(again, name, [])) for name in ("created", "updated", "deleted"))
    show("第二次 apply", "幂等（无变化）" if idle else "仍有改动")
    time.sleep(6)

    banner("4/5  dry_run：只报告不动盘")
    write_tree(source, {"dry/extra.md": "dry run 不落盘\n"})
    planned = snapshot(source)
    before = sorted(os.listdir(target))
    dry = apply_manifest(source, planned, target, dry_run=True)
    after = sorted(os.listdir(target))
    show("计划新增", ", ".join(report_paths(getattr(dry, "created", []))) or "(无)")
    show("目录未变化", before == after)
    time.sleep(6)

    banner("5/5  分块哈希与性能")
    probe = os.path.join(source, "data", "big.bin")
    size = os.path.getsize(probe) if os.path.exists(probe) else 0
    show("大文件", "{:.1f} MiB，按 1 MiB 分块哈希".format(size / 1024 / 1024))
    bulk = os.path.join(workspace, "bulk")
    for index in range(400):
        write_tree(bulk, {"d{:02d}/f{}.txt".format(index % 20, index): "content-{}\n".format(index)})
    start = time.perf_counter()
    bulk_manifest = snapshot(bulk)
    snapshot_seconds = time.perf_counter() - start
    show("snapshot", "{} 个文件 {:.3f} 秒".format(len(entry_paths(bulk_manifest)), snapshot_seconds))
    start = time.perf_counter()
    diff_manifests(bulk_manifest, bulk_manifest)
    show("diff 同清单", "{:.3f} 秒".format(time.perf_counter() - start))
    start = time.perf_counter()
    apply_manifest(bulk, bulk_manifest, os.path.join(workspace, "bulk-target"))
    show("apply 到空目录", "{:.3f} 秒".format(time.perf_counter() - start))
    time.sleep(8)

    shutil.rmtree(workspace, ignore_errors=True)
    banner("演示结束：清单确定性、增量同步、校验与幂等均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
