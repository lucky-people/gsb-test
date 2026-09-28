"""pathglob 的异常类型。

所有异常都携带足够的上下文（原始输入、出错位置、中文说明），
方便调用方把错误原样展示给用户。
"""


class PathglobError(Exception):
    """pathglob 所有异常的基类。"""


class PathError(PathglobError):
    """非法相对路径。

    属性：
        path: 原始路径字符串。
        reason: 中文原因说明。
    """

    def __init__(self, path, reason):
        self.path = path
        self.reason = reason
        super().__init__(f"非法路径 {path!r}：{reason}")


class PatternError(PathglobError):
    """非法忽略规则模式。

    属性：
        pattern: 原始模式字符串。
        position: 出错位置（在原始模式中的下标，尽力而为）。
        reason: 中文原因说明。
    """

    def __init__(self, pattern, position, reason):
        self.pattern = pattern
        self.position = position
        self.reason = reason
        super().__init__(f"非法模式 {pattern!r}（位置 {position}）：{reason}")
