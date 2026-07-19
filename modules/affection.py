"""好感度系统模块。

基于角色性格特征实现智能好感度动态调整。
支持好感度阈值区间，不同区间触发不同的角色反应与剧情分支。
支持为每个角色定义独特的性格-选项-好感度映射规则。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .character import CharacterPrompt


AFFECTION_LEVELS: dict[str, tuple[int, int]] = {
    "冷漠": (-100, -51),
    "陌生": (-50, -1),
    "普通": (0, 30),
    "友好": (31, 60),
    "亲近": (61, 80),
    "亲密": (81, 95),
    "爱慕": (96, 100),
}


def get_affection_level(value: int) -> str:
    """根据好感度数值返回对应的等级名称。"""
    for level, (low, high) in AFFECTION_LEVELS.items():
        if low <= value <= high:
            return level
    return "未知"


@dataclass
class AffectionRule:
    """好感度变动规则。

    定义特定条件（选项/行为）下的好感度变动量。
    """

    option_id: str  # 选项标识
    description: str  # 选项描述
    base_change: int  # 基础变动值
    personality_tags: list[str]  # 适用的角色性格标签
    reverse_for_tags: list[str] = field(default_factory=list)  # 反转符号的性格标签
    special_multiplier: dict[str, float] = field(default_factory=dict)  # 特殊性格倍率

    def calculate_change(self, character_personality: list[str]) -> int:
        """根据角色性格计算实际好感度变动。

        Args:
            character_personality: 角色性格标签列表。

        Returns:
            实际好感度变动值。
        """
        change = self.base_change

        # 检查是否有触发反转的性格标签
        for tag in character_personality:
            if tag in self.reverse_for_tags:
                change = -change
                break

        # 应用特殊倍率
        for tag, multiplier in self.special_multiplier.items():
            if tag in character_personality:
                change = int(change * multiplier)

        return change


@dataclass
class AffectionState:
    """单个角色的好感度状态。"""

    character_name: str
    value: int = 0

    @property
    def level(self) -> str:
        """获取当前好感度等级。"""
        return get_affection_level(self.value)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "character_name": self.character_name,
            "value": self.value,
            "level": self.level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AffectionState:
        """从字典反序列化。"""
        return cls(
            character_name=data.get("character_name", ""),
            value=data.get("value", 0),
        )


class AffectionManager:
    """好感度管理器。

    管理所有角色的好感度状态，应用好感度变动规则。
    """

    def __init__(self) -> None:
        self._states: dict[str, AffectionState] = {}
        self._rules: dict[str, list[AffectionRule]] = {}
        self._character_manager: Any = None  # 运行时注入

    def set_character_manager(self, char_mgr: Any) -> None:
        """注入角色管理器引用。"""
        self._character_manager = char_mgr

    def register_rule(self, character_name: str, rule: AffectionRule) -> None:
        """为指定角色注册一条好感度规则。

        Args:
            character_name: 角色名称。
            rule: 好感度规则。
        """
        if character_name not in self._rules:
            self._rules[character_name] = []
        self._rules[character_name].append(rule)

    def register_rules_from_config(self, character_name: str, rules_config: list[dict[str, Any]]) -> None:
        """从配置字典批量注册好感度规则。

        Args:
            character_name: 角色名称。
            rules_config: 规则配置列表，每项包含 option_id, description, base_change, personality_tags 等。
        """
        for item in rules_config:
            rule = AffectionRule(
                option_id=item["option_id"],
                description=item.get("description", ""),
                base_change=item["base_change"],
                personality_tags=item.get("personality_tags", []),
                reverse_for_tags=item.get("reverse_for_tags", []),
                special_multiplier=item.get("special_multiplier", {}),
            )
            self.register_rule(character_name, rule)

    def get_or_create_state(self, character_name: str) -> AffectionState:
        """获取或创建角色的好感度状态。"""
        if character_name not in self._states:
            self._states[character_name] = AffectionState(character_name=character_name)
        return self._states[character_name]

    def apply_option(self, character_name: str, option_id: str) -> int:
        """应用玩家选项，计算并更新好感度。

        根据选项 ID 匹配规则，结合角色性格计算实际变动值。

        Args:
            character_name: 目标角色。
            option_id: 玩家选择的选项 ID。

        Returns:
            实际好感度变动值。返回 0 表示未找到匹配规则。
        """
        char_rules = self._rules.get(character_name, [])

        # 查找匹配的规则
        matching_rule = None
        for rule in char_rules:
            if rule.option_id == option_id:
                matching_rule = rule
                break

        if matching_rule is None:
            return 0

        # 获取角色性格
        personality = []
        if self._character_manager:
            try:
                character = self._character_manager.get_character(character_name)
                personality = character.personality
            except Exception:
                personality = []

        # 计算变动
        change = matching_rule.calculate_change(personality)
        self.modify(character_name, change)
        return change

    def modify(self, character_name: str, delta: int) -> int:
        """直接修改好感度值。

        Args:
            character_name: 角色名称。
            delta: 好感度变动量（正数增加，负数减少）。

        Returns:
            修改后的好感度值。
        """
        state = self.get_or_create_state(character_name)
        state.value = max(-100, min(100, state.value + delta))
        return state.value

    def get(self, character_name: str) -> AffectionState | None:
        """获取指定角色的好感度状态。"""
        return self._states.get(character_name)

    def get_value(self, character_name: str) -> int:
        """获取指定角色的好感度数值。"""
        state = self.get(character_name)
        return state.value if state else 0

    def get_level(self, character_name: str) -> str:
        """获取指定角色的好感度等级。"""
        state = self.get_or_create_state(character_name)
        return state.level

    def get_threshold_event(self, character_name: str, character: CharacterPrompt) -> str | None:
        """检查是否达到某个好感度阈值，返回触发的事件 ID。

        Args:
            character_name: 角色名称。
            character: 角色 prompt 数据。

        Returns:
            触发的事件 ID，未触发则返回 None。
        """
        value = self.get_value(character_name)
        thresholds = character.affection_thresholds

        for event_id, threshold_value in thresholds.items():
            if value >= threshold_value:
                return event_id
        return None

    def get_all_states(self) -> dict[str, AffectionState]:
        """获取所有角色的好感度状态。"""
        return dict(self._states)

    def load_state(self, states: dict[str, dict[str, Any]]) -> None:
        """从保存的数据加载好感度状态。"""
        self._states.clear()
        for char_name, data in states.items():
            self._states[char_name] = AffectionState.from_dict(data)

    def dump_state(self) -> dict[str, dict[str, Any]]:
        """导出好感度状态用于存档。"""
        return {name: state.to_dict() for name, state in self._states.items()}
