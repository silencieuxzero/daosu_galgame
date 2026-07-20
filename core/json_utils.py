"""JSON 工具函数。

提供带注释的 JSON 解析支持，允许在 JSON 数据文件中使用
// 单行注释和 /* */ 多行注释，在解析前自动清洗。

Usage:
    >>> from core.json_utils import strip_json_comments, load_json_with_comments
    >>> data = load_json_with_comments("data/characters/luoshulv.json")
"""

from __future__ import annotations

import json
import re
from typing import Any


def strip_json_comments(json_str: str) -> str:
    """移除 JSON 中的 // 和 /* */ 注释（仅在字符串外部）。

    手动实现不依赖外部库的 JSON 注释过滤。
    通过维护 in_string 状态避免误删字符串内部的 "//" 或 "/*"。

    Args:
        json_str: 可能包含注释的原始 JSON 字符串。

    Returns:
        移除注释后的纯净 JSON 字符串，可直接传给 json.loads()。
    """
    # 先移除 /* ... */ 块注释
    no_block = re.sub(r'/\*[\s\S]*?\*/', '', json_str)
    # 再移除 // 行注释（不在字符串内部）
    result: list[str] = []
    i = 0
    in_string = False
    while i < len(no_block):
        c = no_block[i]
        if c == '"' and (i == 0 or no_block[i - 1] != '\\'):
            in_string = not in_string
            result.append(c)
            i += 1
        elif not in_string and c == '/' and i + 1 < len(no_block) and no_block[i + 1] == '/':
            # 跳过整行直到换行符
            while i < len(no_block) and no_block[i] != '\n':
                i += 1
        else:
            result.append(c)
            i += 1
    return ''.join(result)


def load_json_with_comments(filepath: str) -> dict[str, Any]:
    """读取并解析带注释的 JSON 文件。

    自动读取文件内容，先清洗注释再解析为标准 JSON。

    Args:
        filepath: JSON 文件路径。

    Returns:
        解析后的 Python 字典。

    Raises:
        FileNotFoundError: 文件不存在。
        json.JSONDecodeError: 清洗注释后仍无法解析。
    """
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    return json.loads(strip_json_comments(content))
