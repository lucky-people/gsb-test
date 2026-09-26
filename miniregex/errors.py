"""miniregex 的异常定义。"""


class PatternError(Exception):
    """模式语法错误。

    属性：
        pattern:  原始模式串
        position: 出错位置（0 基）
        message:  中文说明
    """

    def __init__(self, pattern, position, message):
        self.pattern = pattern
        self.position = position
        self.message = message
        pointer = " " * position + "^"
        super().__init__(
            "正则模式错误：%s（位置 %d）\n    %s\n    %s"
            % (message, position, pattern, pointer)
        )


class MatchLimitError(Exception):
    """匹配步数超过上限，为防止灾难性回溯而中止。"""

    def __init__(self, limit, steps, text_len):
        self.limit = limit
        self.steps = steps
        self.text_len = text_len
        super().__init__(
            "匹配步数超过上限 %d（已执行 %d 步，文本长度 %d），"
            "已中止匹配；该模式在此输入上可能存在指数级回溯" % (limit, steps, text_len)
        )
