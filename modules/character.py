"""角色系统模块。

负责加载角色数据、管理角色 prompt、提供角色信息查询接口。
所有角色数据以 JSON 格式存储于 data/characters/ 目录下。

角色 JSON 支持两种注释格式：
- 单行注释 //
- 多行注释 /* ... */
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from ..core.exceptions import CharacterNotFoundError
from ..core.json_utils import strip_json_comments as _strip_json_comments


@dataclass
class CharacterPrompt:
    """角色 prompt 数据。

    存储角色的完整设定信息，用于 LLM 角色扮演对话。
    所有字段从角色 JSON 文件反序列化得到。

    Attributes:
        name: 角色全名。
        nickname: 角色昵称或常用称呼。
        gender: 性别。
        age: 年龄。
        personality: 性格特征标签列表，如 ["温和", "内向"]。
        background: 角色背景故事文本。
        dialogue_style: 对话风格描述，供 LLM 参考。
        likes: 喜欢的事物列表。
        dislikes: 厌恶的事物列表。
        hobbies: 兴趣爱好列表。
        affection_thresholds: 好感度阈值事件映射表。
            key 为事件 ID，value 为触发该事件所需的最小好感度。
        emotional_triggers: 情绪触发规则，定义特定条件触发的情绪状态。
    """

    name: str
    nickname: str
    gender: str
    age: int
    personality: list[str]
    background: str
    dialogue_style: str
    likes: list[str]
    dislikes: list[str]
    hobbies: list[str]
    affection_thresholds: dict[str, int]
    emotional_triggers: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterPrompt:
        """从字典创建角色数据。

        使用 .get() 安全获取字段，缺失字段使用默认值，
        避免因 JSON 字段缺失导致加载崩溃。

        Args:
            data: 角色数据的字典表示。

        Returns:
            创建好的 CharacterPrompt 实例。
        """
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
        """转为可序列化字典。

        用于存档或 API 传输。

        Returns:
            角色数据的字典表示。
        """
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
        """生成完整的角色 prompt 文本，供 LLM 使用。

        prompt 格式为结构化文本，包含角色名称、性格、背景、
        对话风格、喜好厌恶等信息，指导 LLM 以角色身份进行对话。

        Returns:
            格式化的 prompt 文本字符串。
        """
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

    负责加载、缓存和查询角色数据。角色数据存储为独立的 JSON 文件，
    每个文件对应一个角色。支持热重载。

    Usage:
        mgr = CharacterManager("data/characters")
        mgr.load_all()
        char = mgr.get_character("洛疏律")
        print(char.get_full_prompt())
    """

    def __init__(self, data_dir: str) -> None:
        """初始化角色管理器。

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
        """从磁盘加载所有角色数据。

        扫描 data_dir 下所有 .json 文件，逐一解析并缓存到 _characters 字典。
        加载失败的文件会打印错误日志，不影响其他角色的加载。
        支持带注释的 JSON（由 _strip_json_comments 处理）。
        """
        self._characters.clear()
        if not os.path.isdir(self._data_dir):
            return

        for filename in os.listdir(self._data_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self._data_dir, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    content = f.read()
                # 先移除注释再解析 JSON
                data = json.loads(_strip_json_comments(content))
                character = CharacterPrompt.from_dict(data)
                self._characters[character.name] = character
            except (json.JSONDecodeError, IOError) as e:
                # 记录加载失败但继续加载其他角色
                print(f"[VisualNovel] 加载角色文件失败 {filename}: {e}")

        self._loaded = True

    def reload(self) -> None:
        """重新加载所有角色数据（热重载）。

        在插件运行时配置更新后调用。
        """
        self.load_all()

    def get_character(self, name: str) -> CharacterPrompt:
        """获取指定角色的数据。

        如果尚未加载，自动触发 load_all()。

        Args:
            name: 角色名称。

        Returns:
            角色 prompt 数据。

        Raises:
            CharacterNotFoundError: 角色不存在时抛出，附带可用角色列表。
        """
        if not self._loaded:
            self.load_all()
        character = self._characters.get(name)
        if character is None:
            raise CharacterNotFoundError(
                f"角色 '{name}' 不存在。可用角色: {', '.join(self.list_characters())}"
            )
        return character

    def list_characters(self) -> list[str]:
        """获取所有已加载的角色名称列表。

        Returns:
            角色名列表，如 ["洛疏律", "查维尔"]。
        """
        if not self._loaded:
            self.load_all()
        return list(self._characters.keys())

    def get_all_characters(self) -> dict[str, CharacterPrompt]:
        """获取所有角色数据字典。

        Returns:
            角色名称到 CharacterPrompt 的映射字典。
        """
        if not self._loaded:
            self.load_all()
        return dict(self._characters)
