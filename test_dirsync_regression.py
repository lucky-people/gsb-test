"""dirsync 缺陷回归测试：规则顺序求值 / 重新包含 / dry_run 只读。"""

import os
import shutil
import tempfile
import unittest

import dirsync
from dirsync import apply, snapshot


def make_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dirsync-reg-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def p(self, *parts):
        return os.path.join(self.tmp, *parts)


class TestReincludeRegression(TempDirCase):
    def setUp(self):
        super().setUp()
        make_file(self.p("keep.txt"), b"k")
        make_file(self.p("drop.log"), b"d")
        make_file(self.p("logs/a.log"), b"l")
        make_file(self.p("logs/keep.log"), b"l2")

    def test_ignore_then_reinclude_keep_log(self):
        # ["*.log", "!logs/keep.log"]：先忽略所有 .log，
        # 最后一条匹配的是重新包含规则，logs/keep.log 必须留在清单里。
        manifest = snapshot(self.tmp, ignore=["*.log", "!logs/keep.log"])
        paths = manifest.paths()
        self.assertNotIn("drop.log", paths)
        self.assertNotIn("logs/a.log", paths)
        self.assertIn("logs/keep.log", paths)
        self.assertIn("logs", paths)
        self.assertIn("keep.txt", paths)
        # 被重新包含的文件必须真正参与快照（内容哈希已计算）
        entries = {e.path: e for e in manifest}
        self.assertEqual(entries["logs/keep.log"].kind, "file")
        self.assertEqual(len(entries["logs/keep.log"].sha256), 64)

    def test_plain_rule_after_negation_wins(self):
        # ["!keep.txt", "*.txt"]：后面的普通规则覆盖前面的 !，
        # keep.txt 仍然被忽略（顺序严格求值，不允许把 ! 提到最高优先级）。
        paths = snapshot(self.tmp, ignore=["!keep.txt", "*.txt"]).paths()
        self.assertNotIn("keep.txt", paths)
        # 作为对照：只有 ! 时 keep.txt 应保留
        paths2 = snapshot(self.tmp, ignore=["!keep.txt"]).paths()
        self.assertIn("keep.txt", paths2)


class TestMixedOrderRules(TempDirCase):
    def test_three_rules_mixed_order(self):
        # 三条以上规则混合：忽略 *.tmp、忽略任意层级的 cache/ 子树、
        # 再把 cache/keep.tmp 重新包含。
        make_file(self.p("keep.txt"), b"k")
        make_file(self.p("drop.tmp"), b"d")
        make_file(self.p("src/work.tmp"), b"w")
        make_file(self.p("cache/keep.tmp"), b"c")
        make_file(self.p("cache/junk.tmp"), b"j")
        make_file(self.p("cache/note.txt"), b"n")
        make_file(self.p("cache/sub/deep.tmp"), b"s")
        rules = ["*.tmp", "**/cache/", "!cache/keep.tmp"]
        paths = snapshot(self.tmp, ignore=rules).paths()
        # 重新包含生效
        self.assertIn("cache/keep.tmp", paths)
        # 其余 .tmp 全部忽略（根目录、普通子目录、cache 深处）
        self.assertNotIn("drop.tmp", paths)
        self.assertNotIn("src/work.tmp", paths)
        self.assertNotIn("cache/junk.tmp", paths)
        self.assertNotIn("cache/sub/deep.tmp", paths)
        # cache 目录本身及其未被重新包含的子条目仍被剪掉
        self.assertNotIn("cache", paths)
        self.assertNotIn("cache/note.txt", paths)
        self.assertNotIn("cache/sub", paths)
        # 未命中规则的条目不受影响
        self.assertIn("keep.txt", paths)
        self.assertIn("src", paths)
        # 规则顺序换成 ! 在前：最后的目录忽略规则覆盖重新包含
        rules2 = ["*.tmp", "!cache/keep.tmp", "**/cache/"]
        paths2 = snapshot(self.tmp, ignore=rules2).paths()
        self.assertNotIn("cache/keep.tmp", paths2)


class TestDryRunReadOnly(TempDirCase):
    def test_dry_run_preserves_mtime_and_content(self):
        src = self.p("src")
        dst = self.p("dst")
        make_file(self.p("src/a.txt"), b"aaa")
        make_file(self.p("src/sub/b.txt"), b"bbb")
        manifest = snapshot(src)
        # 预置一个与清单不同的目标目录
        os.makedirs(dst)
        make_file(self.p("dst/a.txt"), b"old-content")
        old_mtime = 1_000_000_000  # 固定的旧时间戳，便于证明没被动过
        os.utime(dst, (old_mtime, old_mtime))
        os.utime(self.p("dst/a.txt"), (old_mtime, old_mtime))
        stat_before_dir = os.stat(dst)
        stat_before_file = os.stat(self.p("dst/a.txt"))
        listing_before = sorted(os.listdir(dst))

        report = apply(src, manifest, dst, dry_run=True)
        self.assertIn("a.txt", report.updated)
        self.assertIn("sub", report.created)
        self.assertIn("sub/b.txt", report.created)

        # 目录与文件的 mtime（纳秒精度）都不能变
        self.assertEqual(os.stat(dst).st_mtime_ns, stat_before_dir.st_mtime_ns)
        self.assertEqual(os.stat(self.p("dst/a.txt")).st_mtime_ns,
                         stat_before_file.st_mtime_ns)
        # 内容不能变，不能多出条目（sub/ 不允许被创建）
        with open(self.p("dst/a.txt"), "rb") as f:
            self.assertEqual(f.read(), b"old-content")
        self.assertEqual(sorted(os.listdir(dst)), listing_before)
        self.assertFalse(os.path.exists(self.p("dst/sub")))

    def test_dry_run_creates_nothing_when_target_missing(self):
        src = self.p("src")
        dst = self.p("dst")
        make_file(self.p("src/a.txt"), b"a")
        manifest = snapshot(src)
        parent_before = os.stat(self.tmp).st_mtime_ns
        report = apply(src, manifest, dst, dry_run=True)
        self.assertEqual(report.created, ["a.txt"])
        self.assertFalse(os.path.exists(dst))
        # 连父目录都不应该被改动
        self.assertEqual(os.stat(self.tmp).st_mtime_ns, parent_before)

    def test_dry_run_still_rejects_tampered_source(self):
        # dry_run 也要在报告前复核源文件；快照后被改动必须抛 ApplyError
        src = self.p("src")
        dst = self.p("dst")
        make_file(self.p("src/a.txt"), b"a")
        manifest = snapshot(src)
        with open(self.p("src/a.txt"), "wb") as f:
            f.write(b"tampered")
        with self.assertRaises(dirsync.ApplyError):
            apply(src, manifest, dst, dry_run=True)
        self.assertFalse(os.path.exists(dst))


if __name__ == "__main__":
    unittest.main()
