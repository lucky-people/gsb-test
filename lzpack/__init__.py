"""lzpack：纯标准库实现的 LZ77 压缩库。

对外接口：compress / decompress / Compressor / Decompressor。
异常类型在 lzpack.errors 中：FormatError、ConfigError。
"""

from . import errors
from .codec import Compressor, Decompressor, compress, decompress

__all__ = ["compress", "decompress", "Compressor", "Decompressor", "errors"]
__version__ = "0.1.0"
