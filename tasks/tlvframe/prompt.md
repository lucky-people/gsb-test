在当前仓库用 Python 标准库实现一个「二进制 TLV 帧编解码与流式解码」库，包名 `tlvframe`，不引入任何第三方依赖。

帧格式固定为（全部小端）：

```text
magic(4 字节 = b"TLVF") | version(1 字节 = 1) | type(1 字节, 0..255) | length(4 字节无符号) | payload(length 字节) | crc32(4 字节, 对 payload 计算)
```

功能要求：
1. 帧对象与编码：`Frame(type: int, payload: bytes)`，提供 `type`、`payload`、`size`（整帧字节数）与 `==`、`repr()`。`encode_frames(frames) -> bytes` 把多个帧拼成一段字节流；`type` 不在 0..255、`payload` 不是 bytes、单个 payload 超过 64 MiB 时抛 `tlvframe.errors.FrameError`（带中文说明与 `frame_index`）。
2. 解码：`decode_frames(data: bytes) -> list[Frame]`，严格校验魔数、版本、长度与实际剩余字节数、CRC32。任何不符（坏魔数、版本不是 1、长度超出剩余数据、CRC 不匹配、字节流被截断、帧后残留无法解释的垃圾）都抛 `FrameError`，异常必须带 `offset`（出错位置在整段字节流里的 0 基偏移）、`frame_index`（第几个帧，0 基）与中文 `reason`。空输入返回空列表。
3. 流式解码：`FrameDecoder()`，提供 `feed(chunk: bytes) -> list[Frame]`（返回当前已凑齐的完整帧，跨 chunk 的半帧与长度不足要缓存）、`finish() -> None`（缓冲区还有残留字节时抛 `FrameError`）、`buffered_bytes` 属性（当前缓存了多少字节）。要求按任意切分方式喂入同一段字节流，得到的帧序列与 `decode_frames` 完全一致。
4. 变长整数：`encode_varint(value: int) -> bytes` 与 `decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]`（返回 `(值, 消耗的字节数)`），使用无符号 LEB128。负数、超过 64 位的值、编码超过 10 字节、`decode_varint` 遇到截断或未终止的字节流都要抛 `FrameError`。`0` 编码为单个 `0x00`。
5. 文本帧辅助：`encode_text(type: int, text: str, encoding: str = "utf-8") -> bytes` 与 `decode_text(frame: Frame, encoding: str = "utf-8") -> str`；`decode_text` 遇到非法字节序列抛 `FrameError`（说明里带上 `frame.type` 与偏移）。
6. 其他辅助：`select(frames, type=None) -> list[Frame]`（按类型筛选，保持顺序）、`frame_checksum(payload: bytes) -> int`（返回 32 位无符号 CRC32 值）。
7. 性能：README 给出本机实测的耗时与峰值内存，且耗时与内存必须分别测量（不得把 tracemalloc 的追踪开销计入计时窗口）。至少报告：编码 10 万个帧（payload 平均 200 字节）的耗时与峰值内存；用 `decode_frames` 解码同一段字节流的耗时；用 `FrameDecoder` 按 4 KB 分块解码同一段字节流的耗时。
8. 边界与健壮性：空 payload、payload 恰好 64 MiB（允许）与超过 64 MiB（报错）、长度字段比实际数据大、CRC 被改一个字节、版本不是 1、魔数被打乱、连续帧之间插入 1 个垃圾字节、流式按 1 字节喂入、`type` 取 0 与 255、payload 全 0 与全 0xFF、非 ASCII 文本帧（含 emoji）、以及固定的字节级断言（手写一段期望的十六进制，证明小端与字段顺序正确）。以上都要写进 README 并有测试。

交付物：
- `tlvframe/` 包：`__init__.py`（对外只暴露 `Frame`、`encode_frames`、`decode_frames`、`FrameDecoder`、`encode_varint`、`decode_varint`、`encode_text`、`decode_text`、`select`、`frame_checksum`）、`frames.py`（帧结构与常量）、`codec.py`（编码/解码/流式解码）、`varint.py`（LEB128）、`errors.py`（自定义异常）。
- `test_tlvframe.py`：标准库 `unittest`，必须覆盖：固定十六进制字节断言、往返编解码、CRC 篡改、版本与魔数错误、长度越界与截断、帧间垃圾字节、流式按 1/3/全量三种切分一致、`finish()` 对残留字节报错、varint 的 0/边界值/超长/截断、文本帧的非法 UTF-8、以及一组性能用例（1 万帧）。
- `bench.py`：构造 10 万个帧（payload 平均约 200 字节），分别报告编码、整段解码、4 KB 分块流式解码的耗时与峰值内存。
- `README.md`：帧格式的字节级说明（含字段偏移表）、CRC 与长度校验策略、流式解码的缓冲与状态机说明、复杂度、与常见 TLV/长度前缀协议（如 length-prefix、MessagePack）的差异、边界取舍、本机实测数据。

约束：只用 Python 标准库；模块按职责拆分，不要把所有逻辑塞进一个文件；注释和报错信息用中文；不要留下临时调试脚本；不要尝试联网或安装依赖。
