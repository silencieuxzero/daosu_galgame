"""好感度系统模块。

基于角色性格特征实现智能好感度动态调整。
支持好感度阈值区间，不同区间触发不同的角色反应与剧情分支。
支持为每个角色定义独特的性格-选项-好感度映射规则。

好感度范围：-100（最低）到 +100（最高），共 7 个等级区间。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .character import CharacterPrompt


# 好感度等级与数值区间映射表
# key：等级名称（友好度标识）
# value：(最低值, 最高值) 闭区间
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
    """根据好感度数值返回对应的等级名称。

    遍历 AFFECTION_LEVELS 查找数值所属的区间，
    返回对应的等级名称。如果不在任何区间内返回"未知"。

    Args:
        value: 好感度数值，范围 -100 到 100。

    Returns:
        等级名称字符串，如"友好"、"亲近"等。
    """
    for level, (low, high) in AFFECTION_LEVELS.items():
        if low <= value <= high:
            return level
    return "未知"


@dataclass
class AffectionRule:
    """好感度变动规则。

    定义特定条件（选项/行为）下的好感度变动量。
    规则包含基础变动值、适用的性格标签、反转标签和特殊倍率。

    Attributes:
        option_id: 规则关联的选项标识，与对话脚本中的 option_id 对应。
        description: 选项描述文本。
        base_change: 基础变动值（正整数表示增加，负整数表示减少）。
        personality_tags: 适用该规则的角色性格标签列表。
        reverse_for_tags: 触发好感度变动反转的性格标签列表。
            如果一个标签在此列表中，且角色具备该性格，则实际变动值取反。
        special_multiplier: 特殊性格倍率字典。
            key 为角色性格标签，value 为倍率系数，最终变动 = 基础变动 × 倍率。
    """

    option_id: str
    description: str
    base_change: int
    personality_tags: list[str] = field(default_factory=list)
    reverse_for_tags: list[str] = field(default_factory=list)
    special_multiplier: dict[str, float] = field(default_factory=dict)

    def calculate_change(self, character_personality: list[str]) -> int:
        """根据角色性格计算实际好感度变动。

        计算流程：
        1. 从 base_change 开始
        2. 检查角色性格中是否有反转标签，如果有则反转符号
        3. 检查角色性格中是否有特殊倍率标签，如果有则乘以倍率

        Args:
            character_personality: 角色性格标签列表。

        Returns:
            实际好感度变动值（整数）。
        """
        change = self.base_change

        # 检查是否有触发反转的性格标签
        # 适用于傲娇等性格：原本加好感的行为反而减好感
        for tag in character_personality:
            if tag in self.reverse_for_tags:
                change = -change
                break

        # 应用特殊倍率
        # 适用于内向、腼腆等性格：对某些行为反应更敏感
        for tag, multiplier in self.special_multiplier.items():
            if tag in character_personality:
                change = int(change * multiplier)

        return change


@dataclass
class AffectionState:
    """单个角色的好感度状态。

    记录单个角色当前的好感度数值，并提供等级查询和序列化能力。

    Attributes:
        character_name: 角色名称。
        value: 好感度数值，范围 -100 到 100。
    """

    character_name: str
    value: int = 0

    @property
    def level(self) -> str:
        """获取当前好感度等级。

        Returns:
            等级名称，如"友好"、"亲近"等。
        """
        return get_affection_level(self.value)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典，用于存档持久化。"""
        return {
            "character_name": self.character_name,
            "value": self.value,
            "level": self.level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AffectionState:
        """从字典反序列化。

        Args:
            data: 包含 character_name 和 value 的字典。

        Returns:
            反序列化后的 AffectionState 实例。
        """
        return cls(
            character_name=data.get("character_name", ""),
            value=data.get("value", 0),
        )


class AffectionManager:
    """好感度管理器。

    管理所有角色的好感度状态，应用好感度变动规则，提供等级查询和阈值检测。

    核心职责：
    - 维护每个角色的好感度数值
    - 根据 AffectionRule 计算并应用选项带来的好感度变动
    - 检测好感度是否达到剧情触发阈值

    Usage:
        mgr = AffectionManager(default_value=0, max_value=100, min_value=-100)
        mgr.register_rules_from_config("洛疏律", rules_config)
        mgr.apply_option("洛疏律", "curious")  # 返回实际变动值
        mgr.get_level("洛疏律")  # 返回"友好"
    """

    def __init__(
        self,
        default_value: int = 0,
        max_value: int = 100,
        min_value: int = -100,
    ) -> None:
        """初始化好感度管理器。

        Args:
            default_value: 新角色的默认好感度初始值。
            max_value: 好感度上限值。
            min_value: 好感度下限值。
        """
        self._states: dict[str, AffectionState] = {}
        self._rules: dict[str, list[AffectionRule]] = {}
        self._character_manager: Any = None  # 运行时注入角色管理器引用
        self._default_value = default_value
        self._max_value = max_value
        self._min_value = min_value

    def set_character_manager(self, char_mgr: Any) -> None:
        """注入角色管理器引用。

        用于在计算好感度变动时获取角色性格标签。

        Args:
            char_mgr: CharacterManager 实例。
        """
        self._character_manager = char_mgr

    def register_rule(self, character_name: str, rule: AffectionRule) -> None:
        """为指定角色注册一条好感度规则。

        Args:
            character_name: 角色名称。
            rule: 好感度规则实例。
        """
        if character_name not in self._rules:
            self._rules[character_name] = []
        self._rules[character_name].append(rule)

    def register_rules_from_config(self, character_name: str, rules_config: list[dict[str, Any]]) -> None:
        """从配置字典批量注册好感度规则。

        常用于从 config.toml 或角色 JSON 中读取规则配置后批量注册。

        Args:
            character_name: 角色名称。
            rules_config: 规则配置列表，每项应包含：
                - option_id: 选项标识
                - description: 选项描述
                - base_change: 基础变动值
                - personality_tags: 适用角色性格标签
                - reverse_for_tags: 反转符号的性格标签（可选）
                - special_multiplier: 特殊倍率（可选）
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
        """获取或创建角色的好感度状态。

        如果角色尚未有状态记录，自动创建一个初始值为 0 的状态。

        Args:
            character_name: 角色名称。

        Returns:
            该角色的 AffectionState 实例。
        """
        if character_name not in self._states:
            self._states[character_name] = AffectionState(
                character_name=character_name, value=self._default_value
            )
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

        不经过规则计算，直接增减好感度数值。
        数值会被限制在 -100 到 100 的范围内。

        Args:
            character_name: 角色名称。
            delta: 好感度变动量（正数增加，负数减少）。

        Returns:
            修改后的好感度值。
        """
        state = self.get_or_create_state(character_name)
        state.value = max(self._min_value, min(self._max_value, state.value + delta))
        return state.value

    def get(self, character_name: str) -> AffectionState | None:
        """获取指定角色的好感度状态。

        Args:
            character_name: 角色名称。

        Returns:
            AffectionState 实例，如果该角色没有记录则返回 None。
        """
        return self._states.get(character_name)

    def get_value(self, character_name: str) -> int:
        """获取指定角色的好感度数值。

        Args:
            character_name: 角色名称。

        Returns:
            好感度数值，如果无记录则返回 0。
        """
        state = self.get(character_name)
        return state.value if state else 0

    def get_level(self, character_name: str) -> str:
        """获取指定角色的好感度等级。

        Args:
            character_name: 角色名称。

        Returns:
            好感度等级名称。
        """
        state = self.get_or_create_state(character_name)
        return state.level

    def get_threshold_event(self, character_name: str, character: CharacterPrompt) -> str | None:
        """检查是否达到某个好感度阈值，返回触发的事件 ID。

        遍历角色的 affection_thresholds 定义，找到所有已满足阈值的事件中
        最近的一个（阈值最大的那个）。

        Args:
            character_name: 角色名称。
            character: 角色 prompt 数据，包含 affection_thresholds 定义。

        Returns:
            触发的事件 ID，未触发则返回 None。
        """
        value = self.get_value(character_name)
        thresholds = character.affection_thresholds

        # 找到所有满足条件的阈值中事件 ID
        # 注意：这里返回的是最后一个满足条件的，不是"最近"的
        for event_id, threshold_value in thresholds.items():
            if value >= threshold_value:
                return event_id
        return None

    def get_all_states(self) -> dict[str, AffectionState]:
        """获取所有角色的好感度状态。

        Returns:
            角色名称到 AffectionState 的映射字典。
        """
        return dict(self._states)

    def load_state(self, states: dict[str, dict[str, Any]]) -> None:
        """从保存的数据加载好感度状态。

        用于读档时恢复所有角色的好感度数据。

        Args:
            states: 角色名到状态字典的映射。
        """
        self._states.clear()
        for char_name, data in states.items():
            self._states[char_name] = AffectionState.from_dict(data)

    def dump_state(self) -> dict[str, dict[str, Any]]:
        """导出好感度状态用于存档。

        Returns:
            可序列化的状态字典，可传入 load_state 恢复。
        """
        return {name: state.to_dict() for name, state in self._states.items()}
