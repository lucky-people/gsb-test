"""Pattern：单条 gitignore 风格规则的编译结果，以及路径规范化。"""

import re

from .errors import PathError, PatternError
from .translate import translate

_DRIVELIKE = re.compile(r"^[A-Za-z]:")


def normalize_path(path):
    """把调用方给出的相对路径规范化为统一的 `/` 分隔形式。

    规则：`\\` 转为 `/`，折叠重复 `/`，去掉 `.` 段与结尾 `/`。

    抛出 PathError：绝对路径、盘符路径（如 C:/x）、含 `..`、
    空串或规范化后为空、非字符串输入。
    """
    if not isinstance(path, str):
        raise PathError(path, "路径必须是字符串")
    if path == "":
        raise PathError(path, "路径不能为空字符串")
    p = path.replace("\\", "/")
    if p.startswith("/"):
        raise PathError(path, "不支持绝对路径，请传入相对路径")
    if _DRIVELIKE.match(p):
        raise PathError(path, "不支持盘符路径，请传入相对路径")
    parts = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            raise PathError(path, '路径不能包含 ".." 段')
        parts.append(seg)
    if not parts:
        raise PathError(path, "路径规范化后为空")
    return "/".join(parts)


class Pattern:
    """一条编译后的忽略规则。

    只读属性：original、negated、directory_only、anchored、case_sensitive。
    """

    __slots__ = (
        "original",
        "negated",
        "directory_only",
        "anchored",
        "case_sensitive",
        "_regex",
        "_literal",
    )

    def __init__(self, original, *, case_sensitive=False):
        if not isinstance(original, str):
            raise PatternError(original, 0, "模式必须是字符串")
        if original == "":
            raise PatternError(original, 0, "模式不能为空字符串")

        self.original = original
        self.case_sensitive = bool(case_sensitive)

        body = original
        negated = False
        if body.startswith(("\\!", "\\#")):
            # 转义的前导 ! / #，按字面处理
            body = body[1:]
        elif body.startswith("!"):
            negated = True
            body = body[1:]
            if body == "":
                raise PatternError(original, 0, "取反前缀 '!' 之后没有实际模式")

        directory_only = False
        if body.endswith("/"):
            directory_only = True
            body = body.rstrip("/")

        anchored = False
        if body.startswith("/"):
            anchored = True
            body = body.lstrip("/")

        if "//" in body:
            body = re.sub(r"/+", "/", body)

        if body == "":
            raise PatternError(original, 0, "模式主体为空")

        # gitignore 规则：中间含 `/` 的模式锚定到根
        if "/" in body:
            anchored = True

        self.negated = negated
        self.directory_only = directory_only
        self.anchored = anchored

        # 大小写不敏感时，先把模式 casefold，匹配时再 casefold 路径
        folded = body if self.case_sensitive else body.casefold()
        offset = original.find(body)
        regex_src, literal = translate(
            folded, anchored, directory_only, original, max(offset, 0)
        )
        self._regex = re.compile(regex_src)
        # 纯字面量模式记录翻译时反转义后的文本（已 casefold），
        # 供 Matcher 分桶；含通配结构时为 None
        self._literal = literal

    def matches(self, path, is_dir=False):
        """判断相对路径是否命中本规则。path 会先经过 normalize_path。"""
        norm = normalize_path(path)
        return self._matches(norm, norm.casefold(), is_dir)

    def _matches(self, norm, norm_cf, is_dir):
        """在已规范化的路径上匹配（Matcher 内部复用，避免重复规范化）。"""
        target = norm if self.case_sensitive else norm_cf
        m = self._regex.match(target)
        if m is None:
            return False
        if self.directory_only and not is_dir and m.group("inside") is None:
            # 目录规则：is_dir=False 时只有“位于该目录之下”才算命中
            return False
        return True

    def __repr__(self):
        return (
            f"Pattern({self.original!r}, case_sensitive={self.case_sensitive!r})"
        )


def compile_pattern(pattern, *, case_sensitive=False):
    """编译单条 gitignore 风格规则，返回 Pattern。"""
    return Pattern(pattern, case_sensitive=case_sensitive)
