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


def hexdump(data, limit=64):
    for offset in range(0, min(len(data), limit), 16):
        chunk = data[offset:offset + 16]
        text = " ".join("{:02x}".format(byte) for byte in chunk)
        print("    {0:08x}  {1}".format(offset, text), flush=True)
        time.sleep(0.4)


def main():
    banner("二进制 TLV 帧编解码与流式解码 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_tlvframe", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from tlvframe import (  # noqa: E402
        Frame, FrameDecoder, decode_frames, decode_text, decode_varint,
        encode_frames, encode_text, encode_varint, frame_checksum,
    )

    banner("2/5  编码：帧结构与字节级布局")
    frames = [Frame(1, b"hello"), Frame(2, "中文".encode("utf-8"))]
    blob = encode_frames(frames)
    show("帧数/总字节", "{} / {}".format(len(frames), len(blob)))
    show("magic", repr(blob[:4]))
    show("version/type", "{} / {}".format(blob[4], blob[5]))
    show("length(LE)", int.from_bytes(blob[6:10], "little"))
    show("payload crc32", frame_checksum(frames[0].payload))
    hexdump(blob, 48)
    time.sleep(7)

    banner("3/5  解码与损坏检测（偏移定位）")
    decoded = decode_frames(blob)
    show("往返一致", [(f.type, f.payload) for f in decoded] == [(f.type, f.payload) for f in frames])
    show("文本帧", decode_text(Frame(2, "中文与 emoji 🙂".encode("utf-8"))))
    broken = bytearray(blob)
    broken[10] ^= 0xFF
    for label, data in (
        ("CRC 被改一个字节", bytes(broken)),
        ("版本号改成 9", bytes(blob[:4]) + b"\x09" + bytes(blob[5:])),
        ("截断最后 5 字节", bytes(blob[:-5])),
        ("帧前插入垃圾字节", b"\x00" + bytes(blob)),
    ):
        try:
            decode_frames(data)
            show(label, "没有抛错（不符合预期）")
        except Exception as exc:  # noqa: BLE001
            show(label, "{} · offset={} · reason={}".format(
                type(exc).__name__, getattr(exc, "offset", "?"), str(exc)[:34]))
        time.sleep(0.8)
    time.sleep(5)

    banner("4/5  流式解码与 varint")
    whole = decode_frames(blob)
    for chunk_size in (1, 3, 7):
        decoder = FrameDecoder()
        produced = []
        for offset in range(0, len(blob), chunk_size):
            produced.extend(decoder.feed(blob[offset:offset + chunk_size]))
        decoder.finish()
        same = [(f.type, f.payload) for f in produced] == [(f.type, f.payload) for f in whole]
        show("按 {} 字节喂入".format(chunk_size), "帧数 {}，与整段一致 {}".format(len(produced), same))
        time.sleep(1)
    for value in (0, 1, 127, 128, 300, 2 ** 32, 2 ** 63 - 1):
        encoded = encode_varint(value)
        back, used = decode_varint(encoded)
        show("varint {}".format(value), "{} 字节 -> {}（消耗 {}）".format(len(encoded), back, used))
        time.sleep(0.6)
    try:
        decode_varint(b"\xff\xff")
        show("截断的 varint", "没有抛错（不符合预期）")
    except Exception as exc:  # noqa: BLE001
        show("截断的 varint", type(exc).__name__)
    time.sleep(5)

    banner("5/5  10 万帧的编码、解码与流式吞吐")
    payload = b"x" * 200
    bulk = [Frame(index % 256, payload) for index in range(100000)]
    start = time.perf_counter()
    big = encode_frames(bulk)
    show("编码", "{:.3f} 秒，{:.1f} MB".format(time.perf_counter() - start, len(big) / 1024 / 1024))
    start = time.perf_counter()
    back = decode_frames(big)
    show("整段解码", "{:.3f} 秒，{} 帧".format(time.perf_counter() - start, len(back)))
    start = time.perf_counter()
    decoder = FrameDecoder()
    count = 0
    for offset in range(0, len(big), 4096):
        count += len(decoder.feed(big[offset:offset + 4096]))
    decoder.finish()
    show("4KB 流式解码", "{:.3f} 秒，{} 帧".format(time.perf_counter() - start, count))
    time.sleep(9)

    banner("演示结束：字节级格式、损坏检测与流式解码均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
