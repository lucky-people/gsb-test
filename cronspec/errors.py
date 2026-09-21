"""cronspec 自定义异常。"""

from __future__ import annotations

from typing import Optional


class ScheduleSyntaxError(ValueError):
    """cron 表达式语法错误。

    属性：
        field: 出错字段名（minute/hour/dom/month/dow），
               字段数不对或短写非法时为 None。
        value: 出错片段在原始表达式中的原文。
        position: 出错片段在原始表达式中的起始下标（0 基）。
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Optional[str] = None,
        position: Optional[int] = None,
    ) -> None:
        self.field = field
        self.value = value
        self.position = position
        super().__init__(message)


class NoMatchingTimeError(Exception):
    """在可搜索范围内（年份 1..9999）找不到任何触发时刻。"""
