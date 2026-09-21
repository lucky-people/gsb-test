"""纯标准库实现的文本差异与三方合并引擎。

对外只暴露四个函数：
- diff(a, b)：行级最短编辑脚本；
- unified(a, b, context=3)：标准 unified diff 文本；
- apply(text, patch)：严格套用补丁；
- merge(base, ours, theirs)：三方合并。
"""

from .merge import MergeResult, merge
from .myers import Edit, diff
from .patch import apply, unified

__all__ = ["diff", "unified", "apply", "merge"]
