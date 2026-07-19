"""互动行为系统模块。

实现多样化的玩家-角色互动功能：
- 礼物赠送系统：选择物品赠送给角色
- 邀约功能：邀请角色参与特定活动
- 日常对话：自由对话交互界面
所有互动行为均关联好感度系统，并支持与记事本线索系统联动。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GiftItem:
    """礼物物品定义。

    Attributes:
        name: 礼物名称。
        description: 礼物描述文本。
        category: 礼物类别（food, book, accessory, decoration, clothing, other）。
        base_affection: 基础好感度加成值。
            最终好感度变动还会受角色性格影响（通过 AffectionRule 计算）。
        tags: 标签列表，用于匹配角色喜好。
    """

    name: str
    description: str
    category: str
    base_affection: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典，用于状态持久化。"""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "base_affection": self.base_affection,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GiftItem:
        """从字典反序列化。

        Args:
            data: 礼物数据的字典表示。

        Returns:
            反序列化后的 GiftItem 实例。
        """
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=data.get("category", "other"),
            base_affection=data.get("base_affection", 0),
            tags=data.get("tags", []),
        )


@dataclass
class Activity:
    """活动定义。

    Attributes:
        name: 活动名称。
        description: 活动描述。
        category: 活动类别（date, adventure, relax, study, etc.）。
        base_affection: 基础好感度加成。
        duration: 持续时间（short, medium, long）。
        tags: 活动标签。
    """

    name: str
    description: str
    category: str
    base_affection: int = 0
    duration: str = "short"
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "base_affection": self.base_affection,
            "duration": self.duration,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Activity:
        """从字典反序列化。"""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=data.get("category", "other"),
            base_affection=data.get("base_affection", 0),
            duration=data.get("duration", "short"),
            tags=data.get("tags", []),
        )


# 默认礼物列表，在插件初始化时加载到管理器
DEFAULT_GIFTS: list[GiftItem] = [
    GiftItem(name="花束", description="一束美丽的鲜花", category="decoration", base_affection=5, tags=["romantic", "beautiful"]),
    GiftItem(name="手工饼干", description="自制的香脆饼干", category="food", base_affection=8, tags=["homemade", "sweet"]),
    GiftItem(name="书籍", description="一本有趣的书", category="book", base_affection=3, tags=["knowledge", "reading"]),
    GiftItem(name="音乐盒", description="精致的音乐盒", category="accessory", base_affection=10, tags=["music", "elegant"]),
    GiftItem(name="围巾", description="温暖的围巾", category="clothing", base_affection=6, tags=["warm", "practical"]),
    GiftItem(name="盆栽", description="可爱的小盆栽", category="decoration", base_affection=4, tags=["nature", "cute"]),
    GiftItem(name="巧克力", description="香浓的巧克力", category="food", base_affection=7, tags=["sweet", "luxury"]),
    GiftItem(name="手写信", description="充满心意的手写信", category="other", base_affection=12, tags=["sincere", "personal"]),
]

# 默认活动列表
DEFAULT_ACTIVITIES: list[Activity] = [
    Activity(name="散步", description="一起去公园散步", category="relax", base_affection=3, duration="short", tags=["outdoor", "casual"]),
    Activity(name="看电影", description="一起看电影", category="date", base_affection=5, duration="medium", tags=["entertainment", "indoor"]),
    Activity(name="喝咖啡", description="一起去咖啡厅", category="date", base_affection=4, duration="short", tags=["food", "casual"]),
    Activity(name="逛书店", description="一起逛书店", category="relax", base_affection=3, duration="medium", tags=["quiet", "knowledge"]),
    Activity(name="野餐", description="一起去郊外野餐", category="adventure", base_affection=8, duration="long", tags=["outdoor", "nature"]),
    Activity(name="做饭", description="一起下厨做饭", category="relax", base_affection=6, duration="medium", tags=["homemade", "cozy"]),
]


class InteractionManager:
    """互动行为管理器。

    管理礼物赠送、邀约活动和日常对话等玩家-角色互动功能。
    与好感度管理器和记事本管理器联动，提供完整的互动闭环体验。

    Usage:
        mgr = InteractionManager(affection_mgr, notebook_mgr)
        mgr.add_all_default_gifts()  # 初始化玩家背包
        result = mgr.give_gift("洛疏律", "花束")
        print(result["message"])
    """

    def __init__(self, affection_manager: Any, notebook_manager: Any | None = None) -> None:
        """初始化互动管理器。

        Args:
            affection_manager: 好感度管理器实例，用于互动后的好感度计算。
            notebook_manager: 可选，记事本管理器实例，用于线索联动提示。
        """
        self._affection = affection_manager
        self._notebook = notebook_manager
        self._gifts: dict[str, GiftItem] = {g.name: g for g in DEFAULT_GIFTS}
        self._activities: dict[str, Activity] = {a.name: a for a in DEFAULT_ACTIVITIES}
        self._player_inventory: list[str] = []  # 玩家拥有的礼物名称列表

    def set_notebook_manager(self, nb_mgr: Any) -> None:
        """注入记事本管理器引用。

        用于初始化时 notebook_manager 尚未就绪的情况。

        Args:
            nb_mgr: NotebookManager 实例。
        """
        self._notebook = nb_mgr

    # ==================== 礼物系统 ====================

    def list_available_gifts(self) -> list[GiftItem]:
        """获取玩家背包中可赠送的礼物列表。

        Returns:
            背包中存在的 GiftItem 列表。
        """
        return [self._gifts[name] for name in self._player_inventory if name in self._gifts]

    def add_gift_to_inventory(self, gift_name: str) -> bool:
        """添加礼物到玩家背包。

        Args:
            gift_name: 礼物名称。

        Returns:
            是否成功添加（礼物不存在时返回 False）。
        """
        if gift_name in self._gifts:
            self._player_inventory.append(gift_name)
            return True
        return False

    def add_all_default_gifts(self) -> None:
        """将所有默认礼物添加到玩家背包。

        通常用于初始化或测试场景，使玩家立即拥有所有可选礼物。
        """
        for name in self._gifts:
            if name not in self._player_inventory:
                self._player_inventory.append(name)

    def give_gift(self, character_name: str, gift_name: str) -> dict[str, Any]:
        """赠送礼物给指定角色。

        处理流程：
        1. 验证礼物是否存在
        2. 验证玩家背包中是否有该礼物
        3. 从背包移除礼物
        4. 计算并应用好感度变动
        5. 查询记事本线索提示

        Args:
            character_name: 目标角色名称。
            gift_name: 礼物名称。

        Returns:
            互动结果字典，包含：
            - success: 是否成功
            - affection_change: 好感度变动值
            - total_affection: 更新后的好感度总值
            - message: 操作结果文本
            - hint: 记事本线索提示（如有）
        """
        gift = self._gifts.get(gift_name)
        if gift is None:
            return {
                "success": False,
                "affection_change": 0,
                "total_affection": 0,
                "message": f"没有找到礼物 '{gift_name}'。",
                "hint": None,
            }

        if gift_name not in self._player_inventory:
            return {
                "success": False,
                "affection_change": 0,
                "total_affection": 0,
                "message": f"背包中没有 '{gift_name}'。",
                "hint": None,
            }

        # 从背包中移除礼物（已消耗）
        self._player_inventory.remove(gift_name)

        # 计算好感度变动：直接使用基础值（如有 AffectionRule 需求可扩展）
        change = gift.base_affection
        total_affection = self._affection.modify(character_name, change)

        # 查询记事本中的礼物匹配线索
        hint = None
        if self._notebook:
            hint = self._notebook.check_gift_match(character_name, gift_name)

        return {
            "success": True,
            "affection_change": change,
            "total_affection": total_affection,
            "message": f"你赠送了 {gift_name} 给 {character_name}。好感度 {'+' if change >= 0 else ''}{change}",
            "hint": hint,
        }

    # ==================== 邀约系统 ====================

    def list_activities(self) -> list[Activity]:
        """获取所有可邀约的活动列表。

        Returns:
            定义好的 Activity 列表。
        """
        return list(self._activities.values())

    def invite(self, character_name: str, activity_name: str) -> dict[str, Any]:
        """邀请角色参加活动。

        好感度变动直接使用活动的基础值，暂未引入性格倍率计算。

        Args:
            character_name: 目标角色名称。
            activity_name: 活动名称。

        Returns:
            互动结果字典。
        """
        activity = self._activities.get(activity_name)
        if activity is None:
            return {
                "success": False,
                "affection_change": 0,
                "total_affection": 0,
                "message": f"没有找到活动 '{activity_name}'。",
            }

        change = activity.base_affection
        total_affection = self._affection.modify(character_name, change)

        return {
            "success": True,
            "affection_change": change,
            "total_affection": total_affection,
            "message": f"你邀请 {character_name} 一起去{activity_name}。好感度 {'+' if change >= 0 else ''}{change}",
        }

    # ==================== 日常对话 ====================

    def process_daily_talk(self, character_name: str, message: str) -> dict[str, Any]:
        """处理日常对话交互。

        从玩家消息中检测关键词，同时扫描是否包含可记录为线索的信息。

        Args:
            character_name: 目标角色名称。
            message: 玩家发送的对话内容。

        Returns:
            处理结果，包含检测到的关键词和发现的线索数量。
        """
        # 简单的关键词反应检测
        keywords_found: list[str] = []
        for keyword in ["你好", "早安", "晚安", "今天", "天气", "开心", "难过"]:
            if keyword in message:
                keywords_found.append(keyword)

        # 扫描文本中的角色喜好线索
        clues_found = 0
        if self._notebook:
            new_clues = self._notebook.scan_text_for_clues(message, character_name)
            clues_found = len(new_clues)

        return {
            "keywords": keywords_found,
            "clues_discovered": clues_found,
            "message": f"你和 {character_name} 进行了日常对话。",
        }

    # ==================== 状态管理 ====================

    def load_state(self, data: dict[str, Any]) -> None:
        """从存档数据加载互动状态。

        Args:
            data: 包含 inventory 键的字典。
        """
        self._player_inventory = data.get("inventory", [])

    def dump_state(self) -> dict[str, Any]:
        """导出互动状态用于存档。

        Returns:
            包含玩家背包库存的可序列化字典。
        """
        return {"inventory": list(self._player_inventory)}
