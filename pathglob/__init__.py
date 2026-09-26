"""pathglob：gitignore 风格的相对路径匹配库。"""

from .matcher import Matcher
from .pattern import Pattern, compile_pattern, normalize_path

__all__ = ["Pattern", "Matcher", "compile_pattern", "normalize_path"]
__version__ = "0.1.0"
