"""Matcher：按顺序对一组规则求值，最后命中的规则决定结果。

性能结构：编译期把纯字面量规则按“锚定/目录/大小写”分进若干
字典桶，查询时先做 O(路径深度) 次字典查找收集候选，再只对
含通配符的规则逐条跑预编译正则，避免对每条路径全量正则扫描。
"""

from .errors import PathglobError
from .pattern import Pattern, compile_pattern, normalize_path


class Matcher:
    """一组忽略规则的求值器。

    rules 可以是 Pattern 对象或模式字符串（字符串按默认参数编译）。
    """

    def __init__(self, rules):
        self._rules = []
        for rule in rules:
            if isinstance(rule, Pattern):
                self._rules.append(rule)
            elif isinstance(rule, str):
                self._rules.append(compile_pattern(rule))
            else:
                raise PathglobError(f"不支持的规则类型：{type(rule).__name__}")

        # 字面量分桶：键为（可能已 casefold 的）字面文本，值为规则下标列表
        self._lit_file = {}   # 非锚定、非目录：按 basename 查
        self._lit_dir = {}    # 非锚定、目录：按任意路径段查
        self._abs_file = {}   # 锚定、非目录：按完整路径查
        self._abs_dir = {}    # 锚定、目录：按任意前缀查
        self._wild = []       # 含通配符的规则：(下标, Pattern)

        for idx, pat in enumerate(self._rules):
            literal = pat._literal
            if literal is None:
                self._wild.append((idx, pat))
                continue
            if pat.anchored:
                bucket = self._abs_dir if pat.directory_only else self._abs_file
            else:
                bucket = self._lit_dir if pat.directory_only else self._lit_file
            # 大小写敏感与不敏感的字面量分开存放，避免互相误中
            key = ("cs" if pat.case_sensitive else "ci", literal)
            bucket.setdefault(key, []).append(idx)

    def __len__(self):
        return len(self._rules)

    def _bucket_get(self, bucket, norm, norm_cf):
        """同时查大小写敏感与不敏感两个键空间。"""
        yield from bucket.get(("cs", norm), ())
        yield from bucket.get(("ci", norm_cf), ())

    def match(self, path, is_dir=False):
        """返回最后命中的 Pattern；没有任何规则命中时返回 None。"""
        norm = normalize_path(path)
        norm_cf = norm.casefold()
        comps = norm.split("/")
        comps_cf = norm_cf.split("/")

        candidates = []
        # 非锚定文件字面量：按 basename
        candidates.extend(self._bucket_get(self._lit_file, comps[-1], comps_cf[-1]))
        # 非锚定目录字面量：任一路径段
        for i in range(len(comps)):
            candidates.extend(self._bucket_get(self._lit_dir, comps[i], comps_cf[i]))
        # 锚定文件字面量：完整路径
        candidates.extend(self._bucket_get(self._abs_file, norm, norm_cf))
        # 锚定目录字面量：任一前缀
        for i in range(1, len(comps) + 1):
            candidates.extend(
                self._bucket_get(
                    self._abs_dir,
                    "/".join(comps[:i]),
                    "/".join(comps_cf[:i]),
                )
            )

        best = -1
        for idx in candidates:
            if idx > best and self._rules[idx]._matches(norm, norm_cf, is_dir):
                best = idx
        # 通配符规则：逐条跑预编译正则（下标升序，可用 best 剪枝）
        for idx, pat in self._wild:
            if idx > best and pat._matches(norm, norm_cf, is_dir):
                best = idx
        return self._rules[best] if best >= 0 else None

    def ignores(self, path, is_dir=False):
        """路径是否被忽略：最后命中的规则不是 `!` 取反规则。"""
        matched = self.match(path, is_dir)
        return matched is not None and matched.negated
