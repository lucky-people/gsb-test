"""LZ77 匹配查找：哈希链 + 贪心选择。

- 用 3 字节哈希建立哈希链，链上保存窗口内的历史位置；
- 每个位置沿链向后找最长匹配，level 决定最大搜索深度（链长）；
- 匹配长度 >= _SKIP_INSERT 时跳过匹配内部位置的插入，
  长重复数据（日志、全 0 等）下把匹配查找从 O(n * 链长) 降到近似 O(n)。

复杂度：设 n 为输入长度、c 为链长上限，则平均 O(n * c)，c 是有界常数，
因此整体是 O(n)；不会出现朴素实现的 O(n^2)。
"""

from array import array

#: 最短匹配长度
MIN_MATCH = 3
#: 最长匹配长度（流格式中长度字段的上限）
MAX_MATCH = 16384

_HASH_BITS = 16
_HASH_SIZE = 1 << _HASH_BITS

#: 各 level 的最大链搜索深度，level 越高找得越仔细
_CHAIN_DEPTH = {1: 4, 2: 8, 3: 16, 4: 32, 5: 64, 6: 128, 7: 256, 8: 512, 9: 1024}
#: 各 level 的“足够好”长度，找到这么长就提前停止搜索
_NICE_LENGTH = {1: 16, 2: 32, 3: 64, 4: 96, 5: 128, 6: 192, 7: 256, 8: 512, 9: 1024}

#: 匹配长度达到该值时，不再把匹配内部的位置插入哈希表（速度优化）
_SKIP_INSERT = 64


def _hash3(data, i):
    """3 字节序列的哈希值（乘积散列）。"""
    v = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16)
    return ((v * 0x9E3779B1) >> (32 - _HASH_BITS)) & (_HASH_SIZE - 1)


def find_tokens(data, level, window):
    """把 data 切成 token 序列。

    产出 ('l', 字面量字节串) 或 ('m', 偏移, 长度)。
    偏移满足 1 <= 偏移 <= window，长度满足 MIN_MATCH <= 长度 <= MAX_MATCH。
    """
    n = len(data)
    depth_max = _CHAIN_DEPTH[level]
    nice = _NICE_LENGTH[level]
    wmask = window - 1  # window 保证是 2 的幂
    head = array("i", [-1]) * _HASH_SIZE
    prev = array("i", [-1]) * window

    i = 0
    lit_start = 0
    while i < n:
        best_len = MIN_MATCH - 1
        best_off = 0
        if i + MIN_MATCH <= n:
            h = _hash3(data, i)
            j = head[h]
            # prev 是 window 大小的环形数组，必须按窗口取模，
            # 否则输入超过 window 后下标越界，且取到的也会是错位的历史位置
            prev[i & wmask] = j
            head[h] = i
            limit = i - window  # 只允许偏移 <= window，即 j >= i - window
            depth = depth_max
            maxl = min(MAX_MATCH, n - i)
            while j >= 0 and j >= limit and depth > 0:
                # 先比“当前最好长度的下一个字节”，不匹配就跳过整段比较
                if best_len < maxl and data[j + best_len] == data[i + best_len]:
                    l = 0
                    while l < maxl and data[j + l] == data[i + l]:
                        l += 1
                    if l > best_len:
                        best_len = l
                        best_off = i - j
                        if l >= nice or l >= maxl:
                            break
                j = prev[j & wmask]
                depth -= 1
        if best_len >= MIN_MATCH:
            if lit_start < i:
                yield ("l", data[lit_start:i])
            yield ("m", best_off, best_len)
            end = i + best_len
            if best_len < _SKIP_INSERT:
                # 短匹配：把内部位置也插入哈希表，保证后续匹配质量
                stop = min(end, n - MIN_MATCH + 1)
                for k in range(i + 1, stop):
                    h = _hash3(data, k)
                    prev[k & wmask] = head[h]
                    head[h] = k
            i = end
            lit_start = i
        else:
            i += 1
    if lit_start < n:
        yield ("l", data[lit_start:n])
