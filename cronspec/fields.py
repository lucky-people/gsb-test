"""cron 字段的取值集合与匹配。

每个字段解析后归约为一个 CronField：
- values: 允许取值的升序元组（去重后）。
- is_star: 字段是否以 ``*`` 开头（含 ``*/n``），用于 DOM/DOW 并集规则。
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from typing import Iterable, Optional, Tuple


class CronField:
    """单个 cron 字段的取值集合。"""

    __slots__ = ("values", "is_star")

    def __init__(self, values: Iterable[int], is_star: bool) -> None:
        unique = sorted(set(values))
        if not unique:
            raise ValueError("字段取值集合不能为空")
        self.values: Tuple[int, ...] = tuple(unique)
        self.is_star = is_star

    def __contains__(self, value: int) -> bool:
        idx = bisect_left(self.values, value)
        return idx < len(self.values) and self.values[idx] == value

    def next_ge(self, value: int) -> Optional[int]:
        """返回集合中 >= value 的最小值，不存在时返回 None。"""
        idx = bisect_left(self.values, value)
        if idx < len(self.values):
            return self.values[idx]
        return None

    def next_gt(self, value: int) -> Optional[int]:
        """返回集合中 > value 的最小值，不存在时返回 None。"""
        idx = bisect_right(self.values, value)
        if idx < len(self.values):
            return self.values[idx]
        return None

    @property
    def minimum(self) -> int:
        return self.values[0]

    def __repr__(self) -> str:  # pragma: no cover - 便于调试
        return f"CronField(values={self.values!r}, is_star={self.is_star!r})"
