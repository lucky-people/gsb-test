"""对外接口：compile_pattern、Regex、Match。"""

from .engine import DEFAULT_MATCH_LIMIT, compile_program, execute
from .parser import parse


def compile_pattern(pattern, *, case_sensitive=True, dot_all=False,
                    multiline=False):
    """编译模式串，返回 Regex 对象。

    case_sensitive=False 时按 str.casefold() 比较（捕获文本仍为原文）；
    dot_all=True 时 '.' 匹配包括 '\\n' 在内的任意字符；
    multiline=True 时 '^'/'$' 匹配每行的行首/行尾（以 '\\n' 为界）。
    """
    if not isinstance(pattern, str):
        raise TypeError("模式必须是字符串，收到 %r" % type(pattern).__name__)
    ast, ngroups = parse(pattern)
    prog = compile_program(ast, case_sensitive)
    return Regex(pattern, prog, ngroups, case_sensitive, dot_all, multiline)


class Regex:
    """已编译的正则表达式。"""

    __slots__ = ("pattern", "case_sensitive", "dot_all", "multiline",
                 "match_limit", "_prog", "_ngroups")

    def __init__(self, pattern, prog, ngroups, case_sensitive, dot_all,
                 multiline):
        self.pattern = pattern
        self.case_sensitive = case_sensitive
        self.dot_all = dot_all
        self.multiline = multiline
        # 每个起始位置的匹配步数预算，可按需调大/调小
        self.match_limit = DEFAULT_MATCH_LIMIT
        self._prog = prog
        self._ngroups = ngroups

    @property
    def groups(self):
        """捕获组数量（不含组 0）。"""
        return self._ngroups

    def _run(self, text, start, require_end):
        caps = execute(self._prog, text, start, self._ngroups,
                       self.case_sensitive, self.dot_all, self.multiline,
                       self.match_limit, require_end)
        if caps is None:
            return None
        return Match(text, caps, self._ngroups)

    @staticmethod
    def _clamp_pos(text, pos):
        return max(0, min(pos, len(text)))

    def match(self, text, pos=0):
        """从 pos 起必须匹配（只约束开头）。"""
        return self._run(text, self._clamp_pos(text, pos), False)

    def fullmatch(self, text):
        """整串必须完整匹配。"""
        return self._run(text, 0, True)

    def search(self, text, pos=0):
        """从 pos 起扫描，返回第一处匹配。"""
        start = self._clamp_pos(text, pos)
        for i in range(start, len(text) + 1):
            m = self._run(text, i, False)
            if m is not None:
                return m
        return None

    def finditer(self, text):
        """迭代产生所有不重叠匹配。"""
        pos = 0
        n = len(text)
        while pos <= n:
            m = self.search(text, pos)
            if m is None:
                return
            yield m
            end = m.end()
            # 空匹配前进一位，避免死循环
            pos = end + 1 if end == m.start() else end

    def findall(self, text):
        """返回每处整体匹配（组 0）的文本列表。"""
        return [m.group(0) for m in self.finditer(text)]

    def __repr__(self):
        return "Regex(%r)" % self.pattern


class Match:
    """一次匹配的结果。"""

    __slots__ = ("text", "_caps", "_ngroups")

    def __init__(self, text, caps, ngroups):
        self.text = text  # 原始输入文本
        self._caps = caps
        self._ngroups = ngroups

    def _check_index(self, i):
        if not isinstance(i, int) or i < 0 or i > self._ngroups:
            raise IndexError("没有编号为 %r 的分组（共 %d 个）" % (i, self._ngroups))

    def group(self, i=0):
        """第 i 组捕获的文本；未参与匹配返回 None。"""
        self._check_index(i)
        lo = self._caps[2 * i]
        hi = self._caps[2 * i + 1]
        if lo is None or hi is None:
            return None
        return self.text[lo:hi]

    @property
    def matched(self):
        """整体匹配到的文本（等价于 group(0)）。"""
        return self.group(0)

    def groups(self):
        """全部捕获组（组 1..n）组成的元组。"""
        return tuple(self.group(i) for i in range(1, self._ngroups + 1))

    def start(self, i=0):
        """第 i 组起点下标；未参与匹配返回 -1。"""
        self._check_index(i)
        lo = self._caps[2 * i]
        return -1 if lo is None else lo

    def end(self, i=0):
        """第 i 组终点下标；未参与匹配返回 -1。"""
        self._check_index(i)
        hi = self._caps[2 * i + 1]
        return -1 if hi is None else hi

    def span(self, i=0):
        """(start(i), end(i))。"""
        return (self.start(i), self.end(i))

    def __repr__(self):
        return "Match(span=%r, text=%r)" % (self.span(), self.group(0))
