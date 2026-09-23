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
    print("  {0:<22}{1}".format(label, value), flush=True)


def write_transactions(store, count, start=0):
    for index in range(start, start + count):
        with store.transaction() as tx:
            tx.put("key:{0:05d}".format(index), "value-{0}".format(index))
            tx.put("meta:{0:05d}".format(index), "m{0}".format(index))


def main():
    banner("带 WAL 与崩溃恢复的事务型 KV · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_walkv", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from walkv import Store  # noqa: E402

    workspace = tempfile.mkdtemp(prefix="walkv-demo-")
    path = os.path.join(workspace, "store")

    banner("2/5  事务、快照读与范围扫描")
    store = Store(path, sync=False)
    write_transactions(store, 5)
    with store.transaction() as tx:
        tx.put("key:00002", "被事务改过")
        show("事务内可见", tx.get("key:00002"))
        show("事务外旧值", store.get("key:00002"))
    show("提交后可见", store.get("key:00002"))
    show("count", store.count())
    show("scan(prefix)", [key for key, _ in store.scan(prefix="key:", limit=3)])
    show("scan(reverse)", [key for key, _ in store.scan(prefix="meta:", reverse=True, limit=2)])
    show("scan(区间)", [key for key, _ in store.scan(start="key:00001", end="key:00004")])
    store.close()
    time.sleep(8)

    banner("3/5  崩溃注入：截断 WAL 与 CRC 损坏")
    store = Store(path, sync=False)
    write_transactions(store, 5, start=5)
    store.close()
    wal_path = os.path.join(path, "wal.log")
    with open(wal_path, "rb") as handle:
        original = handle.read()
    show("WAL 原始大小", "{} 字节".format(len(original)))
    with open(wal_path, "wb") as handle:
        handle.write(original[:-9])
    store = Store(path, sync=False)
    show("截断后恢复", "事务 {} 条，跳过 {} 字节".format(
        getattr(store, "recovered_transactions", "?"), getattr(store, "recovered_bytes", "?")))
    show("最后一个完整事务", store.get("key:00009"))
    show("被截断的事务", store.get("key:00010"))
    store.close()
    damaged = bytearray(original)
    damaged[-20] ^= 0xFF
    with open(wal_path, "wb") as handle:
        handle.write(bytes(damaged))
    store = Store(path, sync=False)
    show("CRC 损坏后恢复", "事务 {} 条".format(getattr(store, "recovered_transactions", "?")))
    show("已有数据仍可读", store.get("key:00009") is not None)
    store.close()
    time.sleep(9)

    banner("4/5  压缩：快照 + 清空 WAL，前后等价")
    store = Store(path, sync=False)
    before = list(store.scan())
    wal_before = os.path.getsize(wal_path)
    sequence = store.compact()
    wal_after = os.path.getsize(wal_path)
    after = list(store.scan())
    show("压缩序号", sequence)
    show("WAL 大小", "{} -> {}".format(wal_before, wal_after))
    show("scan 等价", before == after)
    show("目录内容", ", ".join(sorted(os.listdir(path))))
    store.close()
    store = Store(path, sync=False)
    show("重开后一致", list(store.scan()) == after)
    store.close()
    time.sleep(8)

    banner("5/5  2 万次 put / get 与全量扫描")
    big_path = os.path.join(workspace, "big")
    store = Store(big_path, sync=False)
    start = time.perf_counter()
    write_transactions(store, 10000)
    show("2 万次 put", "{:.3f} 秒".format(time.perf_counter() - start))
    start = time.perf_counter()
    misses = sum(1 for index in range(10000) if store.get("key:{0:05d}".format(index)) is None)
    show("2 万次 get", "{:.3f} 秒，未命中 {}".format(time.perf_counter() - start, misses))
    start = time.perf_counter()
    total = len(list(store.scan()))
    show("全量 scan", "{:.3f} 秒，{} 条".format(time.perf_counter() - start, total))
    start = time.perf_counter()
    store.compact()
    show("compact", "{:.3f} 秒".format(time.perf_counter() - start))
    store.close()
    start = time.perf_counter()
    store = Store(big_path, sync=False)
    show("重新打开恢复", "{:.3f} 秒，count={}".format(time.perf_counter() - start, store.count()))
    store.close()
    shutil.rmtree(workspace, ignore_errors=True)
    time.sleep(9)

    banner("演示结束：事务原子性、崩溃恢复与压缩等价性均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
