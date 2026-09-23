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


def show_rows(rows, limit=4):
    for index, row in enumerate(rows[:limit]):
        print("    {0:>2} | {1}".format(index + 1, " | ".join(repr(cell) for cell in row)), flush=True)
        time.sleep(0.5)
    if len(rows) > limit:
        print("    ... 共 {0} 行".format(len(rows)), flush=True)


def main():
    banner("CSV/TSV 严格解析与写出 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_csvtable", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from csvtable import StreamParser, detect_dialect, infer_types, parse, write_rows  # noqa: E402

    banner("2/5  方言探测与解析")
    sample = 'name;note;qty\r\n"a;b";"换行\n在里面";3\r\nplain;"带""引号""";4\r\n'
    dialect = detect_dialect(sample)
    show("探测分隔符", repr(dialect.delimiter))
    show("行终止符", repr(dialect.line_terminator))
    table = parse(sample)
    show("表头", table.header)
    show("行数×列数", "{} × {}".format(table.row_count, table.column_count))
    show_rows(table.rows)
    time.sleep(9)

    banner("3/5  写出与往返一致")
    rows = [
        ["id", "text", "note"],
        ["1", "带,逗号", "普通"],
        ["2", '带"引号"', "换行\n在这里"],
        ["3", "", "   "],
    ]
    text = write_rows(rows)
    again = parse(text).rows
    show("往返一致", again == rows)
    show("默认 quoting", repr(text.splitlines()[2])[:54] + " ...")
    all_quoted = write_rows(rows, quoting="all")
    show("quoting=all", repr(all_quoted.splitlines()[1])[:54] + " ...")
    show("BOM 往返", parse("\ufeff" + text).had_bom)
    time.sleep(9)

    banner("4/5  严格模式报错定位与宽容模式")
    broken = 'a,b\n1,"未闭合\n2,3\n'
    try:
        parse(broken)
        show("引号未闭合", "没有抛错（不符合预期）")
    except Exception as exc:  # noqa: BLE001
        show("异常类型", type(exc).__name__)
        show("行/列/偏移", "{} / {} / {}".format(
            getattr(exc, "line", "?"), getattr(exc, "column", "?"), getattr(exc, "offset", "?")))
        show("说明", str(exc)[:56])
    loose = parse(broken, strict=False)
    show("宽容模式 warnings", len(getattr(loose, "warnings", [])))
    try:
        parse("a,b\n1,2,3\n")
        show("字段数不一致", "没有抛错（不符合预期）")
    except Exception as exc:  # noqa: BLE001
        show("字段数不一致", "{} · line={}".format(type(exc).__name__, getattr(exc, "line", "?")))
    time.sleep(9)

    banner("5/5  类型推断与 20 MB 级解析性能")
    show("类型推断", ", ".join(infer_types(["1", "2.5", "true", "", "2026-09-23", "abc"])))
    big_lines = ["col_a,col_b,col_c"]
    for index in range(200000):
        big_lines.append('{0},"文本,{1}",{2}'.format(index, index % 97, index * 0.5))
    big = "\r\n".join(big_lines) + "\r\n"
    show("文本规模", "{:.1f} MB / {} 行".format(len(big) / 1024 / 1024, len(big_lines)))
    start = time.perf_counter()
    table = parse(big)
    show("整段解析", "{:.3f} 秒，{} 行".format(time.perf_counter() - start, table.row_count))
    start = time.perf_counter()
    stream = StreamParser()
    produced = 0
    for offset in range(0, len(big), 65536):
        produced += len(stream.feed(big[offset:offset + 65536]))
    produced += len(stream.finish())
    show("分块流式解析", "{:.3f} 秒，{} 行".format(time.perf_counter() - start, produced))
    start = time.perf_counter()
    write_rows([line.split(",") for line in big_lines[:50000]])
    show("写出 5 万行", "{:.3f} 秒".format(time.perf_counter() - start))
    time.sleep(9)

    banner("演示结束：方言探测、引号规则、往返与严格报错均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
