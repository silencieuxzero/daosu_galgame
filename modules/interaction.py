"""互动行为系统模块。

实现多样化的玩家-角色互动功能：
- 礼物赠送系统：选择物品赠送给角色
- 邀约功能：邀请角色参与特定活动
- 日常对话：自由对话交互界面
所有互动行为均关联好感度系统。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GiftItem:
    """礼物物品定义。"""

    name: str  # 礼物名称
    description: str  # 礼物描述
    category: str  # 礼物类别（food, book, accessory, decoration, etc.）
    base_affection: int = 0  # 基础好感度加成
    tags: list[str] = field(default_factory=list)  # 标签（用于匹配角色喜好）

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "base_affection": self.base_affection,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GiftItem:
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=data.get("category", "other"),
            base_affection=data.get("base_affection", 0),
            tags=data.get("tags", []),
        )


@dataclass
class Activity:
    """活动定义。"""

    name: str  # 活动名称
    description: str  # 活动描述
    category: str  # 活动类别（date, adventure, relax, study, etc.）
    base_affection: int = 0  # 基础好感度加成
    duration: str = "short"  # 持续时间（short, medium, long）
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
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
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=data.get("category", "other"),
            base_affection=data.get("base_affection", 0),
            duration=data.get("duration", "short"),
            tags=data.get("tags", []),
        )


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

    管理礼物赠送、邀约活动和日常对话等玩家-角色互动。
    """

    def __init__(self, affection_manager: Any, notebook_manager: Any | None = None) -> None:
        """
        Args:
            affection_manager: 好感度管理器实例。
            notebook_manager: 可选，记事本管理器实例（用于线索联动）。
        """
        self._affection = affection_manager
        self._notebook = notebook_manager
        self._gifts: dict[str, GiftItem] = {g.name: g for g in DEFAULT_GIFTS}
        self._activities: dict[str, Activity] = {a.name: a for a in DEFAULT_ACTIVITIES}
        self._player_inventory: list[str] = []  # 玩家拥有的礼物列表

    def set_notebook_manager(self, nb_mgr: Any) -> None:
        """注入记事本管理器（联动）。"""
        self._notebook = nb_mgr

    # ==================== 礼物系统 ====================

    def list_available_gifts(self) -> list[GiftItem]:
        """获取玩家可赠送的礼物列表。"""
        return [self._gifts[name] for name in self._player_inventory if name in self._gifts]

    def add_gift_to_inventory(self, gift_name: str) -> bool:
        """添加礼物到玩家背包。

        Args:
            gift_name: 礼物名称。

        Returns:
            是否成功添加。
        """
        if gift_name in self._gifts:
            self._player_inventory.append(gift_name)
            return True
        return False

    def add_all_default_gifts(self) -> None:
        """将所有默认礼物添加到玩家背包（测试/初始化用）。"""
        for name in self._gifts:
            if name not in self._player_inventory:
                self._player_inventory.append(name)

    def give_gift(self, character_name: str, gift_name: str) -> dict[str, Any]:
        """赠送礼物给指定角色。

        根据礼物属性和角色偏好计算好感度变动。
        如果有关联的记事本，会查询线索提示。

        Args:
            character_name: 目标角色。
            gift_name: 礼物名称。

        Returns:
            互动结果字典：
            {
                "success": bool,
                "affection_change": int,
                "total_affection": int,
                "message": str,
                "hint": str | None,
            }
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

        # 从背包中移除礼物
        self._player_inventory.remove(gift_name)

        # 计算好感度变动
        change = gift.base_affection
        total_affection = self._affection.modify(character_name, change)

        # 查询线索提示
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
        """获取可邀约的活动列表。"""
        return list(self._activities.values())

    def invite(self, character_name: str, activity_name: str) -> dict[str, Any]:
        """邀请角色参加活动。

        根据活动和角色关系计算好感度变动。

        Args:
            character_name: 目标角色。
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
        """处理日常对话。

        分析消息内容，检测是否包含喜好线索并记录到记事本。

        Args:
            character_name: 目标角色。
            message: 玩家发送的对话内容。

        Returns:
            处理结果。
        """
        # 简单的关键词反应
        keywords_found: list[str] = []
        for keyword in ["你好", "早安", "晚安", "今天", "天气", "开心", "难过"]:
            if keyword in message:
                keywords_found.append(keyword)

        # 扫描线索
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
        """从存档数据加载互动状态。"""
        self._player_inventory = data.get("inventory", [])

    def dump_state(self) -> dict[str, Any]:
        """导出互动状态用于存档。"""
        return {"inventory": list(self._player_inventory)}
