"""记事本与线索系统模块。

在日常对话中自动检测并记录角色的喜好线索到玩家记事本。
记事本按角色分类整理线索，支持与礼物赠送系统联动，
在玩家选择礼物时提供角色喜好提示。

线索分类：喜好（likes）、厌恶（dislikes）、兴趣（hobbies）、性格（personality）、故事（story）
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Clue:
    """单条线索数据。

    记录从对话中提取的一条角色信息线索。

    Attributes:
        category: 线索分类（likes, dislikes, hobbies, personality, story）。
        content: 线索内容文本。
        source: 线索来源，即提取该线索的原始对话文本。
        character_name: 线索关联的角色名称。
        discovered_at: 发现时间，ISO 格式字符串，默认自动生成。
        confirmed: 是否已验证，用于确认线索的准确性。
    """

    category: str
    content: str
    source: str
    character_name: str
    discovered_at: str = ""
    confirmed: bool = False

    def __post_init__(self) -> None:
        """初始化后自动填充发现时间。"""
        if not self.discovered_at:
            self.discovered_at = datetime.now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "category": self.category,
            "content": self.content,
            "source": self.source,
            "character_name": self.character_name,
            "discovered_at": self.discovered_at,
            "confirmed": self.confirmed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Clue:
        """从字典反序列化。

        Args:
            data: 线索数据的字典表示。

        Returns:
            反序列化后的 Clue 实例。
        """
        return cls(
            category=data.get("category", "unknown"),
            content=data.get("content", ""),
            source=data.get("source", ""),
            character_name=data.get("character_name", ""),
            discovered_at=data.get("discovered_at", ""),
            confirmed=data.get("confirmed", False),
        )


# 线索分类的中文标签映射
CATEGORY_LABELS: dict[str, str] = {
    "likes": "喜爱之物",
    "dislikes": "厌恶之物",
    "hobbies": "兴趣爱好",
    "personality": "性格特点",
    "story": "过往经历",
}

# 各类别对应的触发关键词
# 日常对话文本中包含这些关键词时，自动提取为对应分类的线索
CLUE_KEYWORDS: dict[str, list[str]] = {
    "likes": ["喜欢", "最爱", "特别喜欢", "很中意", "不错", "好吃", "好喝", "好看"],
    "dislikes": ["讨厌", "不喜欢", "最讨厌", "受不了", "恶心", "害怕"],
    "hobbies": ["爱好", "平时", "空闲", "周末", "经常", "喜欢做", "兴趣"],
    "personality": ["性格", "脾气", "性子", "就是这样的"],
    "story": ["记得", "以前", "那时候", "曾经", "小时候", "往事"],
}


class NotebookManager:
    """记事本管理器。

    管理所有已发现的线索，提供添加、查询、匹配功能。
    支持自动持久化到磁盘 JSON 文件。

    Usage:
        mgr = NotebookManager("data/saves")
        clues = mgr.scan_text_for_clues("我最喜欢花了", "洛疏律")
        mgr.summarize("洛疏律")  # 生成格式化摘要
    """

    def __init__(self, save_dir: str) -> None:
        """初始化记事本管理器。

        Args:
            save_dir: 存档目录路径，用于持久化记事本数据。
        """
        self._save_dir = save_dir
        self._clues: list[Clue] = []
        self._auto_save = True

    @property
    def auto_save(self) -> bool:
        """是否启用自动保存。

        启用时，每次添加新线索会自动写盘。
        """
        return self._auto_save

    @auto_save.setter
    def auto_save(self, value: bool) -> None:
        self._auto_save = value

    def add_clue(self, clue: Clue) -> bool:
        """添加一条线索。

        去重逻辑：同角色、同分类、同内容的线索视为重复，跳过添加。

        Args:
            clue: 线索数据。

        Returns:
            是否成功添加（True 表示新线索，False 表示已存在）。
        """
        # 去重检查：同角色、同分类、同内容视为重复
        for existing in self._clues:
            if (
                existing.character_name == clue.character_name
                and existing.category == clue.category
                and existing.content == clue.content
            ):
                return False

        self._clues.append(clue)

        if self._auto_save:
            self.save()

        return True

    def scan_text_for_clues(self, text: str, character_name: str) -> list[Clue]:
        """扫描对话文本，提取喜好线索。

        遍历 CLUE_KEYWORDS 中的关键词，如果文本中包含某个关键词，
        则将整段文本作为一条线索记录到对应分类中。

        Args:
            text: 对话文本内容。
            character_name: 说话的角色名称。

        Returns:
            本次扫描发现的新线索列表（已去重）。
        """
        discovered: list[Clue] = []

        for category, keywords in CLUE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    # 将包含关键词的整段文本作为线索内容
                    clue = Clue(
                        category=category,
                        content=text.strip(),
                        source=text.strip(),
                        character_name=character_name,
                    )
                    if self.add_clue(clue):
                        discovered.append(clue)

        return discovered

    def get_clues_for_character(self, character_name: str) -> list[Clue]:
        """获取指定角色的所有线索。

        Args:
            character_name: 角色名称。

        Returns:
            该角色的所有 Clue 列表。
        """
        return [c for c in self._clues if c.character_name == character_name]

    def get_clues_by_category(self, character_name: str, category: str) -> list[Clue]:
        """获取指定角色指定分类的线索。

        Args:
            character_name: 角色名称。
            category: 线索分类。

        Returns:
            符合条件的 Clue 列表。
        """
        return [c for c in self._clues if c.character_name == character_name and c.category == category]

    def get_gift_hints(self, character_name: str) -> list[str]:
        """获取角色喜欢的礼物线索提示。

        返回角色喜好和兴趣相关的线索文本，供 LLM 或 UI 提示用。

        Args:
            character_name: 角色名称。

        Returns:
            格式化后的提示文本列表。
        """
        hints: list[str] = []
        likes = self.get_clues_by_category(character_name, "likes")
        hobbies = self.get_clues_by_category(character_name, "hobbies")

        for clue in likes:
            hints.append(f"（线索）{character_name}似乎喜欢：{clue.content}")

        for clue in hobbies:
            hints.append(f"（线索）{character_name}的兴趣爱好：{clue.content}")

        return hints

    def check_gift_match(self, character_name: str, gift_name: str) -> str | None:
        """检查礼物是否匹配已知线索。

        对比礼物名称与已记录的喜好/厌恶线索，给出匹配或警告提示。
        匹配算法基于字符集重叠度（至少 2 个非空白字符重叠）。

        Args:
            character_name: 目标角色名称。
            gift_name: 礼物名称。

        Returns:
            匹配提示信息。没有已知线索或不匹配时返回 None。
        """
        clues = self.get_clues_for_character(character_name)
        if not clues:
            return None

        # 检查礼物名是否与已知"喜好"线索内容中的词语重叠
        for clue in clues:
            if clue.category in ("likes", "hobbies"):
                clue_chars = set(clue.content)
                gift_chars = set(gift_name)
                # 至少有两个中文字符匹配才算有关联（避免单字误匹配）
                common = clue_chars & gift_chars
                common_non_whitespace = {c for c in common if c.strip()}
                if len(common_non_whitespace) >= 2 or any(
                    keyword in clue.content for keyword in CLUE_KEYWORDS["likes"] + CLUE_KEYWORDS["hobbies"]
                ):
                    return f"根据记事本线索，{character_name}可能会喜欢这个礼物！"

        # 检查是否匹配厌恶的事物
        for clue in clues:
            if clue.category == "dislikes":
                clue_chars = set(clue.content)
                gift_chars = set(gift_name)
                common = clue_chars & gift_chars
                common_non_whitespace = {c for c in common if c.strip()}
                if len(common_non_whitespace) >= 2 or any(
                    keyword in clue.content for keyword in CLUE_KEYWORDS["dislikes"]
                ):
                    return f"警告：根据记事本线索，{character_name}可能不喜欢这类物品。"

        return None

    def summarize(self, character_name: str | None = None) -> str:
        """生成记事本的摘要文本。

        按角色和分类整理所有线索，生成易读的格式化文本。

        Args:
            character_name: 可选，只生成指定角色的摘要。为 None 时生成所有角色汇总。

        Returns:
            格式化的摘要文本字符串。
        """
        if character_name:
            clues = self.get_clues_for_character(character_name)
            header = f"📓 {character_name} 的记事本\n"
        else:
            clues = self._clues
            header = "📓 记事本\n"

        if not clues:
            return header + "（暂无线索记录）"

        # 按分类分组
        by_category: dict[str, list[Clue]] = {}
        for clue in clues:
            by_category.setdefault(clue.category, []).append(clue)

        lines = [header]
        for cat, cat_clues in by_category.items():
            label = CATEGORY_LABELS.get(cat, cat)
            lines.append(f"\n  【{label}】")
            for clue in cat_clues:
                # 截断过长内容
                lines.append(f"    · {clue.content[:50]}{'...' if len(clue.content) > 50 else ''}")

        return "\n".join(lines)

    # ==================== 持久化 ====================

    def save(self) -> None:
        """持久化记事本数据到磁盘。

        保存为 JSON 格式到 save_dir/notebook.json。
        """
        if not self._save_dir:
            return
        os.makedirs(self._save_dir, exist_ok=True)
        filepath = os.path.join(self._save_dir, "notebook.json")
        try:
            data = [clue.to_dict() for clue in self._clues]
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"[VisualNovel] 保存记事本失败: {e}")

    def load(self) -> None:
        """从磁盘加载记事本数据。

        从 save_dir/notebook.json 读取，如文件不存在则不做任何操作。
        """
        filepath = os.path.join(self._save_dir, "notebook.json") if self._save_dir else ""
        if not filepath or not os.path.isfile(filepath):
            return
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            self._clues = [Clue.from_dict(item) for item in data]
        except (json.JSONDecodeError, IOError) as e:
            print(f"[VisualNovel] 加载记事本失败: {e}")

    def clear(self) -> None:
        """清空所有线索。"""
        self._clues.clear()

    # ==================== 存档对接 ====================

    def dump_state(self) -> list[dict[str, Any]]:
        """导出状态用于存档。

        Returns:
            可序列化的线索列表。
        """
        return [clue.to_dict() for clue in self._clues]

    def load_state(self, clues_data: list[dict[str, Any]]) -> None:
        """从存档数据加载状态。

        Args:
            clues_data: 线索字典列表。
        """
        self._clues = [Clue.from_dict(item) for item in clues_data]
