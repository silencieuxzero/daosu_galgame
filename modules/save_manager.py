"""存档管理模块。

实现完整的存档/读档系统，支持玩家进度保存。
存档内容包括：当前剧情节点、角色好感度数据、玩家选择记录、记事本内容等。
采用 JSON 格式存储，确保数据完整性与读写效率。

存档文件存储于 data/saves/ 目录下，每个槽位对应一个独立 JSON 文件。
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
    """单个存档槽位。

    包含游戏运行所需的全部可序列化状态，是存档的最小读写单元。

    Attributes:
        slot_id: 存档槽位编号（从 1 开始）。
        timestamp: 保存时间，ISO 格式字符串。
        label: 用户自定义标签。
        game_state: 保存时的游戏 FSM 状态名。
        current_script: 当前对话脚本 ID。
        current_node: 当前对话节点 ID。
        affection_data: 好感度管理器导出的状态。
        choice_history: 玩家选择记录列表。
        metadata: 额外元数据，可扩展。
    """

    slot_id: int
    timestamp: str
    label: str = ""
    game_state: str = "IDLE"
    current_script: str | None = None
    current_node: str | None = None
    affection_data: dict[str, dict[str, Any]] = field(default_factory=dict)
    choice_history: list[dict[str, Any]] = field(default_factory=list)
    completed_scripts: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典，用于 JSON 序列化。

        Returns:
            可直接传给 json.dump 的字典。
        """
        return {
            "slot_id": self.slot_id,
            "timestamp": self.timestamp,
            "label": self.label,
            "game_state": self.game_state,
            "current_script": self.current_script,
            "current_node": self.current_node,
            "affection_data": self.affection_data,
            "choice_history": self.choice_history,
            "completed_scripts": self.completed_scripts,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SaveSlot:
        """从字典反序列化。

        Args:
            data: 存档数据的字典表示。

        Returns:
            反序列化后的 SaveSlot 实例。
        """
        return cls(
            slot_id=data.get("slot_id", 0),
            timestamp=data.get("timestamp", ""),
            label=data.get("label", ""),
            game_state=data.get("game_state", "IDLE"),
            current_script=data.get("current_script"),
            current_node=data.get("current_node"),
            affection_data=data.get("affection_data", {}),
            choice_history=data.get("choice_history", []),
            completed_scripts=data.get("completed_scripts", {}),
            metadata=data.get("metadata", {}),
        )


# 默认存档槽位数量
DEFAULT_SLOT_COUNT = 20

# 存档文件名模板，{0} 替换为两位数的槽位编号
SAVE_FILE_TEMPLATE = "save_{:02d}.json"


class SaveManager:
    """存档管理器。

    支持多槽位存档/读档，自动管理存档文件的生命周期。
    采用"先写临时文件再重命名"的原子写入策略，防止写中断导致存档损坏。

    Usage:
        mgr = SaveManager("data/saves")
        mgr.scan_slots()  # 扫描所有槽位
        mgr.save(1, label="初见", ...)  # 存档
        slot = mgr.load(1)  # 读档
    """

    def __init__(self, save_dir: str, slot_count: int = DEFAULT_SLOT_COUNT) -> None:
        """初始化存档管理器。

        Args:
            save_dir: 存档文件存放目录的绝对路径。
            slot_count: 最大存档槽位数量。
        """
        self._save_dir = save_dir
        self._slot_count = slot_count
        self._slots: dict[int, SaveSlot | None] = {}
        self._choice_history: list[dict[str, Any]] = []  # 当前会话的选择记录

    @property
    def save_dir(self) -> str:
        """获取存档目录路径。"""
        return self._save_dir

    def _slot_path(self, slot_id: int) -> str:
        """获取指定槽位的文件路径。

        Args:
            slot_id: 槽位编号。

        Returns:
            存档文件的完整路径。
        """
        return os.path.join(self._save_dir, SAVE_FILE_TEMPLATE.format(slot_id))

    def scan_slots(self) -> dict[int, SaveSlot | None]:
        """扫描所有存档槽位。

        读取每个槽位的文件并解析为 SaveSlot 对象，
        损坏的存档文件标记为 None。

        Returns:
            槽位编号到存档数据的映射。无存档或损坏的槽位返回 None。
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
        completed_scripts: dict[str, list[str]] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> SaveSlot:
        """保存游戏进度到指定槽位。

        使用原子写入策略：先写入 .tmp 临时文件，再重命名为正式文件。
        如果写入失败，临时文件会被清理，不会留下损坏的存档。

        Args:
            slot_id: 目标槽位编号（1 到 slot_count）。
            label: 存档标签，供玩家识别。
            game_state: 当前游戏状态名。
            current_script: 当前对话脚本 ID。
            current_node: 当前对话节点 ID。
            affection_data: 好感度管理器导出的数据。
            completed_scripts: 剧情进度数据（角色 -> 已完成脚本列表）。
            extra_metadata: 额外元数据。

        Returns:
            创建的 SaveSlot 对象。

        Raises:
            SaveDataError: 槽位编号无效或写入失败时抛出。
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
            choice_history=list(self._choice_history),
            completed_scripts=completed_scripts or {},
            metadata=extra_metadata or {},
        )

        filepath = self._slot_path(slot_id)

        # 原子写入：先写临时文件再重命名
        # 防止写入过程中断导致存档文件损坏
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

        读取并解析存档文件，恢复选择记录到当前会话。

        Args:
            slot_id: 槽位编号。

        Returns:
            存档数据的 SaveSlot 对象。

        Raises:
            SaveDataError: 槽位无效、存档不存在或文件损坏时抛出。
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
        """删除指定槽位的存档文件。

        Args:
            slot_id: 要删除的槽位编号。
        """
        filepath = self._slot_path(slot_id)
        if os.path.isfile(filepath):
            os.remove(filepath)
        self._slots[slot_id] = None

    def get_slot_info(self, slot_id: int) -> SaveSlot | None:
        """获取指定槽位的存档概要信息。

        从缓存或磁盘读取槽位信息，不修改当前会话状态。

        Args:
            slot_id: 槽位编号。

        Returns:
            存档的 SaveSlot 对象，不存在或损坏时返回 None。
        """
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
        """获取最大槽位数。

        Returns:
            存档管理器支持的最大槽位数量。
        """
        return self._slot_count

    def add_choice_record(self, choice: dict[str, Any]) -> None:
        """记录玩家选择。

        将一次选择追加到当前会话的选择历史中，
        存档时这些记录会一并保存。

        Args:
            choice: 选择记录字典，包含 node_id、choice_index 等字段。
        """
        self._choice_history.append(choice)

    def get_choice_history(self) -> list[dict[str, Any]]:
        """获取当前会话的选择记录。

        Returns:
            选择记录字典列表。
        """
        return list(self._choice_history)

    def clear_choice_history(self) -> None:
        """清空当前会话的选择记录。"""
        self._choice_history.clear()

    def get_latest_save(self) -> SaveSlot | None:
        """获取所有槽位中最近一次存档。

        扫描所有槽位，按 timestamp 字段比较，返回时间最新的存档。
        无存档时返回 None。

        Returns:
            最新的 SaveSlot，无存档则返回 None。
        """
        self.scan_slots()
        latest: SaveSlot | None = None
        for slot in self._slots.values():
            if slot is None:
                continue
            if latest is None or slot.timestamp > latest.timestamp:
                latest = slot
        return latest

    def is_first_time(self) -> bool:
        """检测玩家是否首次游玩。

        通过扫描所有存档槽位判断，当所有槽位均为空时视为首次游玩。
        可用于触发新手引导、开场剧情等首次进入逻辑。

        Returns:
            如果所有存档槽位均无有效存档返回 True，否则 False。
        """
        self.scan_slots()
        return all(slot is None for slot in self._slots.values())
