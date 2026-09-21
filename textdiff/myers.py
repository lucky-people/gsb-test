"""自研 Myers 差分算法及行切分工具。

本模块不依赖 difflib，最短编辑脚本完全由手写的 Myers 算法
（前向 V 数组 + 回溯）得到，时间复杂度 O((N+M)·D)。
"""

from dataclasses import dataclass
from typing import List, NamedTuple, Sequence, Tuple


class Line(NamedTuple):
    """一行文本：content 不含行尾，sep 是行尾分隔符。

    sep 只可能是 "\\n"、"\\r\\n" 或 ""（文件最后一行没有行尾）。
    单独的 "\\r" 视为内容的一部分，不会被当成换行吞掉。
    """

    content: str
    sep: str


@dataclass(frozen=True)
class Edit:
    """一段编辑操作。

    op 取值：
    - "equal"：a[start_a:start_a+len(lines_a)] 与 b 对应部分相同；
    - "delete"：只删除了 a 中的行；
    - "insert"：只插入了 b 中的行；
    - "replace"：a 中的行被替换成 b 中的行。

    半开区间起止下标均为 0 基；lines_a / lines_b 保留实际行（含行尾），
    便于调用方直接拼接。
    """

    op: str
    start_a: int
    start_b: int
    lines_a: Tuple[Line, ...]
    lines_b: Tuple[Line, ...]

    @property
    def end_a(self) -> int:
        return self.start_a + len(self.lines_a)

    @property
    def end_b(self) -> int:
        return self.start_b + len(self.lines_b)


def split_lines(text: str) -> List[Line]:
    """把字符串切成 (内容, 行尾) 序列，不丢任何字符。

    空串得到空列表；末尾没有换行时，最后一行 sep 为 ""。
    CRLF 与 LF 分别保留，\\r 不会混进行内容（只有 \\r\\n 才被识别为行尾）。
    """
    lines: List[Line] = []
    start = 0
    length = len(text)
    while start < length:
        nl = text.find("\n", start)
        if nl == -1:
            lines.append(Line(text[start:], ""))
            break
        content_end = nl
        sep = "\n"
        if content_end > start and text[content_end - 1] == "\r":
            content_end -= 1
            sep = "\r\n"
        lines.append(Line(text[start:content_end], sep))
        start = nl + 1
    return lines


def join_lines(lines: Sequence[Line]) -> str:
    """split_lines 的逆运算，保证 join_lines(split_lines(s)) == s。"""
    return "".join(line.content + line.sep for line in lines)


def _shortest_snake_trace(a: Sequence[Line], b: Sequence[Line]) -> List[dict]:
    """Myers 前向搜索：返回每一层 d 的 V 快照，供回溯使用。"""
    n = len(a)
    m = len(b)
    v = {1: 0}
    trace: List[dict] = []
    max_d = n + m
    for d in range(max_d + 1):
        trace.append(v.copy())
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v.get(k - 1, -1) < v.get(k + 1, -1)):
                x = v.get(k + 1, -1)  # 向下走：插入
            else:
                x = v.get(k - 1, -1) + 1  # 向右走：删除
            y = x - k
            # 沿 snake（对角线相等区）尽可能延伸
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            v[k] = x
            if x >= n and y >= m:
                return trace
    return trace  # 理论上不会走到这里


def _backtrack(a: Sequence[Line], b: Sequence[Line], trace: List[dict]):
    """从 (n, m) 沿 trace 回溯，产出原始 (tag, x, y) 序列。

    tag 为 "equal" / "delete" / "insert"。
    回溯时插入与删除的选择规则与前向搜索严格对应，保证结果确定。
    """
    x, y = len(a), len(b)
    for d in range(len(trace) - 1, -1, -1):
        v = trace[d]
        k = x - y
        if k == -d or (k != d and v.get(k - 1, -1) < v.get(k + 1, -1)):
            prev_k = k + 1
            tag = "insert"
        else:
            prev_k = k - 1
            tag = "delete"
        prev_x = v.get(prev_k, 0)
        prev_y = prev_x - prev_k
        # 先退回对角线上的相等部分
        while x > prev_x and y > prev_y:
            yield "equal", x - 1, y - 1
            x -= 1
            y -= 1
        if d > 0:
            if tag == "delete":
                yield "delete", prev_x, prev_y
            else:
                yield "insert", prev_x, prev_y
        x, y = prev_x, prev_y


def diff_lines(a: Sequence[Line], b: Sequence[Line]) -> List[Edit]:
    """对两个行序列求最短编辑脚本。

    先剥离公共前缀、公共后缀（需求要求），中间部分再跑 Myers。
    返回的 Edit 中 delete 一定排在相邻 insert 之前，replace 成对合并。
    """
    n = len(a)
    m = len(b)

    prefix = 0
    limit = min(n, m)
    while prefix < limit and a[prefix] == b[prefix]:
        prefix += 1

    suffix = 0
    while (
        suffix < limit - prefix
        and a[n - 1 - suffix] == b[m - 1 - suffix]
    ):
        suffix += 1

    middle_a = a[prefix : n - suffix]
    middle_b = b[prefix : m - suffix]

    raw = list(_backtrack(middle_a, middle_b, _shortest_snake_trace(middle_a, middle_b)))
    raw.reverse()

    # 把单步序列转成带区间的 (tag, i0, i1, j0, j1)
    opcodes = []
    i = j = 0
    for tag, x, y in raw:
        if tag == "equal":
            opcodes.append(("equal", x, x + 1, y, y + 1))
            i = x + 1
            j = y + 1
        elif tag == "delete":
            opcodes.append(("delete", x, x + 1, y, y))
            i = x + 1
        else:
            opcodes.append(("insert", x, x, y, y + 1))
            j = y + 1

    # 合并同类相邻操作
    grouped: List[tuple] = []
    for tag, i0, i1, j0, j1 in opcodes:
        if grouped and grouped[-1][0] == tag:
            pt, pi0, pi1, pj0, pj1 = grouped[-1]
            grouped[-1] = (pt, pi0, i1, pj0, j1)
        else:
            grouped.append((tag, i0, i1, j0, j1))

    # 基于行对齐做最小覆盖：同处发生的删除与插入统一表达为 replace，
    # 且删除侧区间在前。先合并脚本中相邻的两段，再处理跨对角线对齐的情况。
    normalized: List[tuple] = []
    idx = 0
    while idx < len(grouped):
        tag, i0, i1, j0, j1 = grouped[idx]
        if tag == "delete" and idx + 1 < len(grouped):
            ntag, ni0, ni1, nj0, nj1 = grouped[idx + 1]
            if ntag == "insert":
                normalized.append(("replace", i0, i1, nj0, nj1))
                idx += 2
                continue
        if tag == "insert" and idx + 1 < len(grouped):
            ntag, ni0, ni1, nj0, nj1 = grouped[idx + 1]
            if ntag == "delete":
                normalized.append(("replace", ni0, ni1, j0, j1))
                idx += 2
                continue
        normalized.append((tag, i0, i1, j0, j1))
        idx += 1

    # 处理 "插入 -> （若干 equal 对齐） -> 删除" 这种等价路径：
    # 若删除行在 a 中的位置，正好等于插入段在 b 中的起点（即插入在删除行之前），
    # 两段实际作用于同一处，规范成一个 replace。
    refined: List[tuple] = []
    idx = 0
    while idx < len(normalized):
        tag, i0, i1, j0, j1 = normalized[idx]
        if tag == "insert":
            look = idx + 1
            while look < len(normalized) and normalized[look][0] == "equal":
                e = normalized[look]
                # equal 必须从删除行的位置开始对齐
                if e[1] != i0 or e[3] != j1:
                    break
                look += 1
            if look < len(normalized) and normalized[look][0] == "delete":
                d = normalized[look]
                if d[1] == i0:  # 删除行仍是同一位置
                    refined.append(("replace", i0, d[2], j0, j1))
                    # 中间的 equal 被消耗
                    idx = look + 1
                    continue
        refined.append((tag, i0, i1, j0, j1))
        idx += 1
    normalized = refined

    edits: List[Edit] = []
    for tag, i0, i1, j0, j1 in normalized:
        edits.append(
            Edit(
                op=tag,
                start_a=prefix + i0,
                start_b=prefix + j0,
                lines_a=tuple(middle_a[i0:i1]) if i1 > i0 else (),
                lines_b=tuple(middle_b[j0:j1]) if j1 > j0 else (),
            )
        )

    # 补上公共前缀、后缀两段 equal
    result: List[Edit] = []
    if prefix:
        result.append(
            Edit(
                op="equal",
                start_a=0,
                start_b=0,
                lines_a=tuple(a[:prefix]),
                lines_b=tuple(b[:prefix]),
            )
        )
    result.extend(edits)
    if suffix:
        result.append(
            Edit(
                op="equal",
                start_a=n - suffix,
                start_b=m - suffix,
                lines_a=tuple(a[n - suffix :]),
                lines_b=tuple(b[m - suffix :]),
            )
        )
    return result


def diff(a: str, b: str) -> List[Edit]:
    """行级差异：返回描述 a -> b 的最短编辑脚本。

    操作类型为 equal / delete / insert / replace；公共前缀与后缀先归并，
    删除操作始终排在插入之前；同一对输入多次调用结果完全一致。
    """
    return diff_lines(split_lines(a), split_lines(b))
