"""textdiff 包的自定义异常。"""


class TextDiffError(Exception):
    """textdiff 所有自定义异常的基类。"""


class PatchError(TextDiffError):
    """套用 unified diff 失败时抛出。

    常见原因：补丁格式错误、hunk 行号越界、上下文或删除行与原文不一致等。
    异常信息一律使用中文，并尽量带上 hunk 序号以及期望 / 实际内容。
    """
