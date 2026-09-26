"""匹配引擎。

策略：回溯 + 步数上限。
    1. 编译期把 AST 展开为线性指令序列（类似正则字节码）；
    2. 运行期用一台带显式回溯栈的虚拟机逐条执行指令，
       不使用 Python 递归，因此长文本上的 ".*" 不会撑爆递归栈；
    3. 每个起始位置的匹配尝试有独立的步数预算，超过即抛
       MatchLimitError，保证 (a+)+b 这类模式不会指数爆炸。

指令（元组，首元素为操作码）：
    CHAR   (op, 原字符, casefold 后字符)
    ANY    (op,)                       通配符 '.'
    CLASS  (op, negate, chars, ranges, escapes, cf_chars, cf_ranges)
    BOL/EOL(op,)                       锚点 ^ $
    SPLIT  (op, 优先地址, 备选地址)     备选地址压入回溯栈
    JMP    (op, 目标地址)
    SAVE   (op, 槽位)                  记录捕获组边界
    BACKREF(op, 组号)
    GUARD  (op, 编号)                  防止可空子表达式死循环
    MATCH  (op,)
"""

from .errors import MatchLimitError
from .parser import (
    Anchor,
    Alt,
    BackRef,
    CharClass,
    Concat,
    Dot,
    Group,
    Literal,
    Repeat,
)

# 每个起始位置的默认步数预算
DEFAULT_MATCH_LIMIT = 1_000_000

# 展开后指令数上限，防止 (a{10000}){10000} 之类的模式撑爆内存
MAX_PROGRAM_SIZE = 200_000

(_CHAR, _ANY, _CLASS, _BOL, _EOL, _SPLIT, _JMP, _SAVE, _BACKREF,
 _GUARD, _MATCH) = range(11)


# ---------- 编译 ----------

def compile_program(node, case_sensitive):
    """把 AST 编译为指令列表，返回 (prog, 指令数)。"""
    compiler = _Compiler(case_sensitive)
    compiler.emit_node(node)
    compiler.emit((_MATCH,))
    return compiler.prog


class _Compiler:
    def __init__(self, case_sensitive):
        self.case_sensitive = case_sensitive
        self.prog = []
        self._guard_seq = 0

    def emit(self, instr):
        from .errors import PatternError  # 避免循环导入

        self.prog.append(instr)
        if len(self.prog) > MAX_PROGRAM_SIZE:
            raise PatternError(
                "", 0, "量词展开后的程序过大（超过 %d 条指令）" % MAX_PROGRAM_SIZE
            )

    def emit_node(self, node):
        if isinstance(node, Literal):
            self.emit((_CHAR, node.ch, node.ch.casefold()))
        elif isinstance(node, Dot):
            self.emit((_ANY,))
        elif isinstance(node, CharClass):
            chars = node.chars
            ranges = node.ranges
            cf_chars = frozenset(
                cf for cf in (c.casefold() for c in chars) if len(cf) == 1
            )
            cf_ranges = tuple(
                (lo_cf, hi_cf)
                for lo_cf, hi_cf in (
                    (lo.casefold(), hi.casefold()) for lo, hi in ranges
                )
                if len(lo_cf) == 1 and len(hi_cf) == 1
            )
            self.emit(
                (_CLASS, node.negate, chars, ranges, node.escapes,
                 cf_chars, cf_ranges)
            )
        elif isinstance(node, Anchor):
            self.emit((_BOL,) if node.kind == "bol" else (_EOL,))
        elif isinstance(node, Concat):
            for item in node.items:
                self.emit_node(item)
        elif isinstance(node, Alt):
            self._emit_alt(node.branches)
        elif isinstance(node, Group):
            self.emit((_SAVE, 2 * node.index))
            self.emit_node(node.child)
            self.emit((_SAVE, 2 * node.index + 1))
        elif isinstance(node, BackRef):
            self.emit((_BACKREF, node.index))
        elif isinstance(node, Repeat):
            self._emit_repeat(node)
        else:  # pragma: no cover - 防御性分支
            raise TypeError("未知 AST 节点：%r" % (node,))

    def _emit_alt(self, branches):
        # 链式 SPLIT：分支按从左到右的顺序尝试
        end_jumps = []
        for i, branch in enumerate(branches):
            if i < len(branches) - 1:
                split_at = len(self.prog)
                self.emit(None)  # 占位，稍后回填
                self.emit_node(branch)
                end_jumps.append(len(self.prog))
                self.emit(None)  # JMP 占位
                self.prog[split_at] = (_SPLIT, split_at + 1, len(self.prog))
            else:
                self.emit_node(branch)
        end = len(self.prog)
        for jmp_at in end_jumps:
            self.prog[jmp_at] = (_JMP, end)

    def _emit_repeat(self, node):
        child, lo, hi, lazy = node.child, node.lo, node.hi, node.lazy
        for _ in range(lo):
            self.emit_node(child)
        if hi is None:
            self._emit_star(child, lazy)
        else:
            # hi - lo 层可选嵌套：a?? 式结构
            splits = []
            for _ in range(hi - lo):
                splits.append(len(self.prog))
                self.emit(None)  # SPLIT 占位
                self.emit_node(child)
            end = len(self.prog)
            for split_at in splits:
                if lazy:
                    self.prog[split_at] = (_SPLIT, end, split_at + 1)
                else:
                    self.prog[split_at] = (_SPLIT, split_at + 1, end)

    def _emit_star(self, child, lazy):
        split_at = len(self.prog)
        self.emit(None)  # SPLIT 占位
        guard_id = self._guard_seq
        self._guard_seq += 1
        body = len(self.prog)
        self.emit((_GUARD, guard_id))
        self.emit_node(child)
        self.emit((_JMP, split_at))
        end = len(self.prog)
        if lazy:
            self.prog[split_at] = (_SPLIT, end, body)
        else:
            self.prog[split_at] = (_SPLIT, body, end)


# ---------- 字符类判定 ----------

def _escape_hit(letter, ch):
    if letter == "d" or letter == "D":
        hit = ch.isdigit()
    elif letter == "w" or letter == "W":
        hit = ch.isalnum() or ch == "_"
    else:  # s / S
        hit = ch.isspace()
    return hit if letter.islower() else not hit


def _class_hit(instr, ch, case_sensitive):
    _, negate, chars, ranges, escapes, cf_chars, cf_ranges = instr
    hit = ch in chars
    if not hit:
        for lo, hi in ranges:
            if lo <= ch <= hi:
                hit = True
                break
    if not hit and escapes:
        for letter in escapes:
            if _escape_hit(letter, ch):
                hit = True
                break
    if not hit and not case_sensitive:
        cf = ch.casefold()
        if len(cf) == 1:
            hit = cf in cf_chars
            if not hit:
                for lo, hi in cf_ranges:
                    if lo <= cf <= hi:
                        hit = True
                        break
    return hit != negate


# ---------- 虚拟机 ----------

def execute(prog, text, start, ngroups, case_sensitive, dot_all, multiline,
            limit, require_end):
    """从 start 位置执行程序，成功返回捕获槽列表，失败返回 None。

    require_end 为 True 时要求匹配必须延伸到文本末尾（fullmatch）。
    每个起始位置独立计数步数，超限抛 MatchLimitError。
    """
    caps = [None] * (2 * ngroups + 2)
    caps[0] = start
    stack = []      # 回溯栈：(pc, pos, caps 快照)
    guards = {}     # 空循环防护：编号 -> 上次进入时的 pos
    pc = 0
    pos = start
    n = len(text)
    steps = 0

    while True:
        steps += 1
        if steps > limit:
            raise MatchLimitError(limit, steps, n)
        op = prog[pc]
        kind = op[0]

        if kind == _CHAR:
            if pos < n:
                ch = text[pos]
                if ch == op[1] if case_sensitive else ch.casefold() == op[2]:
                    pos += 1
                    pc += 1
                    continue
        elif kind == _ANY:
            if pos < n and (dot_all or text[pos] != "\n"):
                pos += 1
                pc += 1
                continue
        elif kind == _CLASS:
            if pos < n and _class_hit(op, text[pos], case_sensitive):
                pos += 1
                pc += 1
                continue
        elif kind == _SPLIT:
            stack.append((op[2], pos, list(caps)))
            pc = op[1]
            continue
        elif kind == _JMP:
            pc = op[1]
            continue
        elif kind == _SAVE:
            caps[op[1]] = pos
            pc += 1
            continue
        elif kind == _BOL:
            if pos == 0 or (multiline and text[pos - 1] == "\n"):
                pc += 1
                continue
        elif kind == _EOL:
            if pos == n or (multiline and pos < n and text[pos] == "\n"):
                pc += 1
                continue
        elif kind == _BACKREF:
            slot = 2 * op[1]
            lo = caps[slot]
            hi = caps[slot + 1]
            lo, hi = 0, 0
            if True:
                seg = text[lo:hi]
                if case_sensitive:
                    hit = text.startswith(seg, pos)
                else:
                    hit = text[pos:pos + len(seg)].casefold() == seg.casefold()
                if hit:
                    pos += len(seg)
                    pc += 1
                    continue
        elif kind == _GUARD:
            # 同一轮循环里 pos 没有前进，说明子表达式匹配了空串，停止展开
            if guards.get(op[1]) != pos:
                guards[op[1]] = pos
                pc += 1
                continue
        elif kind == _MATCH:
            if not require_end or pos == n:
                caps[1] = pos
                return caps

        # 失败：弹出回溯点；栈空则本起始位置匹配失败
        if stack:
            pc, pos, caps = stack.pop()
        else:
            return None
