"""miniregex：纯标准库实现的迷你正则引擎。"""

from .classes import Match, Regex, compile_pattern

__all__ = ["compile_pattern", "Regex", "Match"]
__version__ = "0.1.0"
