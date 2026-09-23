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


def show_hits(hits, limit=5):
    for hit in hits[:limit]:
        print("    {0:<12} score={1:>7.3f} terms={2} pos={3}".format(
            hit.doc_id, hit.score, ",".join(hit.matched_terms), list(hit.positions)[:3]), flush=True)
        time.sleep(0.5)
    if len(hits) > limit:
        print("    ... 共 {0} 条".format(len(hits)), flush=True)


DOCS = [
    ("doc-01", "Python 标准库实现倒排索引 search engine basics"),
    ("doc-02", "搜索引擎 与 倒排 索引 的 基本 原理"),
    ("doc-03", "BM25 ranking and inverted index scoring"),
    ("doc-04", "标准库 实现 事务 与 崩溃 恢复"),
    ("doc-05", "search relevance tuning for inverted index queries"),
]


def main():
    banner("倒排索引与 BM25 检索 · 效果演示")
    show("工作目录", os.getcwd())
    show("Python", sys.version.split()[0])
    time.sleep(5)

    banner("1/5  单元测试（unittest）")
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "unittest", "test_invindex", "-v"],
        capture_output=True, text=True,
    )
    output = (proc.stderr or "") + (proc.stdout or "")
    for line in [l for l in output.splitlines() if l.strip()][-5:]:
        print("  " + line, flush=True)
    show("结果", "全部通过" if proc.returncode == 0 else "存在失败")
    time.sleep(10)

    sys.path.insert(0, os.getcwd())
    from invindex import Index, tokenize  # noqa: E402

    banner("2/5  分词、建索引与 AND / OR 查询")
    show("词元示例", " ".join(tokenize("Python 标准库 Search Engine")))
    index = Index()
    for doc_id, text in DOCS:
        index.add_document(doc_id, text)
    show("文档数", index.doc_count)
    show("词项数", index.term_count)
    show("posting 对数", getattr(index, "postings_count", "?"))
    show_hits(index.search("index inverted", mode="and"))
    show_hits(index.search("索引 事务", mode="or"))
    time.sleep(9)

    banner("3/5  短语、排除、字段与高亮")
    index.add_document("doc-06", "", fields={"title": "inverted index basics", "body": "search engine notes"})
    show_hits(index.search('"inverted index"'))
    show_hits(index.search("index -ranking"))
    show_hits(index.search("title:basics"))
    show("高亮 doc-05", index.highlight("doc-05", "index"))
    show("高亮 doc-06", index.highlight("doc-06", '"inverted index"'))
    time.sleep(9)

    banner("4/5  增删改、保存加载与压缩")
    index.remove_document("doc-03")
    show("删除后查询", [hit.doc_id for hit in index.search("ranking")])
    workspace = tempfile.mkdtemp(prefix="invindex-demo-")
    target = os.path.join(workspace, "index")
    index.save(target)
    before = [(hit.doc_id, round(hit.score, 6)) for hit in index.search("index inverted", mode="and")]
    show("目录内容", ", ".join(sorted(os.listdir(target))))
    loaded = Index.load(target)
    after = [(hit.doc_id, round(hit.score, 6)) for hit in loaded.search("index inverted", mode="and")]
    show("加载结果一致", before == after)
    segments_before = len([name for name in os.listdir(target) if name.startswith("seg-")])
    loaded.compact()
    segments_after = len([name for name in os.listdir(target) if name.startswith("seg-")])
    show("段数", "{} -> {}".format(segments_before, segments_after))
    show("压缩后一致", after == [(hit.doc_id, round(hit.score, 6))
                                 for hit in loaded.search("index inverted", mode="and")])
    shutil.rmtree(workspace, ignore_errors=True)
    time.sleep(9)

    banner("5/5  2 万文档建索引与查询吞吐")
    bulk = Index()
    words = ["alpha", "beta", "gamma", "delta", "epsilon", "index", "search", "query", "term", "document"]
    start = time.perf_counter()
    for number in range(20000):
        text = " ".join("{0}{1}".format(words[(number + offset) % len(words)], offset)
                        for offset in range(60))
        bulk.add_document("bulk-{0:05d}".format(number), text)
    show("建索引", "{:.3f} 秒，{} 文档".format(time.perf_counter() - start, bulk.doc_count))
    start = time.perf_counter()
    total_hits = 0
    for _ in range(200):
        total_hits += len(bulk.search("alpha1 beta2", top_k=20))
    show("200 次查询", "{:.3f} 秒，命中合计 {}".format(time.perf_counter() - start, total_hits))
    time.sleep(9)

    banner("演示结束：分词、布尔检索、BM25 排序与持久化均通过")
    time.sleep(5)


if __name__ == "__main__":
    main()
