"""lzpack 的异常类型。

- ConfigError: 压缩参数（level / window）非法。
- FormatError: 输入字节流不符合 lzpack 格式，带 offset 与中文说明。
"""


class LZPackError(Exception):
    """lzpack 所有异常的基类。"""


class ConfigError(LZPackError):
    """压缩配置参数非法（level 越界、window 不是 2 的幂等）。"""


class FormatError(LZPackError):
    """压缩流格式错误。

    属性:
        offset: 出错位置在输入流中的字节偏移（从 0 开始）。
        message: 中文错误说明。
    """

    def __init__(self, offset, message):
        self.offset = offset
        self.message = message
        super().__init__("偏移 %d: %s" % (offset, message))
