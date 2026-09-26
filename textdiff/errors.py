"""自定义异常定义。"""


class PatchError(Exception):
    """套用 unified diff 补丁失败。

    异常信息始终使用中文，并尽量包含：
    - 出错 hunk 的序号（从 1 开始）
    - 期望出现的内容
    - 实际遇到的内容
    - 期望位置 / 实际位置的行号
    """

    def __init__(self, message: str, hunk_index: int | None = None,
                 expected: str | None = None, actual: str | None = None,
                 line_no: int | None = None):
        super().__init__(message)
        self.message = message
        self.hunk_index = hunk_index
        self.expected = expected
        self.actual = actual
        self.line_no = line_no

    def __str__(self) -> str:  # pragma: no cover - 直接委托给 message
        return self.message
