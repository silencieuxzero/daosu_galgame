"""存档管理模块。

实现完整的存档/读档系统，支持玩家进度保存。
存档内容包括：当前剧情节点、角色好感度数据、玩家选择记录、记事本内容等。
采用 JSON 格式存储，确保数据完整性与读写效率。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..core.exceptions import SaveDataError


@dataclass
class SaveSlot:
    """单个存档槽位。"""

    slot_id: int  # 存档槽位编号
    timestamp: str  # 保存时间 ISO 格式
    label: str = ""  # 用户自定义标签
    game_state: str = "IDLE"  # 当前游戏状态
    current_script: str | None = None  # 当前对话脚本 ID
    current_node: str | None = None  # 当前对话节点 ID
    affection_data: dict[str, dict[str, Any]] = field(default_factory=dict)  # 好感度数据
    notebook_data: list[dict[str, Any]] = field(default_factory=list)  # 记事本数据
    interaction_data: dict[str, Any] = field(default_factory=dict)  # 互动数据
    choice_history: list[dict[str, Any]] = field(default_factory=list)  # 玩家选择记录
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "slot_id": self.slot_id,
            "timestamp": self.timestamp,
            "label": self.label,
            "game_state": self.game_state,
            "current_script": self.current_script,
            "current_node": self.current_node,
            "affection_data": self.affection_data,
            "notebook_data": self.notebook_data,
            "interaction_data": self.interaction_data,
            "choice_history": self.choice_history,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SaveSlot:
        """从字典反序列化。"""
        return cls(
            slot_id=data.get("slot_id", 0),
            timestamp=data.get("timestamp", ""),
            label=data.get("label", ""),
            game_state=data.get("game_state", "IDLE"),
            current_script=data.get("current_script"),
            current_node=data.get("current_node"),
            affection_data=data.get("affection_data", {}),
            notebook_data=data.get("notebook_data", []),
            interaction_data=data.get("interaction_data", {}),
            choice_history=data.get("choice_history", []),
            metadata=data.get("metadata", {}),
        )


# 默认存档槽位数量
DEFAULT_SLOT_COUNT = 20

# 存档文件名模板
SAVE_FILE_TEMPLATE = "save_{:02d}.json"


class SaveManager:
    """存档管理器。

    支持多槽位存档/读档，自动管理存档文件的生命周期。
    JSON 持久化存储。
    """

    def __init__(self, save_dir: str, slot_count: int = DEFAULT_SLOT_COUNT) -> None:
        """
        Args:
            save_dir: 存档文件存放目录。
            slot_count: 存档槽位数量。
        """
        self._save_dir = save_dir
        self._slot_count = slot_count
        self._slots: dict[int, SaveSlot | None] = {}
        self._choice_history: list[dict[str, Any]] = []  # 当前会话选择记录

    @property
    def save_dir(self) -> str:
        return self._save_dir

    def _slot_path(self, slot_id: int) -> str:
        """获取指定槽位的文件路径。"""
        return os.path.join(self._save_dir, SAVE_FILE_TEMPLATE.format(slot_id))

    def scan_slots(self) -> dict[int, SaveSlot | None]:
        """扫描所有存档槽位，返回槽位编号到存档数据的映射。

        不存在的槽位返回 None。
        """
        os.makedirs(self._save_dir, exist_ok=True)
        self._slots.clear()

        for slot_id in range(1, self._slot_count + 1):
            filepath = self._slot_path(slot_id)
            if os.path.isfile(filepath):
                try:
                    with open(filepath, encoding="utf-8") as f:
                        data = json.load(f)
                    self._slots[slot_id] = SaveSlot.from_dict(data)
                except (json.JSONDecodeError, IOError):
                    # 损坏的存档标记为 None
                    self._slots[slot_id] = None
            else:
                self._slots[slot_id] = None

        return dict(self._slots)

    def save(
        self,
        slot_id: int,
        *,
        label: str = "",
        game_state: str = "IDLE",
        current_script: str | None = None,
        current_node: str | None = None,
        affection_data: dict[str, dict[str, Any]] | None = None,
        notebook_data: list[dict[str, Any]] | None = None,
        interaction_data: dict[str, Any] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> SaveSlot:
        """保存游戏进度到指定槽位。

        Args:
            slot_id: 目标槽位编号（1 开始）。
            label: 存档标签。
            game_state: 当前游戏状态。
            current_script: 当前对话脚本 ID。
            current_node: 当前对话节点 ID。
            affection_data: 好感度数据。
            notebook_data: 记事本数据。
            interaction_data: 互动数据。
            extra_metadata: 额外元数据。

        Returns:
            创建的存档对象。

        Raises:
            SaveDataError: 保存失败时抛出。
        """
        if slot_id < 1 or slot_id > self._slot_count:
            raise SaveDataError(f"存档槽位编号无效：{slot_id}（有效范围：1-{self._slot_count}）")

        os.makedirs(self._save_dir, exist_ok=True)

        slot = SaveSlot(
            slot_id=slot_id,
            timestamp=datetime.now().isoformat(),
            label=label,
            game_state=game_state,
            current_script=current_script,
            current_node=current_node,
            affection_data=affection_data or {},
            notebook_data=notebook_data or [],
            interaction_data=interaction_data or {},
            choice_history=list(self._choice_history),
            metadata=extra_metadata or {},
        )

        filepath = self._slot_path(slot_id)

        # 原子写入：先写临时文件再重命名
        tmp_path = filepath + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(slot.to_dict(), f, ensure_ascii=False, indent=2)
            shutil.move(tmp_path, filepath)
        except (IOError, OSError) as e:
            # 清理临时文件
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
            raise SaveDataError(f"保存存档失败（槽位 {slot_id}）: {e}") from e

        self._slots[slot_id] = slot
        return slot

    def load(self, slot_id: int) -> SaveSlot:
        """从指定槽位加载存档。

        Args:
            slot_id: 槽位编号。

        Returns:
            存档数据。

        Raises:
            SaveDataError: 存档不存在或损坏时抛出。
        """
        if slot_id < 1 or slot_id > self._slot_count:
            raise SaveDataError(f"存档槽位编号无效：{slot_id}")

        filepath = self._slot_path(slot_id)
        if not os.path.isfile(filepath):
            raise SaveDataError(f"槽位 {slot_id} 没有存档。")

        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            slot = SaveSlot.from_dict(data)
            self._choice_history = list(slot.choice_history)
            self._slots[slot_id] = slot
            return slot
        except (json.JSONDecodeError, IOError) as e:
            raise SaveDataError(f"加载存档失败（槽位 {slot_id}）: {e}") from e

    def delete_slot(self, slot_id: int) -> None:
        """删除指定槽位的存档。"""
        filepath = self._slot_path(slot_id)
        if os.path.isfile(filepath):
            os.remove(filepath)
        self._slots[slot_id] = None

    def get_slot_info(self, slot_id: int) -> SaveSlot | None:
        """获取指定槽位的存档信息（不反序列化完整数据）。"""
        if slot_id in self._slots:
            return self._slots[slot_id]

        filepath = self._slot_path(slot_id)
        if not os.path.isfile(filepath):
            return None

        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            slot = SaveSlot.from_dict(data)
            self._slots[slot_id] = slot
            return slot
        except (json.JSONDecodeError, IOError):
            return None

    def get_slot_count(self) -> int:
        """获取最大槽位数。"""
        return self._slot_count

    def add_choice_record(self, choice: dict[str, Any]) -> None:
        """记录玩家选择。

        用于存档中的选择记录，便于回放和统计。
        """
        self._choice_history.append(choice)

    def get_choice_history(self) -> list[dict[str, Any]]:
        """获取当前会话的选择记录。"""
        return list(self._choice_history)

    def clear_choice_history(self) -> None:
        """清空选择记录。"""
        self._choice_history.clear()

    def get_latest_save(self) -> SaveSlot | None:
        """获取最近一次的存档。"""
        self.scan_slots()
        latest: SaveSlot | None = None
        for slot in self._slots.values():
            if slot is None:
                continue
            if latest is None or slot.timestamp > latest.timestamp:
                latest = slot
        return latest
