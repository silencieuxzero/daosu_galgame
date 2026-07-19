"""记事本与线索系统模块。

在日常对话中自动检测并记录角色的喜好线索到玩家记事本。
记事本按角色分类整理线索，支持与礼物赠送系统联动。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Clue:
    """单条线索数据。"""

    category: str  # 线索分类（likes, dislikes, hobbies, personality, story）
    content: str  # 线索内容
    source: str  # 线索来源（对话文本）
    character_name: str  # 关联角色
    discovered_at: str = ""  # 发现时间
    confirmed: bool = False  # 是否已验证

    def __post_init__(self) -> None:
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
        """从字典反序列化。"""
        return cls(
            category=data.get("category", "unknown"),
            content=data.get("content", ""),
            source=data.get("source", ""),
            character_name=data.get("character_name", ""),
            discovered_at=data.get("discovered_at", ""),
            confirmed=data.get("confirmed", False),
        )


CATEGORY_LABELS: dict[str, str] = {
    "likes": "喜爱之物",
    "dislikes": "厌恶之物",
    "hobbies": "兴趣爱好",
    "personality": "性格特点",
    "story": "过往经历",
}

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
    """

    def __init__(self, save_dir: str) -> None:
        """
        Args:
            save_dir: 存档目录，用于持久化记事本数据。
        """
        self._save_dir = save_dir
        self._clues: list[Clue] = []
        self._auto_save = True

    @property
    def auto_save(self) -> bool:
        """是否自动保存。"""
        return self._auto_save

    @auto_save.setter
    def auto_save(self, value: bool) -> None:
        self._auto_save = value

    def add_clue(self, clue: Clue) -> bool:
        """添加一条线索。

        避免重复添加完全相同的线索。

        Args:
            clue: 线索数据。

        Returns:
            是否成功添加（True 表示新线索，False 表示已存在）。
        """
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

        Args:
            text: 对话文本。
            character_name: 说话的角色名称。

        Returns:
            本次扫描发现的新线索列表。
        """
        discovered: list[Clue] = []

        for category, keywords in CLUE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    # 提取包含关键词的句子作为线索
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
        """获取指定角色的所有线索。"""
        return [c for c in self._clues if c.character_name == character_name]

    def get_clues_by_category(self, character_name: str, category: str) -> list[Clue]:
        """获取指定角色指定分类的线索。"""
        return [c for c in self._clues if c.character_name == character_name and c.category == category]

    def get_gift_hints(self, character_name: str) -> list[str]:
        """获取角色喜欢的礼物线索提示。

        供礼物赠送界面调用，提示玩家该角色喜欢什么。
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

        在礼物赠送界面调用，提示玩家选择的礼物是否符合角色喜好。

        Args:
            character_name: 目标角色名称。
            gift_name: 礼物名称。

        Returns:
            匹配提示信息。如果没有匹配线索或已拥有线索则不返回信息。
        """
        clues = self.get_clues_for_character(character_name)
        if not clues:
            return None

        # 检查礼物名是否与已知"喜好"线索内容中的词语重叠
        for clue in clues:
            if clue.category in ("likes", "hobbies"):
                # 提取线索内容中所有字符，检查是否与礼物名有交集
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

        Args:
            character_name: 可选，只生成指定角色的摘要。

        Returns:
            格式化的摘要文本。
        """
        if character_name:
            clues = self.get_clues_for_character(character_name)
            header = f"📓 {character_name} 的记事本\n"
        else:
            clues = self._clues
            header = "📓 记事本\n"

        if not clues:
            return header + "（暂无线索记录）"

        by_category: dict[str, list[Clue]] = {}
        for clue in clues:
            by_category.setdefault(clue.category, []).append(clue)

        lines = [header]
        for cat, cat_clues in by_category.items():
            label = CATEGORY_LABELS.get(cat, cat)
            lines.append(f"\n  【{label}】")
            for clue in cat_clues:
                lines.append(f"    · {clue.content[:50]}{'...' if len(clue.content) > 50 else ''}")

        return "\n".join(lines)

    def save(self) -> None:
        """持久化记事本数据到磁盘。"""
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
        """从磁盘加载记事本数据。"""
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

    def dump_state(self) -> list[dict[str, Any]]:
        """导出状态用于存档。"""
        return [clue.to_dict() for clue in self._clues]

    def load_state(self, clues_data: list[dict[str, Any]]) -> None:
        """从存档数据加载状态。"""
        self._clues = [Clue.from_dict(item) for item in clues_data]
