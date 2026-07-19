"""角色系统模块。

负责加载角色数据、管理角色 prompt、提供角色信息查询接口。
所有角色数据以 JSON 格式存储于 data/characters/ 目录下。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from ..core.exceptions import CharacterNotFoundError


@dataclass
class CharacterPrompt:
    """角色 prompt 数据。"""

    name: str  # 角色名称
    nickname: str  # 角色昵称/称呼
    gender: str  # 性别
    age: int  # 年龄
    personality: list[str]  # 性格特征列表
    background: str  # 角色背景故事
    dialogue_style: str  # 对话风格描述
    likes: list[str]  # 喜欢的事物
    dislikes: list[str]  # 厌恶的事物
    hobbies: list[str]  # 兴趣爱好
    affection_thresholds: dict[str, int]  # 好感度阈值区间
    emotional_triggers: dict[str, Any] = field(default_factory=dict)  # 情绪触发规则

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterPrompt:
        """从字典创建角色数据。"""
        return cls(
            name=data.get("name", ""),
            nickname=data.get("nickname", ""),
            gender=data.get("gender", "未知"),
            age=data.get("age", 0),
            personality=data.get("personality", []),
            background=data.get("background", ""),
            dialogue_style=data.get("dialogue_style", ""),
            likes=data.get("likes", []),
            dislikes=data.get("dislikes", []),
            hobbies=data.get("hobbies", []),
            affection_thresholds=data.get("affection_thresholds", {}),
            emotional_triggers=data.get("emotional_triggers", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """转为可序列化字典。"""
        return {
            "name": self.name,
            "nickname": self.nickname,
            "gender": self.gender,
            "age": self.age,
            "personality": self.personality,
            "background": self.background,
            "dialogue_style": self.dialogue_style,
            "likes": self.likes,
            "dislikes": self.dislikes,
            "hobbies": self.hobbies,
            "affection_thresholds": self.affection_thresholds,
            "emotional_triggers": self.emotional_triggers,
        }

    def get_full_prompt(self) -> str:
        """生成完整的角色 prompt 文本，供 LLM 使用。"""
        lines = [
            f"你正在扮演 {self.name}（{self.nickname}）。",
            f"性格特征：{'、'.join(self.personality)}",
            f"背景故事：{self.background}",
            f"对话风格：{self.dialogue_style}",
            f"喜欢的事物：{'、'.join(self.likes)}",
            f"厌恶的事物：{'、'.join(self.dislikes)}",
            f"兴趣爱好：{'、'.join(self.hobbies)}",
            "",
            "请根据以上设定进行对话，保持角色的一致性。",
        ]
        return "\n".join(lines)


class CharacterManager:
    """角色管理器。

    负责加载、缓存和查询角色数据。角色数据存储为独立 JSON 文件。
    """

    def __init__(self, data_dir: str) -> None:
        """
        Args:
            data_dir: 角色数据文件所在目录的绝对路径。
        """
        self._data_dir = data_dir
        self._characters: dict[str, CharacterPrompt] = {}
        self._loaded = False

    @property
    def data_dir(self) -> str:
        """获取角色数据目录路径。"""
        return self._data_dir

    def load_all(self) -> None:
        """从磁盘加载所有角色数据。"""
        self._characters.clear()
        if not os.path.isdir(self._data_dir):
            return

        for filename in os.listdir(self._data_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self._data_dir, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = json.load(f)
                character = CharacterPrompt.from_dict(data)
                self._characters[character.name] = character
            except (json.JSONDecodeError, IOError) as e:
                # 记录加载失败但继续加载其他角色
                print(f"[VisualNovel] 加载角色文件失败 {filename}: {e}")

        self._loaded = True

    def reload(self) -> None:
        """重新加载所有角色数据（热重载）。"""
        self.load_all()

    def get_character(self, name: str) -> CharacterPrompt:
        """获取指定角色的数据。

        Args:
            name: 角色名称。

        Returns:
            角色 prompt 数据。

        Raises:
            CharacterNotFoundError: 角色不存在。
        """
        if not self._loaded:
            self.load_all()
        character = self._characters.get(name)
        if character is None:
            raise CharacterNotFoundError(f"角色 '{name}' 不存在。可用角色: {', '.join(self.list_characters())}")
        return character

    def list_characters(self) -> list[str]:
        """获取所有已加载的角色名称列表。"""
        if not self._loaded:
            self.load_all()
        return list(self._characters.keys())

    def get_all_characters(self) -> dict[str, CharacterPrompt]:
        """获取所有角色数据字典（名称 -> 数据）。"""
        if not self._loaded:
            self.load_all()
        return dict(self._characters)
