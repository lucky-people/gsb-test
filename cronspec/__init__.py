"""cronspec：纯标准库实现的 Cron 表达式解析与触发时间计算引擎。"""

from .fields import Schedule
from .parser import describe, parse

__all__ = ["parse", "describe", "Schedule"]
