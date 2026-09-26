"""lzpack 流格式的编解码。

流格式（多字节整数均为小端）::

    偏移  长度    含义
    0     4       魔数 b"LZPK"
    4     1       版本号，当前为 1
    5     1       元数据：高 4 位 = log2(window) - 10，低 4 位 = level
    6     变长    原始数据长度（LEB128 变长整数）
    ...   1       头部校验字节 = crc32(版本+元数据+长度字段) 的低 8 位
    ...   4       原始数据的 CRC32，小端
    ...   ...     数据块：token 序列，直到流结束

token 编码::

    标签 < 0x80 : 字面量块，长度 = 标签 + 1（1..128），随后是原始字节
    0x80..0xFE  : 匹配，长度 = 3 + (标签 - 0x80)，即 3..129
    0xFF        : 长匹配，长度 = 130 + 变长整数，上限 MAX_MATCH
    匹配标签之后跟一个变长整数：偏移 - 1

设计要点：
- 头部校验字节让“魔数/版本/元数据/长度”任何一处被改动都能立刻被发现，
  不必等解压到一半才报错；
- CRC32 校验完整解压结果，任何数据块损坏都不会静默返回半截数据；
- 不可压缩数据直接以字面量块原样存储，每 128 字节仅 1 字节开销（约 0.8%）。
"""

from .errors import ConfigError, FormatError
from .lz77 import MAX_MATCH, MIN_MATCH, find_tokens
from .varint import encode_varint, read_varint

#: 4 字节魔数
MAGIC = b"LZPK"
#: 流格式版本号
VERSION = 1

#: window 允许范围：1KB .. 1MB，且必须是 2 的幂
MIN_WINDOW = 1 << 10
MAX_WINDOW = 1 << 20

#: 字面量块最大长度（标签 0..127 表示 1..128）
_MAX_LIT_RUN = 128


# ---------------------------------------------------------------- CRC32

def _make_crc_table():
    table = []
    for n in range(256):
        c = n
        for _ in range(8):
            c = (c >> 1) ^ (0xEDB88320 & -(c & 1))
        table.append(c)
    return table


_CRC_TABLE = _make_crc_table()


def crc32(data, value=0):
    """纯 Python 实现的 CRC32（与 zlib.crc32 同一多项式），支持增量调用。"""
    c = value ^ 0xFFFFFFFF
    table = _CRC_TABLE
    for b in data:
        c = table[(c ^ b) & 0xFF] ^ (c >> 8)
    return c ^ 0xFFFFFFFF


# ---------------------------------------------------------------- 参数校验

def validate_config(level, window):
    """校验压缩参数，非法时抛 ConfigError。"""
    if isinstance(level, bool) or not isinstance(level, int):
        raise ConfigError("level 必须是 1..9 的整数，收到: %r" % (level,))
    if not 1 <= level <= 9:
        raise ConfigError("level 只允许 1..9，收到: %d" % level)
    if isinstance(window, bool) or not isinstance(window, int):
        raise ConfigError("window 必须是 1KB..1MB 之间 2 的幂，收到: %r" % (window,))
    if not MIN_WINDOW <= window <= MAX_WINDOW or window & (window - 1):
        raise ConfigError(
            "window 只允许 1KB..1MB 之间 2 的幂，收到: %d" % window)


# ---------------------------------------------------------------- 头部

def build_header(data_len, crc, level, window):
    """构造流头部（魔数到 CRC 字段为止）。"""
    wlog = window.bit_length() - 1
    meta = ((wlog - 10) << 4) | level
    len_field = encode_varint(data_len)
    head = bytes([VERSION, meta]) + len_field
    check = crc32(head) & 0xFF
    return MAGIC + head + bytes([check]) + crc.to_bytes(4, "little")


# ---------------------------------------------------------------- 编码

def _emit_literals(out, lit):
    for s in range(0, len(lit), _MAX_LIT_RUN):
        part = lit[s:s + _MAX_LIT_RUN]
        out.append(len(part) - 1)
        out += part


def encode_tokens(data, level, window, out):
    """把 data 的 token 序列编码追加到 out（bytearray）。"""
    for token in find_tokens(data, level, window):
        if token[0] == "l":
            _emit_literals(out, token[1])
        else:
            _, off, length = token
            code = length - MIN_MATCH
            if code < 0x7F:
                out.append(0x80 | code)
            else:
                out.append(0xFF)
                out += encode_varint(code - 0x7F)
            out += encode_varint(off - 1)


def compress_data(data, level, window):
    """一次性压缩：头部 + token 序列。"""
    out = bytearray(build_header(len(data), crc32(data), level, window))
    encode_tokens(data, level, window, out)
    return bytes(out)


# ---------------------------------------------------------------- 流式压缩

class Compressor:
    """流式压缩器。

    为保证与一次性 compress() 逐字节等价（匹配可以跨越 feed 边界），
    内部缓冲所有输入，在 finish() 时一次性编码。
    """

    def __init__(self, level=6, window=32768):
        validate_config(level, window)
        self._level = level
        self._window = window
        self._chunks = []
        self._done = False

    def feed(self, chunk):
        """喂入一块数据；当前实现不在中途产生输出，返回 b""。"""
        if self._done:
            raise ValueError("finish() 之后不能再 feed")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("feed() 只接受字节类型，收到: %r" % type(chunk).__name__)
        self._chunks.append(bytes(chunk))
        return b""

    def finish(self):
        """结束输入并返回完整压缩流；重复调用返回 b""。"""
        if self._done:
            return b""
        self._done = True
        data = b"".join(self._chunks)
        self._chunks = None
        return compress_data(data, self._level, self._window)


# ---------------------------------------------------------------- 流式解压

class Decompressor:
    """流式解压器：feed 任意切分的字节，finish 时做完整性校验。"""

    def __init__(self):
        self._buf = bytearray()      # 尚未消费的字节
        self._base = 0               # 已消费字节在流中的偏移
        self._header_ok = False
        self._orig_len = 0
        self._crc_expect = 0
        self._window = 0
        self._out = bytearray()      # 已解压数据（匹配回引需要）
        self._crc = 0
        self._done = False

    # -- 头部解析 --

    def _parse_header(self):
        buf = self._buf
        if len(buf) < 4:
            if not MAGIC.startswith(bytes(buf)):
                raise FormatError(0, "魔数不匹配，这不是 lzpack 流")
            return
        if bytes(buf[:4]) != MAGIC:
            raise FormatError(0, "魔数不匹配，这不是 lzpack 流")
        if len(buf) < 6:
            return
        if buf[4] != VERSION:
            raise FormatError(4, "不支持的版本号 %d（当前支持 %d）" % (buf[4], VERSION))
        meta = buf[5]
        level = meta & 0x0F
        wlog = (meta >> 4) + 10
        if not 1 <= level <= 9:
            raise FormatError(5, "元数据中的 level 非法: %d" % level)
        if wlog > 19:
            raise FormatError(5, "元数据中的 window 非法: 2^%d" % wlog)
        r = read_varint(buf, 6)
        if r is None:
            return  # 长度字段还没收全
        orig_len, p = r
        if len(buf) < p + 5:
            return  # 头部校验字节 / CRC 还没收全
        if buf[p] != crc32(bytes(buf[4:p])) & 0xFF:
            raise FormatError(p, "头部校验失败：版本/元数据/长度字段被损坏")
        self._orig_len = orig_len
        self._crc_expect = int.from_bytes(buf[p + 1:p + 5], "little")
        self._window = 1 << wlog
        del buf[:p + 5]
        self._base = p + 5
        self._header_ok = True

    # -- token 解码 --

    def _decode_tokens(self):
        buf = self._buf
        out = self._out
        orig_len = self._orig_len
        window = self._window
        produced = bytearray()
        pos = 0
        n = len(buf)
        while pos < n:
            tag = buf[pos]
            if tag < 0x80:
                cnt = tag + 1
                if pos + 1 + cnt > n:
                    break  # 字面量块没收全，等更多数据
                seg = bytes(buf[pos + 1:pos + 1 + cnt])
                pos += 1 + cnt
            else:
                if tag == 0xFF:
                    r = read_varint(buf, pos + 1)
                    if r is None:
                        break
                    extra, p2 = r
                    length = MIN_MATCH + 0x7F + extra
                else:
                    length = MIN_MATCH + (tag - 0x80)
                    p2 = pos + 1
                if length > MAX_MATCH:
                    raise FormatError(
                        self._base + pos,
                        "匹配长度 %d 超过上限 %d" % (length, MAX_MATCH))
                r = read_varint(buf, p2)
                if r is None:
                    break  # 偏移字段没收全
                off = r[0] + 1
                if off > window:
                    raise FormatError(
                        self._base + pos,
                        "匹配偏移 %d 超过窗口大小 %d" % (off, window))
                if off > len(out):
                    raise FormatError(
                        self._base + pos,
                        "匹配偏移 %d 超出已解码数据量 %d" % (off, len(out)))
                if off >= length:
                    seg = bytes(out[len(out) - off:len(out) - off + length])
                else:
                    # 偏移小于长度：源与目标重叠，按周期重复
                    piece = bytes(out[len(out) - off:])
                    q, rem = divmod(length, off)
                    seg = piece * q + piece[:rem]
                pos = r[1]
            out += seg
            produced += seg
            if len(out) > orig_len:
                raise FormatError(
                    self._base + pos,
                    "解码长度超过头部声明的 %d 字节" % orig_len)
        if pos:
            del buf[:pos]
            self._base += pos
        if produced:
            self._crc = crc32(produced)
        return bytes(produced)

    # -- 对外接口 --

    def feed(self, chunk):
        """喂入一块压缩数据，返回本次新解压出的字节。"""
        if self._done:
            raise ValueError("finish() 之后不能再 feed")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            raise TypeError("feed() 只接受字节类型，收到: %r" % type(chunk).__name__)
        self._buf += chunk
        if not self._header_ok:
            self._parse_header()
        if self._header_ok:
            return self._decode_tokens()
        return b""

    def finish(self):
        """结束输入并做完整性校验；重复调用返回 b""。"""
        if self._done:
            return b""
        self._done = True
        if not self._header_ok:
            raise FormatError(self._base, "数据被截断：头部不完整")
        if self._buf:
            raise FormatError(self._base, "数据被截断：数据块不完整")
        if len(self._out) != self._orig_len:
            raise FormatError(
                self._base,
                "实际解压长度 %d 与头部声明的 %d 不符" % (len(self._out), self._orig_len))
        if self._crc != self._crc_expect:
            raise FormatError(
                self._base,
                "CRC32 校验失败：期望 %08X，实际 %08X" % (self._crc_expect, self._crc))
        return b""


# ---------------------------------------------------------------- 一次性接口

def compress(data, *, level=6, window=32768):
    """一次性压缩，返回完整 lzpack 流。"""
    validate_config(level, window)
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("compress() 只接受字节类型，收到: %r" % type(data).__name__)
    return compress_data(bytes(data), level, window)


def decompress(blob):
    """一次性解压；任何格式问题都抛 FormatError。"""
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise TypeError("decompress() 只接受字节类型，收到: %r" % type(blob).__name__)
    d = Decompressor()
    out = [d.feed(bytes(blob))]
    out.append(d.finish())
    return b"".join(out)
