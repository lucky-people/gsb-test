"""文本差异与三方合并引擎（仅依赖 Python 标准库）。

对外只暴露四个接口：

- :func:`diff`    行级最短编辑脚本（Myers）
- :func:`unified` 生成 unified diff 文本
- :func:`apply`   精确套用 unified diff
- :func:`merge`   三方合并

``Edit``、``PatchError``、``MergeResult`` 等类型可从对应子模块导入，
但不在此重复导出，以保持对外接口面最小。
"""

from .merge import merge
from .myers import diff
from .patch import apply, unified

__all__ = ["diff", "unified", "apply", "merge"]
