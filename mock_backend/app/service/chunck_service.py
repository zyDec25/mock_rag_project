"""
文本分块服务模块

re 库说明：
    re 是 Python 内置的正则表达式（Regular Expression）标准库，
    提供对字符串进行模式匹配、搜索、替换、分割等操作的功能。
    正则表达式是一种用特殊字符序列描述字符串匹配规则的"迷你语言"。

本文件中用到的关键方法说明：

1. str.replace(old, new)
   - Python 字符串的内置方法（非 re 库方法）
   - 将字符串中所有出现的 old 子串替换为 new 子串
   - 是精确的字面量替换，不支持正则表达式模式
   - 示例: "hello world".replace("world", "python") → "hello python"

2. re.sub(pattern, repl, string)
   - re 库提供的正则替换方法
   - 在 string 中查找所有匹配 pattern（正则表达式）的部分，替换为 repl
   - 比 str.replace 更强大，支持模式匹配（如匹配任意数量的空格、数字等）
   - 示例: re.sub(r"\\d+", "X", "abc123def456") → "abcXdefX"

3. str.strip()
   - Python 字符串的内置方法（非 re 库方法）
   - 去除字符串首尾的空白字符（空格、制表符、换行符等）
   - 不影响字符串中间的空白字符
   - 示例: "  hello world  ".strip() → "hello world"

4. re.split(pattern, string)
   - re 库提供的正则分割方法
   - 按照正则表达式 pattern 匹配到的位置将 string 分割成列表
   - 比 str.split 更灵活，支持复杂的分隔符模式
   - 示例: re.split(r"[,;]", "a,b;c") → ["a", "b", "c"]
"""

import re


def normalize_text(text: str) -> str:
    """
    文本标准化函数：将原始文本清理为统一格式。

    处理步骤：
    1. 将 Windows 换行符 "\\r\\n" 统一替换为 Unix 换行符 "\\n"
       （replace 精确匹配替换，先处理 \\r\\n 避免被后续步骤拆成两个换行）
    2. 将残留的旧版 Mac 换行符 "\\r" 替换为 "\\n"
    3. 使用 re.sub 将连续的空格和制表符（[ \\t]+）压缩为单个空格
       （正则 [ \\t]+ 匹配一个或多个空格/制表符）
    4. 使用 re.sub 将三个及以上连续换行（\\n{3,}）压缩为两个换行（即一个空行）
       （正则 \\n{3,} 匹配3个或更多连续换行符）
    5. 使用 strip() 去除文本首尾的空白字符

    Args:
        text: 需要标准化的原始文本

    Returns:
        标准化后的干净文本
    """
    # 步骤1: 统一 Windows 风格换行符 "\r\n" 为 "\n"
    # 步骤2: 统一旧版 Mac 风格换行符 "\r" 为 "\n"
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 步骤3: 将连续的空格和制表符压缩为单个空格（re.sub 正则替换）
    # 正则 r"[ \t]+" 含义：匹配一个或多个（+）空格或制表符（[ \t]）
    text = re.sub(r"[ \t]+", " ", text)

    # 步骤4: 将3个及以上连续换行压缩为2个换行，保留段落间的空行
    # 正则 r"\n{3,}" 含义：匹配3个或更多（{3,}）连续的换行符（\n）
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 步骤5: 去除首尾空白字符（strip 方法）
    return text.strip()


def split_paragraphs(text: str) -> list[str]:
    """
    段落分割函数：将文本按段落拆分为字符串列表。

    处理步骤：
    1. 先调用 normalize_text 对文本进行标准化
    2. 使用 re.split 按"空行"分割文本（空行 = 换行符 + 可选空白 + 换行符）
       正则 r"\\n\\s*\\n" 含义：匹配一个换行符(\\n)，后跟零个或多个空白字符(\\s*)，
       再跟一个换行符(\\n)，即匹配段落之间的空行
    3. 对每个段落使用 strip() 去除首尾空白，并过滤掉空段落

    Args:
        text: 需要分割的文本

    Returns:
        段落字符串列表，每个元素为一个非空段落
    """
    # 先标准化文本
    text = normalize_text(text)

    # 使用 re.split 按空行分割段落
    # 正则 r"\n\s*\n" 匹配：换行 + 任意空白 + 换行（即段落间的空行）
    paragraphs = re.split(r"\n\s*\n", text)

    # 对每个段落去除首尾空白（strip），并过滤掉空字符串
    return [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]


def split_long_text(text: str, max_chunk_chars: int, overlap_chars: int) -> list[str]:
    """
    长文本滑动窗口切分函数：将超长文本按固定长度切分，并在相邻块之间保留重叠部分。

    核心思想（滑动窗口 + 重叠）：
    - 从文本开头开始，每次截取 max_chunk_chars 个字符作为一个块
    - 下一个块的起始位置 = 当前块结束位置 - overlap_chars（回退重叠字符数）
    - 重叠部分确保上下文不会在块边界处完全断裂，有利于后续检索和语义理解

    示意图（max_chunk_chars=10, overlap_chars=3）：
    文本: [ABCDEFGHIJKLMNOPQRST]
    块1:  [ABCDEFGHIJ]          (位置 0-10)
    块2:       [HIJKLMNOPQ]     (位置 7-17，与块1重叠 HIJ)
    块3:            [OPQRST]    (位置 14-20，与块2重叠 OPQ)

    Args:
        text: 需要切分的长文本
        max_chunk_chars: 每个块的最大字符数
        overlap_chars: 相邻块之间的重叠字符数（用于保持上下文连贯性）

    Returns:
        切分后的文本块列表
    """
    chunks = []
    start = 0  # 当前块的起始位置

    while start < len(text):
        # 计算当前块的结束位置，不超过文本总长度
        end = min(start + max_chunk_chars, len(text))

        # 截取当前块并去除首尾空白
        chunk = text[start:end].strip()

        # 只添加非空块
        if chunk:
            chunks.append(chunk)

        # 如果已经到达文本末尾，结束循环
        if end >= len(text):
            break

        # 下一个块的起始位置 = 当前结束位置 - 重叠字符数
        # 使用 max(0, ...) 防止起始位置变为负数
        start = max(0, end - overlap_chars)

    return chunks


def naive_chunk(
    text: str,
    max_chunk_chars: int = 800,
    overlap_chars: int = 120,
    min_chunk_chars: int = 80,
) -> list[str]:
    """
    朴素文本分块函数（Naive Chunking）：将文本智能地切分为适合 RAG 检索的文本块。

    这是整个分块服务的核心入口函数，采用"贪心合并 + 长文本滑动窗口"的策略：
    - 优先按段落自然边界分割，尽量保持语义完整性
    - 短段落尽可能合并到一个块中（贪心策略），避免产生过多碎片块
    - 超长段落使用滑动窗口切分（调用 split_long_text）
    - 过短的尾部块合并到前一个块中，避免产生无意义的小碎片

    算法流程：
    1. 调用 split_paragraphs 将文本分割为段落列表
    2. 遍历每个段落：
       a. 如果段落超长（> max_chunk_chars）→ 用 split_long_text 滑动窗口切分
       b. 如果当前缓冲区为空 → 将段落放入缓冲区
       c. 尝试将段落追加到缓冲区（用两个换行连接）：
          - 合并后未超限 → 继续累积
          - 合并后超限 → 将缓冲区作为一个块输出，段落成为新缓冲区
       d. 输出缓冲区时，如果缓冲区太短（< min_chunk_chars）→ 合并到上一个块
    3. 处理最后剩余的缓冲区内容

    Args:
        text: 需要分块的原始文本
        max_chunk_chars: 每个块的最大字符数（默认800），控制块的上限大小
        overlap_chars: 长文本滑动窗口切分时的重叠字符数（默认120）
        min_chunk_chars: 块的最小字符数（默认80），低于此值会被合并到相邻块

    Returns:
        分块后的文本列表，每个元素为一个文本块
    """
    # 第1步：将文本按段落分割
    paragraphs = split_paragraphs(text)
    chunks: list[str] = []  # 最终结果列表
    current: str = ""  # 当前正在累积的缓冲区

    for paragraph in paragraphs:
        # 情况A：段落本身超过最大块长度，需要用滑动窗口强制切分
        if len(paragraph) > max_chunk_chars:
            # 先将当前缓冲区中已有的内容输出为一个块
            if current:
                chunks.append(current.strip())
                current = ""

            # 对超长段落使用滑动窗口切分，结果直接追加到 chunks
            chunks.extend(
                split_long_text(
                    paragraph,
                    max_chunk_chars=max_chunk_chars,
                    overlap_chars=overlap_chars,
                )
            )
            continue

        # 情况B：缓冲区为空，直接将当前段落放入缓冲区
        if not current:
            current = paragraph
            continue

        # 情况C：尝试将段落合并到缓冲区（用空行 "\n\n" 连接，模拟段落间距）
        candidate = f"{current}\n\n{paragraph}"

        if len(candidate) <= max_chunk_chars:
            # 合并后未超限，继续累积（贪心策略：尽量让块更大更完整）
            current = candidate
        else:
            # 合并后超限，需要将当前缓冲区输出为一个块
            if len(current) < min_chunk_chars and chunks:
                # 如果缓冲区太短（不足 min_chunk_chars），合并到上一个块的末尾
                # 避免产生过短的无意义碎片块
                chunks[-1] = f"{chunks[-1]}\n\n{current}".strip()
            else:
                # 正常输出为一个独立的块
                chunks.append(current.strip())

            # 当前段落成为新缓冲区的起始内容
            current = paragraph

    # 第3步：处理循环结束后缓冲区中剩余的内容
    if current:
        if len(current) < min_chunk_chars:
            # 剩余内容太短，合并到最后一个块
            chunks[-1] = f"{chunks[-1]}\n\n{current}".strip()
        else:
            # 正常输出为最后一个块
            chunks.append(current.strip())

    return chunks
