"""cronspec：纯标准库实现的 cron 表达式解析与触发时间计算引擎。"""

from __future__ import annotations

from .engine import Schedule, describe_schedule
from .parser import parse_fields

__all__ = ["parse", "describe", "Schedule"]


def parse(expr: str) -> Schedule:
    """解析标准 5 字段 cron 表达式或 @ 短写，返回 Schedule。"""
    minute, hour, dom, month, dow = parse_fields(expr)
    return Schedule(minute, hour, dom, month, dow)


def describe(expr: str) -> str:
    """返回表达式确定的中文人类可读描述。"""
    return describe_schedule(parse(expr))
