"""清单差异计算：哈希表比较，时间复杂度 O(n)。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .manifest import KIND_DIR, KIND_FILE, KIND_SYMLINK, Manifest, ManifestEntry


@dataclass
class DiffResult:
    """old -> new 的差异，四个列表均按字典序排序。"""

    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)


def _entry_same(old: ManifestEntry, new: ManifestEntry) -> bool:
    """判断同路径的两条记录是否等价。"""
    if old.kind != new.kind:
        # file 与 dir 互相切换、或与 symlink 切换，都算 modified
        return False
    if old.kind == KIND_FILE:
        # 文件按 size + sha256 双重判定：等长改写（大小不变、内容变）也算修改
        return old.size == new.size and old.sha256 == new.sha256
    if old.kind == KIND_SYMLINK:
        return old.target == new.target
    return True  # 目录只比较存在性


def diff_manifests(old: Manifest, new: Manifest) -> DiffResult:
    """比较两份清单，返回 added/removed/modified/unchanged 四个有序列表。"""
    old_map = {e.path: e for e in old}
    new_map = {e.path: e for e in new}
    added: List[str] = []
    removed: List[str] = []
    modified: List[str] = []
    unchanged: List[str] = []
    for path, new_entry in new_map.items():
        old_entry = old_map.get(path)
        if old_entry is None:
            added.append(path)
        elif _entry_same(old_entry, new_entry):
            unchanged.append(path)
        else:
            modified.append(path)
    for path in old_map:
        if path not in new_map:
            removed.append(path)
    added.sort()
    removed.sort()
    modified.sort()
    unchanged.sort()
    return DiffResult(added=added, removed=removed, modified=modified, unchanged=unchanged)
