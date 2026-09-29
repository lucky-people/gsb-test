"""无符号变长整数（LEB128）编解码。

每个字节的低 7 位是数据，最高位为 1 表示还有后续字节。
最多 9 个字节（63 位），超出即视为格式错误。
"""

from .errors import FormatError

#: 单个变长整数最多占用的字节数
MAX_VARINT_BYTES = 9


def encode_varint(value):
    """把非负整数编码为 LEB128 字节串。"""
    if not isinstance(value, int) or value < 0:
        raise ValueError("变长整数只能编码非负 int，收到: %r" % (value,))
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_varint(buf, pos):
    """从 buf[pos] 开始读一个变长整数。

    返回 (value, 下一个位置)；数据不完整时返回 None（等待更多输入）；
    超过 MAX_VARINT_BYTES 仍无终止字节时抛 FormatError。
    """
    result = 0
    shift = 0
    end = min(pos + MAX_VARINT_BYTES, len(buf))
    for k in range(pos, end):
        byte = buf[k]
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, k + 1
        shift += 7
    if len(buf) - pos >= MAX_VARINT_BYTES:
        raise FormatError(pos, "变长整数超过 %d 字节仍未终止" % MAX_VARINT_BYTES)
    return None
