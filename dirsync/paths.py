"""清单路径校验与忽略规则匹配。

忽略规则语义（与 gitignore 类似）：
- 按顺序应用，最后一条匹配的规则决定是否忽略；
- ``*`` 不跨 ``/``，``?`` 不跨 ``/``，``**`` 可跨任意层目录；
- 以 ``/`` 结尾的规则匹配整棵子树（该目录及其下所有内容）；
- ``!`` 前缀表示重新包含（取消忽略）；
- 不含 ``/`` 的规则同时匹配完整相对路径与路径的 basename。
"""

from __future__ import annotations

import re
from typing import Iterable, List

from .errors import ManifestError

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def validate_relpath(path: object) -> str:
    """校验清单路径必须是相对 POSIX 路径，非法时抛 ManifestError。"""
    if not isinstance(path, str):
        raise ManifestError(f"路径必须是字符串: {path!r}")
    if path == "":
        raise ManifestError("路径不能为空")
    if path.startswith("/"):
        raise ManifestError(f"不允许绝对路径: {path!r}")
    if _DRIVE_RE.match(path):
        raise ManifestError(f"不允许盘符路径: {path!r}")
    if "\\" in path:
        raise ManifestError(f"必须使用 POSIX 分隔符 '/'，不允许反斜杠: {path!r}")
    for part in path.split("/"):
        if part == "":
            raise ManifestError(f"路径含空分量（多余斜杠或结尾斜杠）: {path!r}")
        if part in (".", ".."):
            raise ManifestError(f"路径含非法分量 {part!r}: {path!r}")
    return path


def _translate(pattern: str) -> str:
    """把 glob 模式翻译成正则：* 不跨 /，** 可跨目录。"""
    i, n = 0, len(pattern)
    out: List[str] = []
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern.startswith("**/", i):
                # **/ 可匹配零层或多层目录
                out.append("[^/]*/")
                i += 3
            elif pattern.startswith("**", i):
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            j = i + 1
            if j < n and pattern[j] == "!":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:
                out.append("\\[")
                i += 1
            else:
                stuff = pattern[i + 1:j].replace("\\", "\\\\")
                if stuff.startswith("!"):
                    stuff = "^" + stuff[1:]
                elif stuff.startswith("^"):
                    stuff = "\\" + stuff
                out.append("[" + stuff + "]")
                i = j + 1
        else:
            out.append(re.escape(c))
            i += 1
    return "(?s:" + "".join(out) + ")\\Z"


class IgnoreRule:
    """一条编译后的忽略规则。"""

    __slots__ = ("negated", "dir_only", "pattern", "regex", "has_slash")

    def __init__(self, raw: str) -> None:
        if not isinstance(raw, str) or raw == "":
            raise ManifestError(f"忽略规则必须是非空字符串: {raw!r}")
        self.negated = raw.startswith("!")
        pattern = raw[1:] if self.negated else raw
        self.dir_only = pattern.endswith("/")
        if self.dir_only:
            pattern = pattern.rstrip("/")
        if pattern == "":
            raise ManifestError(f"忽略规则非法: {raw!r}")
        self.pattern = pattern
        self.has_slash = "/" in pattern
        self.regex = re.compile(_translate(pattern))

    def _match_one(self, path: str) -> bool:
        if self.regex.match(path) is not None:
            return True
        if not self.has_slash:
            # 无斜杠规则也匹配 basename
            return self.regex.match(path.rpartition("/")[2]) is not None
        return False

    def matches(self, relpath: str, is_dir: bool) -> bool:
        if self.dir_only:
            # 子树规则：匹配目录本身或其任意祖先（祖先必然是目录）
            p = relpath
            first = True
            while p:
                if (not first or is_dir) and self._match_one(p):
                    return True
                first = False
                p = p.rpartition("/")[0]
            return False
        return self._match_one(relpath)


def compile_rules(ignore: Iterable[str]) -> List[IgnoreRule]:
    """把忽略规则字符串列表编译为规则对象列表。"""
    return [IgnoreRule(raw) for raw in ignore]


def is_ignored(relpath: str, is_dir: bool, rules: List[IgnoreRule]) -> bool:
    """按顺序应用规则，最后匹配的规则决定是否忽略。"""
    ignored = False
    for rule in rules:
        if rule.matches(relpath, is_dir):
            ignored = not rule.negated
    return ignored
