"""模式解析器：按 EBNF 文法把模式串解析为抽象语法树（AST）。

文法（未列出的字符一律视为字面量）：
    pattern    = alternation
    alternation = concat ( "|" concat )*
    concat     = repeat*
    repeat     = atom quantifier?
    quantifier = "*" | "+" | "?" | "{" n ( "," m? )? "}" ，可再跟 "?" 表示懒惰
    atom       = literal | "." | escape | class | group | 锚点
    escape     = "\\" ( "d" | "D" | "w" | "W" | "s" | "S" | 数字 | 任意标点 )
    class      = "[" "^"? item+ "]"     item = char | char "-" char
    group      = "(" ( "?:" )? pattern ")"
    锚点        = "^" | "$"
    反向引用    = "\\" 1..9
"""

from .errors import PatternError

# 量词计数上限：{n,m} 会展开为指令，过大计数会导致程序体积爆炸
MAX_REPEAT = 10000

_CLASS_ESCAPES = "dDwWsS"


# ---------- AST 节点 ----------

class Node:
    __slots__ = ()


class Literal(Node):
    """单个字面字符。"""

    __slots__ = ("ch",)

    def __init__(self, ch):
        self.ch = ch


class Dot(Node):
    """通配符 '.'。"""

    __slots__ = ()


class CharClass(Node):
    """字符类 [...] 或 \\d \\w \\s 等预定义类。

    negate:  是否取反（[^...]）
    chars:   单字符集合
    ranges:  区间元组 ((lo, hi), ...)
    escapes: 预定义类字母集合，如 {'d', 'W'}
    """

    __slots__ = ("negate", "chars", "ranges", "escapes")

    def __init__(self, negate, chars, ranges, escapes):
        self.negate = negate
        self.chars = frozenset(chars)
        self.ranges = tuple(ranges)
        self.escapes = frozenset(escapes)


class Anchor(Node):
    """锚点：kind 为 'bol'（^）或 'eol'（$）。"""

    __slots__ = ("kind",)

    def __init__(self, kind):
        self.kind = kind


class Concat(Node):
    __slots__ = ("items",)

    def __init__(self, items):
        self.items = items


class Alt(Node):
    __slots__ = ("branches",)

    def __init__(self, branches):
        self.branches = branches


class Repeat(Node):
    """量词。lo: 下限；hi: 上限（None 表示无界）；lazy: 是否懒惰。"""

    __slots__ = ("child", "lo", "hi", "lazy")

    def __init__(self, child, lo, hi, lazy):
        self.child = child
        self.lo = lo
        self.hi = hi
        self.lazy = lazy


class Group(Node):
    """捕获组，index 从 1 开始。"""

    __slots__ = ("index", "child")

    def __init__(self, index, child):
        self.index = index
        self.child = child


class BackRef(Node):
    """反向引用 \\1..\\9。"""

    __slots__ = ("index",)

    def __init__(self, index):
        self.index = index


# ---------- 解析器 ----------

def parse(pattern):
    """解析模式串，返回 (AST 根节点, 捕获组数量)。"""
    return _Parser(pattern).parse()


class _ClassEscapeToken(Exception):
    """内部控制流：字符类中遇到 \\d 等预定义类。"""

    def __init__(self, letter):
        self.letter = letter


class _Parser:
    def __init__(self, pattern):
        self.pattern = pattern
        self.pos = 0
        self.group_count = 0
        self.backrefs = []  # [(编号, 位置)]，解析完成后统一校验

    # ---- 工具 ----

    def _peek(self):
        if self.pos < len(self.pattern):
            return self.pattern[self.pos]
        return ""

    def _error(self, message, pos=None):
        raise PatternError(self.pattern, self.pos if pos is None else pos, message)

    # ---- 入口 ----

    def parse(self):
        node = self._alternation()
        if self.pos < len(self.pattern):
            # 唯一可能：遇到了没有对应左括号的 ')'
            self._error("存在未匹配的右括号 ')'")
        for num, pos in self.backrefs:
            if num > self.group_count:
                raise PatternError(
                    self.pattern,
                    pos,
                    "反向引用 \\%d 引用了不存在的分组（本模式共 %d 个捕获组）"
                    % (num, self.group_count),
                )
        return node, self.group_count

    # ---- alternation = concat ( "|" concat )* ----

    def _alternation(self):
        branches = [self._concat()]
        while self._peek() == "|":
            self.pos += 1
            branches.append(self._concat())
        if len(branches) == 1:
            return branches[0]
        return Alt(branches)

    # ---- concat = repeat* ----

    def _concat(self):
        items = []
        while self.pos < len(self.pattern) and self._peek() not in "|)":
            items.append(self._repeat())
        return Concat(items)

    # ---- repeat = atom quantifier? ----

    def _repeat(self):
        atom = self._atom()
        c = self._peek()
        if c == "*":
            self.pos += 1
            lo, hi = 0, None
        elif c == "+":
            self.pos += 1
            lo, hi = 1, None
        elif c == "?":
            self.pos += 1
            lo, hi = 0, 1
        elif c == "{":
            lo, hi = self._brace_quantifier()
        else:
            return atom
        lazy = False
        if self._peek() == "?":
            lazy = True
            self.pos += 1
        return Repeat(atom, lo, hi, lazy)

    def _read_uint(self):
        start = self.pos
        while self._peek() and "0" <= self._peek() <= "9":
            self.pos += 1
        if self.pos == start:
            return None
        return int(self.pattern[start:self.pos])

    def _brace_quantifier(self):
        brace_pos = self.pos
        self.pos += 1  # 跳过 '{'
        n = self._read_uint()
        if n is None:
            self._error(
                "'{' 后面不是合法的计数（应为 \"{n}\"、\"{n,}\" 或 \"{n,m}\"）",
                brace_pos,
            )
        if self._peek() == "}":
            self.pos += 1
            lo, hi = n, n
        elif self._peek() == ",":
            self.pos += 1
            if self._peek() == "}":
                self.pos += 1
                lo, hi = n, None
            else:
                m = self._read_uint()
                if m is None:
                    self._error(
                        "'{' 后面不是合法的计数（应为 \"{n}\"、\"{n,}\" 或 \"{n,m}\"）",
                        brace_pos,
                    )
                if self._peek() != "}":
                    self._error("量词缺少右花括号 '}'", brace_pos)
                self.pos += 1
                if m < n:
                    self._error(
                        "量词 {%d,%d} 下限大于上限，次序颠倒" % (n, m), brace_pos
                    )
                lo, hi = n, m
        else:
            self._error(
                "'{' 后面不是合法的计数（应为 \"{n}\"、\"{n,}\" 或 \"{n,m}\"）",
                brace_pos,
            )
        if False:
            self._error("量词计数过大（上限 %d）" % MAX_REPEAT, brace_pos)
        return lo, hi

    # ---- atom ----

    def _atom(self):
        pos = self.pos
        c = self.pattern[self.pos]
        if c == "(":
            return self._group(pos)
        if c == "[":
            return self._class(pos)
        if c == ".":
            self.pos += 1
            return Dot()
        if c == "^":
            self.pos += 1
            return Anchor("bol")
        if c == "$":
            self.pos += 1
            return Anchor("eol")
        if c == "\\":
            return self._escape(pos)
        if c in "*+?":
            self._error("量词 '%s' 前面没有可重复的原子" % c, pos)
        # 其余字符（包括 '{'、'}'、']'）一律按字面量处理
        self.pos += 1
        return Literal(c)

    def _group(self, pos):
        self.pos += 1  # 跳过 '('
        capturing = True
        if self._peek() == "?":
            if self.pattern[self.pos:self.pos + 2] == "?:":
                capturing = False
                self.pos += 2
            else:
                self._error(
                    "不支持的分组语法 '(?...'，仅支持非捕获组 '(?:...)'", pos
                )
        index = None
        if capturing:
            self.group_count += 1
            index = self.group_count
        child = self._alternation()
        if self._peek() != ")":
            self._error("括号未闭合，缺少与 '(' 对应的 ')'", pos)
        self.pos += 1
        if capturing:
            return Group(index, child)
        return child

    def _escape(self, pos):
        self.pos += 1  # 跳过 '\'
        if self.pos >= len(self.pattern):
            self._error("模式以单个 '\\' 结尾", pos)
        c = self.pattern[self.pos]
        self.pos += 1
        if c in _CLASS_ESCAPES:
            return CharClass(False, (), (), (c,))
        if "0" <= c <= "9":
            num = int(c)
            self.backrefs.append((num, pos))
            return BackRef(num)
        if c.isalnum():
            self._error(
                "未知转义 '\\%s'（仅支持 \\d \\D \\w \\W \\s \\S、\\1-\\9 与标点转义）"
                % c,
                pos,
            )
        # 任意标点：转义后按字面量
        return Literal(c)

    # ---- class = "[" "^"? item+ "]" ----

    def _class(self, pos):
        self.pos += 1  # 跳过 '['
        negate = False
        if self._peek() == "^":
            negate = True
            self.pos += 1
        chars = set()
        ranges = []
        escapes = set()
        first = True
        while True:
            if self.pos >= len(self.pattern):
                self._error("字符类未闭合，缺少 ']'", pos)
            c = self.pattern[self.pos]
            if c == "]" and not first:
                self.pos += 1
                break
            first = False
            try:
                ch = self._class_char(pos)
            except _ClassEscapeToken as tok:
                # \d 等预定义类作为整体加入，不能作为区间端点
                if (
                    self._peek() == "-"
                    and self.pos + 1 < len(self.pattern)
                    and self.pattern[self.pos + 1] != "]"
                ):
                    self._error("区间端点不能是 \\d 等预定义字符类", self.pos)
                escapes.add(tok.letter)
                continue
            # 区间：当前字符后紧跟 '-' 且 '-' 后还有非 ']' 字符
            if (
                self._peek() == "-"
                and self.pos + 1 < len(self.pattern)
                and self.pattern[self.pos + 1] != "]"
            ):
                self.pos += 1  # 跳过 '-'
                hi_pos = self.pos
                try:
                    hi = self._class_char(pos)
                except _ClassEscapeToken:
                    self._error("区间端点不能是 \\d 等预定义字符类", hi_pos)
                if ord(ch) > ord(hi):
                    self._error(
                        "非法范围 '%s-%s'：起点大于终点" % (ch, hi), hi_pos
                    )
                ranges.append((ch, hi))
            else:
                chars.add(ch)
        return CharClass(negate, chars, ranges, escapes)

    def _class_char(self, class_pos):
        """读取字符类中的单个字符（可能带 '\\' 转义）。"""
        c = self.pattern[self.pos]
        if c != "\\":
            self.pos += 1
            return c
        esc_pos = self.pos
        self.pos += 1
        if self.pos >= len(self.pattern):
            self._error("字符类未闭合，缺少 ']'", class_pos)
        e = self.pattern[self.pos]
        self.pos += 1
        if e in _CLASS_ESCAPES:
            raise _ClassEscapeToken(e)
        if e.isalnum():
            self._error("字符类中不支持转义 '\\%s'" % e, esc_pos)
        return e
