"""按清单把目标目录同步成与源目录一致的状态。

安全约束：
- 动手前先全量校验清单，并核对 source 里每个待写文件的 size 与 sha256，
  不一致就抛 ApplyError，且此时不修改任何文件；
- 写文件必须原子：同目录临时文件 + os.replace；
- dry_run=True 时不修改磁盘上的任何字节。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List

from .diff import diff_manifests
from .errors import ApplyError
from .manifest import (
    KIND_DIR,
    KIND_FILE,
    KIND_SYMLINK,
    Manifest,
    _validate_entry,
    hash_file,
    snapshot,
)


@dataclass
class ApplyReport:
    """一次 apply 的结果报告，四个列表均按字典序。"""

    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)

    @property
    def created_count(self) -> int:
        return len(self.created)

    @property
    def updated_count(self) -> int:
        return len(self.updated)

    @property
    def deleted_count(self) -> int:
        return len(self.deleted)

    @property
    def unchanged_count(self) -> int:
        return len(self.unchanged)


def _check_source_files(source_root: str, manifest: Manifest, to_write: List[str]) -> None:
    """核对 source 里每个待写文件的 size 与 sha256，不一致抛 ApplyError。"""
    wanted: Dict[str, object] = {e.path: e for e in manifest}
    for rel in to_write:
        entry = wanted[rel]
        if entry.kind != KIND_FILE:
            continue
        src = os.path.join(source_root, rel)
        if not os.path.isfile(src) or os.path.islink(src):
            raise ApplyError(f"源文件缺失或不是普通文件: {rel!r}")
        actual_size = os.path.getsize(src)
        if actual_size != entry.size:
            raise ApplyError(
                f"源文件大小与清单不符: {rel!r} "
                f"(清单 {entry.size} 字节, 实际 {actual_size} 字节)"
            )
        actual_sha = hash_file(src)
        if actual_sha != entry.sha256:
            raise ApplyError(f"源文件内容与清单不符 (sha256 不匹配): {rel!r}")


def _atomic_write_file(src: str, dst: str) -> None:
    """同目录临时文件 + os.replace，保证目标路径要么旧要么新。"""
    dst_dir = os.path.dirname(dst) or "."
    os.makedirs(dst_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".dirsync-", dir=dst_dir)
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as f:
            shutil.copyfileobj(f, out, length=1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        shutil.copymode(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_symlink(target: str, dst: str) -> None:
    """先建临时符号链接再 os.replace，避免中途出现缺失窗口。"""
    dst_dir = os.path.dirname(dst) or "."
    os.makedirs(dst_dir, exist_ok=True)
    tmp = os.path.join(dst_dir, f".dirsync-{os.getpid()}-{id(dst)}")
    try:
        os.symlink(target, tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _remove_path(path: str) -> None:
    """删除文件/符号链接/目录（目录递归删除）。"""
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)


def apply(
    source_root: str,
    manifest: Manifest,
    target_root: str,
    dry_run: bool = False,
    prune: bool = True,
) -> ApplyReport:
    """按 manifest 把 target_root 同步成 source_root 的状态。

    - dry_run=True：只计算报告，不修改磁盘；
    - prune=True：删除目标里清单外的多余条目；False 时保留。
    """
    if not isinstance(manifest, Manifest):
        raise ApplyError("manifest 必须是 Manifest 实例")
    # 动手前先全量校验清单（构造时已校验，这里再显式复核一遍）
    for entry in manifest:
        _validate_entry(entry)

    if os.path.isdir(target_root):
        current = snapshot(target_root)
    else:
        current = Manifest([])
    diff = diff_manifests(current, manifest)

    created = diff.added
    updated = diff.modified
    unchanged = diff.unchanged
    deleted = diff.removed if prune else []

    # 核对 source 里每个待写文件，失败则抛错且此时未修改任何文件
    _check_source_files(source_root, manifest, created + updated)

    report = ApplyReport(
        created=created, updated=updated, deleted=deleted, unchanged=unchanged
    )
    if dry_run:
        return report

    entries: Dict[str, object] = {e.path: e for e in manifest}
    current_kinds: Dict[str, str] = {e.path: e.kind for e in current}

    if not os.path.isdir(target_root):
        os.makedirs(target_root, exist_ok=True)

    # 1. 删除多余条目：先删文件/链接，再按深度从深到浅删目录
    for rel in sorted(deleted, key=lambda p: (p.count("/"), p), reverse=True):
        victim = os.path.join(target_root, rel)
        if os.path.lexists(victim):
            _remove_path(victim)

    # 2. kind 切换（如 file <-> dir）的条目先删旧，避免挡住后续创建
    for rel in updated:
        entry = entries[rel]
        old_kind = current_kinds.get(rel)
        dst = os.path.join(target_root, rel)
        if old_kind is not None and old_kind != entry.kind and os.path.lexists(dst):
            _remove_path(dst)

    # 3. 处理 created / updated（按字典序，保证父目录先于子条目创建）
    for rel in sorted(created + updated):
        entry = entries[rel]
        dst = os.path.join(target_root, rel)
        if entry.kind == KIND_DIR:
            os.makedirs(dst, exist_ok=True)
        elif entry.kind == KIND_FILE:
            src = os.path.join(source_root, rel)
            _atomic_write_file(src, dst)
        else:  # symlink
            _atomic_write_symlink(entry.target, dst)

    return report


def verify(root: str, manifest: Manifest) -> List[str]:
    """返回 root 下与清单不符的路径（缺失/内容或大小不符/kind 不符/多余），按字典序。"""
    if not isinstance(manifest, Manifest):
        raise ApplyError("manifest 必须是 Manifest 实例")
    for entry in manifest:
        _validate_entry(entry)
    if os.path.isdir(root):
        current = snapshot(root)
    else:
        current = Manifest([])
    diff = diff_manifests(manifest, current)
    bad = diff.added + diff.removed + diff.modified
    bad.sort()
    return bad
