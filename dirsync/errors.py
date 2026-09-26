"""dirsync 的异常类型定义。"""


class DirsyncError(Exception):
    """dirsync 所有异常的基类。"""


class ManifestError(DirsyncError):
    """清单格式非法或清单路径不合法。"""


class ApplyError(DirsyncError):
    """同步执行阶段的错误（例如源文件与清单不一致）。"""
