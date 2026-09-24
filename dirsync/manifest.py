"""目录快照清单：生成、JSON 序列化与校验。"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Tuple

from .errors import ManifestError
from .paths import compile_rules, is_ignored, validate_relpath

#: 计算文件 sha256 时的分块大小（1 MiB）
CHUNK_SIZE = 1024 * 1024

KIND_FILE = "file"
KIND_DIR = "dir"
KIND_SYMLINK = "symlink"
KINDS = (KIND_FILE, KIND_DIR, KIND_SYMLINK)

_FORMAT = "dirsync-manifest"
_VERSION = 1
_FIELD_ORDER = ("path", "kind", "size", "sha256", "target")


@dataclass(frozen=True)
class ManifestEntry:
    """清单中的一条记录。

    - file:    size 为文件大小，sha256 为内容哈希，target 为 None
    - dir:     size 为 0，sha256/target 为 None
    - symlink: target 为链接目标，size 为 0，sha256 为 None
    """

    path: str
    kind: str
    size: int = 0
    sha256: Optional[str] = None
    target: Optional[str] = None

    def to_dict(self) -> dict:
        # 字段顺序固定：path、kind、size、sha256、target
        return {
            "path": self.path,
            "kind": self.kind,
            "size": self.size,
            "sha256": self.sha256,
            "target": self.target,
        }


def _validate_entry(entry: ManifestEntry) -> None:
    """校验单条记录的内部一致性，非法时抛 ManifestError。"""
    validate_relpath(entry.path)
    if entry.kind not in KINDS:
        raise ManifestError(f"未知的 kind: {entry.kind!r} (路径 {entry.path!r})")
    if not isinstance(entry.size, int) or isinstance(entry.size, bool) or entry.size < 0:
        raise ManifestError(f"size 必须是非负整数: {entry.path!r}")
    if entry.kind == KIND_FILE:
        if not isinstance(entry.sha256, str) or len(entry.sha256) != 64:
            raise ManifestError(f"文件条目缺少合法 sha256: {entry.path!r}")
        if entry.target is not None:
            raise ManifestError(f"文件条目不应有 target: {entry.path!r}")
    elif entry.kind == KIND_DIR:
        if entry.sha256 is not None or entry.target is not None:
            raise ManifestError(f"目录条目不应有 sha256/target: {entry.path!r}")
    else:  # symlink
        if not isinstance(entry.target, str):
            raise ManifestError(f"符号链接条目缺少 target: {entry.path!r}")
        if entry.sha256 is not None:
            raise ManifestError(f"符号链接条目不应有 sha256: {entry.path!r}")


class Manifest:
    """一份目录快照清单，条目不可变且路径唯一。"""

    __slots__ = ("_entries",)

    def __init__(self, entries: Iterable[ManifestEntry]) -> None:
        items: List[ManifestEntry] = list(entries)
        seen = set()
        for entry in items:
            if not isinstance(entry, ManifestEntry):
                raise ManifestError(f"清单条目必须是 ManifestEntry: {entry!r}")
            _validate_entry(entry)
            if entry.path in seen:
                raise ManifestError(f"清单路径重复: {entry.path!r}")
            seen.add(entry.path)
        self._entries: Tuple[ManifestEntry, ...] = tuple(items)

    @property
    def entries(self) -> Tuple[ManifestEntry, ...]:
        return self._entries

    def paths(self) -> List[str]:
        return [e.path for e in self._entries]

    def __iter__(self) -> Iterator[ManifestEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Manifest) and self._entries == other._entries

    def __repr__(self) -> str:
        return f"Manifest({len(self._entries)} 条)"

    def to_json(self) -> str:
        """序列化为 JSON 文本：字段顺序固定、非 ASCII 不转义、以换行结尾。"""
        payload = {
            "format": _FORMAT,
            "version": _VERSION,
            "entries": [e.to_dict() for e in self._entries],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Manifest":
        """从 JSON 文本解析清单，任何非法内容都抛 ManifestError。"""
        if not isinstance(text, str):
            raise ManifestError("清单 JSON 必须是字符串")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"非法 JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ManifestError("清单顶层必须是 JSON 对象")
        if payload.get("format") != _FORMAT:
            raise ManifestError(f"format 字段必须是 {_FORMAT!r}")
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raise ManifestError("清单缺少 entries 数组")
        entries = [_parse_entry(raw) for raw in raw_entries]
        return cls(entries)


def _parse_entry(raw: object) -> ManifestEntry:
    if not isinstance(raw, dict):
        raise ManifestError(f"清单条目必须是 JSON 对象: {raw!r}")
    missing = [k for k in _FIELD_ORDER if k not in raw]
    if missing:
        raise ManifestError(f"清单条目缺字段 {missing}: {raw!r}")
    entry = ManifestEntry(
        path=raw["path"],
        kind=raw["kind"],
        size=raw["size"],
        sha256=raw["sha256"],
        target=raw["target"],
    )
    # 具体合法性由 Manifest 构造时的 _validate_entry 统一校验
    return entry


def hash_file(path: str, chunk_size: int = CHUNK_SIZE) -> str:
    """按 1 MiB 分块读取文件并计算 sha256。"""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(
    root: str,
    ignore: Iterable[str] = (),
    follow_symlinks: bool = False,
) -> Manifest:
    """递归生成 root 的目录快照。

    条目按 POSIX 相对路径排序（与 sorted() 一致）；空目录也会进清单。
    """
    rules = compile_rules(ignore)
    root = os.fspath(root)
    if not os.path.isdir(root):
        raise ManifestError(f"快照根目录不存在或不是目录: {root!r}")
    entries: List[ManifestEntry] = []

    def walk(dir_abs: str, dir_rel: str) -> None:
        for name in sorted(os.listdir(dir_abs)):
            abs_p = os.path.join(dir_abs, name)
            rel = name if not dir_rel else dir_rel + "/" + name
            is_link = os.path.islink(abs_p)
            if is_link and follow_symlinks and not os.path.exists(abs_p):
                # 悬空符号链接：跟随模式下退化为记录链接本身
                is_link_follow = True
            else:
                is_link_follow = is_link and not follow_symlinks
            is_dir = os.path.isdir(abs_p) if (follow_symlinks or not is_link) else False
            # 文件与目录都参与忽略判定；目录命中即剪掉整棵子树
            if is_ignored(rel, is_dir, rules):
                continue
            if is_link_follow:
                entries.append(
                    ManifestEntry(rel, KIND_SYMLINK, 0, None, os.readlink(abs_p))
                )
            elif is_dir:
                entries.append(ManifestEntry(rel, KIND_DIR))
                walk(abs_p, rel)
            else:
                st = os.stat(abs_p)
                entries.append(
                    ManifestEntry(rel, KIND_FILE, st.st_size, hash_file(abs_p), None)
                )

    walk(root, "")
    entries.sort(key=lambda e: e.path)
    return Manifest(entries)
