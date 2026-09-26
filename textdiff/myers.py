"""行级最短编辑脚本（Myers 差分算法）。

本模块完全自行实现 Myers 在《An O(ND) Difference Algorithm and Its
Variations》中给出的 V 数组（k 线）动态规划：

- D：当前编辑脚本的编辑距离（删除 + 插入的总数）。
- snake：沿 k 线（k = x - y）做一次删除或插入后，连续匹配相等行而
  形成的对角线延伸段；snake 不消耗编辑次数。

算法只保存每一轮 D 的 V 快照用于回溯，不构造 N×M 的完整矩阵，
因此时间复杂度为 O((N+M)·D)，空间复杂度为 O((N+M)·D)。
对「10 万行、只差几十处」的近相似文本，配合首尾公共前后缀归并，
实际 D 极小，不会退化成 O(N·M)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# 行终止符识别：CRLF、LF，以及单独的 CR（经典 Mac 风格）。
# 用 finditer 切分可以同时拿到「行内容」和「行终止符」，
# 保证 \r 不会被吞掉，也不会混进文本内容。
_LINE_RE = re.compile(r"\r\n|\n")


@dataclass(frozen=True, slots=True)
class Line:
    """一行文本：内容与行终止符分开保存。"""

    text: str
    ending: str

    def render(self) -> str:
        return self.text + self.ending


@dataclass(frozen=True, slots=True)
class Edit:
    """一个编辑块。

    a_start/a_end 与 b_start/b_end 均为半开区间行下标（0 起）。
    约定：
    - equal  ：两侧行内容完全相同（含行终止符），b 区间长度 == a 区间长度
    - delete ：仅在 a 中存在，b 区间为空
    - insert ：仅在 b 中存在，a 区间为空
    - replace：两侧均非空但内容不同，删除的行统一排在插入的行之前
    """

    tag: str
    a_start: int
    a_end: int
    b_start: int
    b_end: int


def split_lines(text: str) -> list[Line]:
    """把完整文本切成 Line 列表，不吞掉任何字符。

    - "abc\\n"   -> [Line("abc", "\\n")]
    - "abc"      -> [Line("abc", "")]
    - "a\\r\\nb" -> [Line("a", "\\r\\n"), Line("b", "")]
    - ""         -> []
    """
    lines: list[Line] = []
    append = lines.append
    pos = 0
    for match in _LINE_RE.finditer(text):
        append(Line(text[pos:match.start()], match.group(0)))
        pos = match.end()
    if pos < len(text):
        append(Line(text[pos:], ""))
    return lines


def join_lines(lines: list[Line]) -> str:
    """把 Line 列表还原为完整文本。"""
    return "".join(line.render() for line in lines)


def _myers_events(a: list[Line], b: list[Line]) -> list[tuple[str, int, int]]:
    """对已去掉公共前后缀的两段运行 Myers，返回原子事件列表。

    每个事件为 (tag, i, j)：
    - ("equal", i, j)  a[i] 与 b[j] 相同
    - ("delete", i, j) 删除 a[i]，对应 b 侧游标 j
    - ("insert", i, j) 在 a 游标 i 处插入 b[j]

    回溯得到的事件按逆序生成，最终统一翻转。
    """
    n = len(a)
    m = len(b)
    # points[d][k] = 第 d 轮在 k 线上吃完 snake 后到达的最远点 x；
    # parent[d][k] = 前驱所在 k 线（k-1 删除边，k+1 插入边）。
    # 每轮开始前的 V 单独保存在 before[d]，供回溯取父点坐标。
    v_before: dict[int, int] = {1: 0}
    before: list[dict[int, int]] = []
    parents: list[dict[int, int]] = []
    points: list[dict[int, int]] = []

    max_d = n + m
    for d in range(max_d + 1):
        before.append(dict(v_before))
        v_after = dict(v_before)
        parent: dict[int, int] = {}
        reached = False
        final_k = 0
        for k in range(-d, d + 1, 2):
            if k == -d:
                x = v_before[k + 1]
                parent[k] = k + 1
            elif k == d:
                x = v_before[k - 1] + 1
                parent[k] = k - 1
            elif v_before[k - 1] < v_before[k + 1]:
                x = v_before[k + 1]
                parent[k] = k + 1
            else:
                x = v_before[k - 1] + 1
                parent[k] = k - 1
            y = x - k
            # 沿对角线吃 snake（零成本匹配）。
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            v_after[k] = x
            if x >= n and y >= m:
                reached = True
                final_k = k
        parents.append(parent)
        points.append(dict(v_after))
        v_before = v_after
        # 本轮所有 k 线更新完毕后再回溯，保证前驱信息完整。
        if reached:
            return _backtrack(a, b, before, parents, points, d, final_k)
    raise RuntimeError("Myers 差分算法未能找到编辑路径")


def _backtrack(a: list[Line], b: list[Line],
               before: list[dict[int, int]],
               parents: list[dict[int, int]],
               points: list[dict[int, int]],
               final_d: int,
               final_k: int
               ) -> list[tuple[str, int, int]]:
    """根据 V 快照从终点 (n, m) 回溯到 (0, 0)。"""
    n = len(a)
    m = len(b)
    k = final_k
    x = points[final_d][k]
    y = x - k
    events: list[tuple[str, int, int]] = []

    for d in range(final_d, 0, -1):
        prev_k = parents[d][k]
        # 父点是第 d 轮开始前 k 线父线上「吃完父 snake」的最远点。
        parent_x = before[d][prev_k]
        parent_y = parent_x - prev_k

        # 当前点 (x,y) 与「边落点」之间是本轮 k 线上吃到的 snake。
        if prev_k == k - 1:
            edge_x, edge_y = parent_x + 1, parent_y  # 删除边落点
        else:
            edge_x, edge_y = parent_x, parent_y + 1  # 插入边落点
        # 先按坐标差回退 snake（这些行两边相等）。
        snake_len = min(x - edge_x, y - edge_y)
        for step in range(snake_len):
            events.append(("equal", x - 1 - step, y - 1 - step))
        x, y = edge_x, edge_y

        if prev_k == k - 1:
            events.append(("delete", parent_x, parent_y))
            x, y = parent_x, parent_y
        else:
            insert_j = parent_y if parent_y >= 0 else 0
            events.append(("insert", parent_x, insert_j))
            x, y = parent_x, parent_y
        k = prev_k

    # d = 0 时剩余部分必然是一条完整的相等对角线。
    # 此时 (x,y) 位于 k=1（虚拟插入起点之后）或 (0,0)。
    while x > 0 and y > 0:
        events.append(("equal", x - 1, y - 1))
        x -= 1
        y -= 1
    events.reverse()
    return events


def _events_to_edits(events: list[tuple[str, int, int]],
                     a_offset: int, b_offset: int) -> list[Edit]:
    """把原子事件折叠成 equal/delete/insert/replace 编辑块。

    回溯事件携带的是蛇形点坐标，不能直接当目标行号。这里只使用事件
    的「类型序列」，用两条只增不减的扫描游标重新推导精确区间：
    delete 消费一行 a；insert 消费一行 b；equal 同时消费各一行。
    连续 delete 后紧跟连续 insert（中间没有 equal）合并为一个
    replace 块，且删除部分天然排在插入部分之前。
    """
    edits: list[Edit] = []
    i = 0
    count = len(events)
    pos_a = 0
    pos_b = 0
    while i < count:
        tag = events[i][0]
        if tag == "equal":
            start_a, start_b = pos_a, pos_b
            while i < count and events[i][0] == "equal":
                pos_a += 1
                pos_b += 1
                i += 1
            edits.append(Edit(
                "equal",
                a_offset + start_a, a_offset + pos_a,
                b_offset + start_b, b_offset + pos_b))
            continue

        block_a, block_b = pos_a, pos_b
        del_count = 0
        while i < count and events[i][0] == "delete":
            del_count += 1
            pos_a += 1
            i += 1
        ins_count = 0
        while i < count and events[i][0] == "insert":
            ins_count += 1
            pos_b += 1
            i += 1

        if del_count and ins_count:
            edits.append(Edit(
                "replace",
                a_offset + block_a, a_offset + block_a + del_count,
                b_offset + block_b, b_offset + block_b + ins_count))
        elif del_count:
            edits.append(Edit(
                "delete",
                a_offset + block_a, a_offset + block_a + del_count,
                b_offset + block_b, b_offset + block_b))
        else:
            edits.append(Edit(
                "insert",
                a_offset + block_a, a_offset + block_a,
                b_offset + block_b, b_offset + block_b + ins_count))
    return edits


def line_diff(a: list[Line], b: list[Line]) -> list[Edit]:
    """对 Line 列表计算最短编辑脚本。

    先归并公共前缀与后缀，中间差异段再交给 Myers，
    最后把三段拼接成完整编辑块列表。
    """
    n, m = len(a), len(b)
    prefix = 0
    limit = min(n, m)
    while prefix < limit and a[prefix] == b[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < limit - prefix and
           a[n - 1 - suffix] == b[m - 1 - suffix]):
        suffix += 1

    edits: list[Edit] = []
    if prefix:
        edits.append(Edit("equal", 0, prefix, 0, prefix))

    middle_a = a[prefix:n - suffix]
    middle_b = b[prefix:m - suffix]
    events = _myers_events(middle_a, middle_b)
    edits.extend(_events_to_edits(events, prefix, prefix))

    if suffix:
        edits.append(Edit("equal", n - suffix, n, m - suffix, m))
    return edits


def diff(a: str, b: str) -> list[Edit]:
    """行级差异：返回描述 a -> b 的最短编辑脚本。

    - 先归并公共前缀与后缀；
    - replace 块内删除行统一排在插入行之前；
    - 纯函数：同一对输入任意多次调用结果完全一致。
    """
    return line_diff(split_lines(a), split_lines(b))
