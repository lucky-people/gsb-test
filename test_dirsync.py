"""dirsync 的标准库 unittest 测试套件。"""

import hashlib
import json
import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dirsync
from dirsync import (
    ApplyError,
    Manifest,
    ManifestEntry,
    ManifestError,
    apply,
    diff_manifests,
    snapshot,
    verify,
)
from dirsync.manifest import CHUNK_SIZE


def make_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dirsync-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def p(self, *parts):
        return os.path.join(self.tmp, *parts)


class TestSnapshot(TempDirCase):
    def test_deterministic_and_sorted(self):
        make_file(self.p("b/2.txt"), b"2")
        make_file(self.p("a/1.txt"), b"1")
        make_file(self.p("c.txt"), b"3")
        m1 = snapshot(self.tmp)
        m2 = snapshot(self.tmp)
        self.assertEqual(m1.to_json(), m2.to_json())
        paths = m1.paths()
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(paths, ["a", "a/1.txt", "b", "b/2.txt", "c.txt"])

    def test_empty_dir_included(self):
        os.makedirs(self.p("empty/nested"))
        m = snapshot(self.tmp)
        kinds = {e.path: e.kind for e in m}
        self.assertEqual(kinds, {"empty": "dir", "empty/nested": "dir"})

    def test_chunked_hash_empty_and_large(self):
        # 0 字节文件
        make_file(self.p("zero.bin"), b"")
        # 大于 8 MiB 的文件，跨多次 1 MiB 分块
        rng = random.Random(42)
        big = rng.randbytes(8 * 1024 * 1024 + 12345)
        make_file(self.p("big.bin"), big)
        m = snapshot(self.tmp)
        entries = {e.path: e for e in m}
        self.assertEqual(
            entries["zero.bin"].sha256, hashlib.sha256(b"").hexdigest()
        )
        self.assertEqual(entries["zero.bin"].size, 0)
        self.assertEqual(entries["big.bin"].sha256, hashlib.sha256(big).hexdigest())
        self.assertEqual(entries["big.bin"].size, len(big))
        self.assertGreater(len(big), 8 * CHUNK_SIZE // 1)  # 确认 >8MiB 前提

    def test_non_ascii_and_space_names(self):
        make_file(self.p("目录 空格/中文 文件.txt"), "你好".encode("utf-8"))
        m = snapshot(self.tmp)
        self.assertIn("目录 空格/中文 文件.txt", m.paths())
        text = m.to_json()
        self.assertIn("中文 文件.txt", text)  # 非 ASCII 不转义
        self.assertNotIn("\\u4e2d", text)

    def test_symlink_recorded_with_target(self):
        make_file(self.p("real.txt"), b"x")
        os.symlink("real.txt", self.p("link"))
        m = snapshot(self.tmp)
        entries = {e.path: e for e in m}
        self.assertEqual(entries["link"].kind, "symlink")
        self.assertEqual(entries["link"].target, "real.txt")
        m_follow = snapshot(self.tmp, follow_symlinks=True)
        kinds = {e.path: e.kind for e in m_follow}
        self.assertEqual(kinds["link"], "file")


class TestManifestJson(TempDirCase):
    def test_round_trip(self):
        make_file(self.p("d/f.txt"), b"data")
        os.makedirs(self.p("empty"))
        m = snapshot(self.tmp)
        text = m.to_json()
        m2 = Manifest.from_json(text)
        self.assertEqual(m, m2)
        self.assertEqual(m2.to_json(), text)

    def test_field_order_and_trailing_newline(self):
        make_file(self.p("f.txt"), b"x")
        text = snapshot(self.tmp).to_json()
        self.assertTrue(text.endswith("\n"))
        payload = json.loads(text)
        for entry in payload["entries"]:
            self.assertEqual(
                list(entry.keys()), ["path", "kind", "size", "sha256", "target"]
            )

    def test_invalid_json(self):
        with self.assertRaises(ManifestError):
            Manifest.from_json("{not json")
        with self.assertRaises(ManifestError):
            Manifest.from_json("[1, 2]")

    def test_missing_field(self):
        entry = {"path": "a", "kind": "file", "size": 1, "sha256": "x" * 64}
        text = json.dumps({"format": "dirsync-manifest", "version": 1,
                           "entries": [entry]})
        with self.assertRaises(ManifestError):
            Manifest.from_json(text)

    def test_unknown_kind(self):
        entry = {"path": "a", "kind": "socket", "size": 0,
                 "sha256": None, "target": None}
        text = json.dumps({"format": "dirsync-manifest", "version": 1,
                           "entries": [entry]})
        with self.assertRaises(ManifestError):
            Manifest.from_json(text)

    def test_illegal_paths(self):
        bad = ["", "/abs/path", "C:/win", "c:relative", "../up", "a/../b",
               "a//b", "a/./b", "a\\b", "trail/"]
        for path in bad:
            entry = {"path": path, "kind": "dir", "size": 0,
                     "sha256": None, "target": None}
            text = json.dumps({"format": "dirsync-manifest", "version": 1,
                               "entries": [entry]})
            with self.assertRaises(ManifestError, msg=f"应拒绝路径 {path!r}"):
                Manifest.from_json(text)

    def test_duplicate_path(self):
        entry = {"path": "a", "kind": "dir", "size": 0,
                 "sha256": None, "target": None}
        text = json.dumps({"format": "dirsync-manifest", "version": 1,
                           "entries": [entry, entry]})
        with self.assertRaises(ManifestError):
            Manifest.from_json(text)


class TestIgnoreRules(TempDirCase):
    def setUp(self):
        super().setUp()
        self.build_tree()

    def build_tree(self):
        make_file(self.p("keep.txt"), b"k")
        make_file(self.p("drop.log"), b"d")
        make_file(self.p("build/out.bin"), b"b")
        make_file(self.p("src/temp.tmp"), b"t")
        make_file(self.p("src/sub/temp.tmp"), b"t2")
        make_file(self.p("logs/a.log"), b"l")
        make_file(self.p("logs/keep.log"), b"l2")

    def paths_of(self, ignore):
        return snapshot(self.tmp, ignore=ignore).paths()

    def test_fnmatch_star_not_cross_slash(self):
        paths = self.paths_of(["*.log"])
        self.assertNotIn("drop.log", paths)
        self.assertNotIn("logs/a.log", paths)  # 无斜杠规则匹配 basename
        self.assertIn("keep.txt", paths)

    def test_double_star_crosses_dirs(self):
        paths = self.paths_of(["**/temp.tmp"])
        self.assertNotIn("src/temp.tmp", paths)
        self.assertNotIn("src/sub/temp.tmp", paths)
        self.assertIn("keep.txt", paths)

    def test_double_star_matches_zero_dirs(self):
        # 回归：**/ 必须能匹配零层目录，顶层文件也要命中
        make_file(self.p("top.tmp"), b"t")
        paths = self.paths_of(["**/top.tmp"])
        self.assertNotIn("top.tmp", paths)
        self.assertIn("keep.txt", paths)

    def test_trailing_slash_ignores_subtree(self):
        paths = self.paths_of(["build/"])
        self.assertNotIn("build", paths)
        self.assertNotIn("build/out.bin", paths)

    def test_order_last_match_wins_and_reinclude(self):
        # 先忽略所有 .log，再重新包含 keep.log
        paths = self.paths_of(["*.log", "!keep.log"])
        self.assertNotIn("drop.log", paths)
        self.assertNotIn("logs/a.log", paths)
        self.assertIn("logs/keep.log", paths)
        self.assertIn("keep.txt", paths)
        # 规则顺序反过来：最后的 *.log 生效，keep.log 也被忽略
        paths2 = self.paths_of(["!keep.log", "*.log"])
        self.assertNotIn("logs/keep.log", paths2)


class TestDiff(unittest.TestCase):
    def entry(self, path, kind="file", size=1, sha="a" * 64, target=None):
        return ManifestEntry(path, kind, size, sha, target)

    def test_four_categories(self):
        old = Manifest([
            self.entry("same.txt"),
            self.entry("gone.txt"),
            self.entry("changed.txt", sha="a" * 64),
            self.entry("resized.txt", size=1),
            self.entry("link", kind="symlink", size=0, sha=None, target="x"),
            ManifestEntry("wasdir", "dir"),
        ])
        new = Manifest([
            self.entry("same.txt"),
            self.entry("born.txt"),
            self.entry("changed.txt", sha="b" * 64),
            self.entry("resized.txt", size=2),  # 仅大小变也算修改
            self.entry("link", kind="symlink", size=0, sha=None, target="y"),
            self.entry("wasdir", sha="c" * 64),  # dir -> file 算 modified
        ])
        d = diff_manifests(old, new)
        self.assertEqual(d.added, ["born.txt"])
        self.assertEqual(d.removed, ["gone.txt"])
        self.assertEqual(d.modified,
                         ["changed.txt", "link", "resized.txt", "wasdir"])
        self.assertEqual(d.unchanged, ["same.txt"])
        for lst in (d.added, d.removed, d.modified, d.unchanged):
            self.assertEqual(lst, sorted(lst))

    def test_same_size_content_change_is_modified(self):
        # 回归：等长改写（size 相同、sha256 不同）必须判为 modified
        old = Manifest([self.entry("f.txt", size=3, sha="a" * 64)])
        new = Manifest([self.entry("f.txt", size=3, sha="b" * 64)])
        d = diff_manifests(old, new)
        self.assertEqual(d.modified, ["f.txt"])
        self.assertEqual(d.unchanged, [])


class TestApply(TempDirCase):
    def setUp(self):
        super().setUp()
        self.src = self.p("src")
        self.dst = self.p("dst")
        os.makedirs(self.src)
        make_file(self.p("src/a.txt"), b"aaa")
        make_file(self.p("src/sub/b.txt"), b"bbb")
        os.makedirs(self.p("src/emptydir"))
        self.manifest = snapshot(self.src)

    def test_apply_and_idempotent(self):
        r1 = apply(self.src, self.manifest, self.dst)
        self.assertEqual(r1.created_count, 4)
        self.assertEqual(r1.updated_count, 0)
        self.assertEqual(r1.deleted_count, 0)
        self.assertEqual(verify(self.dst, self.manifest), [])
        # 第二次 apply：三个列表全空，幂等
        r2 = apply(self.src, self.manifest, self.dst)
        self.assertEqual(r2.created, [])
        self.assertEqual(r2.updated, [])
        self.assertEqual(r2.deleted, [])
        self.assertEqual(r2.unchanged_count, 4)

    def test_atomic_write_leaves_no_temp_files(self):
        apply(self.src, self.manifest, self.dst)
        for root, _dirs, files in os.walk(self.dst):
            for name in files:
                self.assertFalse(name.startswith(".dirsync-"),
                                 f"残留临时文件 {name}")
        with open(self.p("dst/a.txt"), "rb") as f:
            self.assertEqual(f.read(), b"aaa")

    def test_update_modified_file(self):
        apply(self.src, self.manifest, self.dst)
        make_file(self.p("src/a.txt"), b"changed")
        m2 = snapshot(self.src)
        r = apply(self.src, m2, self.dst)
        self.assertEqual(r.updated, ["a.txt"])
        self.assertEqual(verify(self.dst, m2), [])

    def test_prune_on_and_off(self):
        apply(self.src, self.manifest, self.dst)
        make_file(self.p("dst/extra.txt"), b"extra")
        # prune=False：保留多余文件
        r = apply(self.src, self.manifest, self.dst, prune=False)
        self.assertEqual(r.deleted, [])
        self.assertTrue(os.path.exists(self.p("dst/extra.txt")))
        # prune=True：删除多余文件
        r2 = apply(self.src, self.manifest, self.dst, prune=True)
        self.assertEqual(r2.deleted, ["extra.txt"])
        self.assertFalse(os.path.exists(self.p("dst/extra.txt")))

    def test_dry_run_changes_nothing(self):
        before = snapshot(self.dst) if os.path.isdir(self.dst) else None
        r = apply(self.src, self.manifest, self.dst, dry_run=True)
        self.assertEqual(r.created_count, 4)
        self.assertFalse(os.path.exists(self.dst))  # 磁盘一个字节都没改
        # 已有部分文件时 dry_run 也不应改动
        os.makedirs(self.dst)
        make_file(self.p("dst/a.txt"), b"old")
        apply(self.src, self.manifest, self.dst, dry_run=True)
        with open(self.p("dst/a.txt"), "rb") as f:
            self.assertEqual(f.read(), b"old")
        self.assertFalse(os.path.exists(self.p("dst/sub")))

    def test_source_tampered_raises_and_untouched(self):
        apply(self.src, self.manifest, self.dst)
        # 快照后源文件被改动
        make_file(self.p("src/a.txt"), b"tampered!")
        make_file(self.p("dst/a.txt"), b"keepme")
        with self.assertRaises(ApplyError):
            apply(self.src, self.manifest, self.dst)
        # 目标未被修改
        with open(self.p("dst/a.txt"), "rb") as f:
            self.assertEqual(f.read(), b"keepme")

    def test_source_tampered_same_size_raises(self):
        # 回归：待更新文件的源被等长篡改（size 不变、sha256 变）也要拦
        apply(self.src, self.manifest, self.dst)
        make_file(self.p("src/a.txt"), b"XXX")  # 与 "aaa" 等长
        make_file(self.p("dst/a.txt"), b"keepme")
        with self.assertRaises(ApplyError):
            apply(self.src, self.manifest, self.dst)
        with open(self.p("dst/a.txt"), "rb") as f:
            self.assertEqual(f.read(), b"keepme")

    def test_source_check_covers_created_and_updated(self):
        # 回归：新建与待更新的文件都要核对源，缺一不可
        apply(self.src, self.manifest, self.dst)
        make_file(self.p("src/new.txt"), b"new")
        make_file(self.p("src/sub/b.txt"), b"tampered")
        m2 = snapshot(self.src)
        # 篡改 m2 清单里 sub/b.txt 的 sha256，模拟快照后源被改动
        entries = [
            ManifestEntry(e.path, e.kind, e.size,
                          "0" * 64 if e.path == "sub/b.txt" else e.sha256,
                          e.target)
            for e in m2
        ]
        m3 = Manifest(entries)
        before = snapshot(self.dst)
        with self.assertRaises(ApplyError):
            apply(self.src, m3, self.dst)
        self.assertEqual(snapshot(self.dst), before)  # 目标保持原样

    def test_kind_switch_file_to_dir(self):
        apply(self.src, self.manifest, self.dst)
        os.unlink(self.p("src/a.txt"))
        os.makedirs(self.p("src/a.txt"))
        make_file(self.p("src/a.txt/inner.txt"), b"i")
        m2 = snapshot(self.src)
        r = apply(self.src, m2, self.dst)
        self.assertIn("a.txt", r.updated)
        self.assertEqual(verify(self.dst, m2), [])


class TestVerify(TempDirCase):
    def setUp(self):
        super().setUp()
        self.src = self.p("src")
        os.makedirs(self.src)
        make_file(self.p("src/a.txt"), b"aaa")
        make_file(self.p("src/sub/b.txt"), b"bbb")
        self.manifest = snapshot(self.src)
        self.dst = self.p("dst")
        apply(self.src, self.manifest, self.dst)

    def test_clean_returns_empty(self):
        self.assertEqual(verify(self.dst, self.manifest), [])

    def test_detects_tamper_missing_and_extra(self):
        make_file(self.p("dst/a.txt"), b"hacked")     # 内容篡改
        os.unlink(self.p("dst/sub/b.txt"))             # 缺失
        make_file(self.p("dst/rogue.txt"), b"rogue")   # 多余
        bad = verify(self.dst, self.manifest)
        self.assertEqual(bad, ["a.txt", "rogue.txt", "sub/b.txt"])
        self.assertEqual(bad, sorted(bad))

    def test_detects_same_size_tamper(self):
        # 回归：等长篡改（大小不变、内容变了）也要被 verify 检出
        make_file(self.p("dst/a.txt"), b"XXX")  # 与 "aaa" 等长
        self.assertEqual(verify(self.dst, self.manifest), ["a.txt"])

    def test_detects_kind_mismatch(self):
        os.unlink(self.p("dst/a.txt"))
        os.makedirs(self.p("dst/a.txt"))
        self.assertEqual(verify(self.dst, self.manifest), ["a.txt"])


if __name__ == "__main__":
    unittest.main()
