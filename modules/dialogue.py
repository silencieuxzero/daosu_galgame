"""对话系统模块。

管理剧情对话流程，包括对话脚本加载、选项分支处理、
以及情绪状态检测（如"倾诉烦恼"状态）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from ..core.exceptions import DialogueScriptError


@dataclass
class DialogueNode:
    """对话节点。"""

    node_id: str  # 节点唯一标识
    speaker: str  # 说话者（角色名或 " narrator" 表示旁白）
    text: str  # 对话文本（支持模板变量如 {player_name}）
    emotion: str = "neutral"  # 说话情绪
    choices: list[DialogueChoice] = field(default_factory=list)  # 玩家选项
    next_node: str | None = None  # 自动跳转的下一个节点 ID
    conditions: dict[str, Any] = field(default_factory=dict)  # 触发条件

    def has_choices(self) -> bool:
        """是否有选项分支。"""
        return len(self.choices) > 0

    def is_venting(self) -> bool:
        """检测是否为倾诉烦恼状态。"""
        return self.emotion in ("sad", "anxious", "frustrated", "venting")


@dataclass
class DialogueChoice:
    """对话选项。"""

    text: str  # 选项显示文本
    next_node: str  # 选择后跳转的节点 ID
    option_id: str | None = None  # 关联的好感度规则选项 ID
    affection_change: int = 0  # 直接好感度变动
    conditions: dict[str, Any] = field(default_factory=dict)  # 触发条件


@dataclass
class DialogueScript:
    """对话脚本。

    包含一系列对话节点，构成一个完整的对话场景。
    """

    script_id: str  # 脚本 ID
    title: str  # 脚本标题
    start_node: str  # 起始节点 ID
    characters: list[str] = field(default_factory=list)  # 参与角色
    nodes: dict[str, DialogueNode] = field(default_factory=dict)  # 节点映射
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据


class DialogueManager:
    """对话管理器。

    负责加载对话脚本、管理对话流程推进、追踪当前对话状态。
    """

    def __init__(self, events_dir: str) -> None:
        """
        Args:
            events_dir: 事件/对话脚本目录。
        """
        self._events_dir = events_dir
        self._scripts: dict[str, DialogueScript] = {}
        self._current_script: DialogueScript | None = None
        self._current_node: DialogueNode | None = None
        self._visited_nodes: set[str] = set()
        self._script_loaded = False

    def load_all_scripts(self) -> None:
        """从磁盘加载所有对话脚本。"""
        self._scripts.clear()
        if not os.path.isdir(self._events_dir):
            return

        for filename in os.listdir(self._events_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self._events_dir, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = json.load(f)
                script = self._parse_script(data)
                self._scripts[script.script_id] = script
            except (json.JSONDecodeError, IOError, DialogueScriptError) as e:
                print(f"[VisualNovel] 加载脚本失败 {filename}: {e}")

        self._script_loaded = True

    def reload(self) -> None:
        """重新加载所有脚本。"""
        self.load_all_scripts()

    def _parse_script(self, data: dict[str, Any]) -> DialogueScript:
        """解析 JSON 数据为 DialogueScript 对象。"""
        script_id = data.get("script_id")
        if not script_id:
            raise DialogueScriptError("脚本缺少 script_id 字段")

        nodes_data = data.get("nodes", {})
        nodes: dict[str, DialogueNode] = {}

        for node_id, node_data in nodes_data.items():
            choices_data = node_data.get("choices", [])
            choices = [
                DialogueChoice(
                    text=c.get("text", ""),
                    next_node=c.get("next_node", ""),
                    option_id=c.get("option_id"),
                    affection_change=c.get("affection_change", 0),
                    conditions=c.get("conditions", {}),
                )
                for c in choices_data
            ]

            nodes[node_id] = DialogueNode(
                node_id=node_id,
                speaker=node_data.get("speaker", "narrator"),
                text=node_data.get("text", ""),
                emotion=node_data.get("emotion", "neutral"),
                choices=choices,
                next_node=node_data.get("next_node"),
                conditions=node_data.get("conditions", {}),
            )

        return DialogueScript(
            script_id=script_id,
            title=data.get("title", ""),
            start_node=data.get("start_node", ""),
            characters=data.get("characters", []),
            nodes=nodes,
            metadata=data.get("metadata", {}),
        )

    def start_script(self, script_id: str) -> DialogueNode | None:
        """开始一个对话脚本。

        Args:
            script_id: 脚本 ID。

        Returns:
            起始对话节点，如果脚本不存在则返回 None。
        """
        if not self._script_loaded:
            self.load_all_scripts()

        script = self._scripts.get(script_id)
        if script is None:
            return None

        self._current_script = script
        self._visited_nodes.clear()
        return self._go_to_node(script.start_node)

    def _go_to_node(self, node_id: str) -> DialogueNode | None:
        """跳转到指定节点。"""
        if self._current_script is None:
            return None

        node = self._current_script.nodes.get(node_id)
        if node is None:
            return None

        self._current_node = node
        self._visited_nodes.add(node_id)
        return node

    def choose(self, choice_index: int) -> DialogueNode | None:
        """玩家选择选项后推进对话。

        Args:
            choice_index: 选项索引（从 0 开始）。

        Returns:
            选择后跳转到的节点，如果无效则返回 None。
        """
        if self._current_node is None or not self._current_node.has_choices():
            return None

        if choice_index < 0 or choice_index >= len(self._current_node.choices):
            return None

        choice = self._current_node.choices[choice_index]
        return self._go_to_node(choice.next_node)

    def advance(self) -> DialogueNode | None:
        """自动推进到下一个节点。

        仅当当前节点没有选项分支且有 next_node 时有效。
        """
        if self._current_node is None:
            return None

        if self._current_node.has_choices():
            return None  # 有选项时需玩家选择

        next_id = self._current_node.next_node
        if next_id is None:
            return None  # 对话结束

        return self._go_to_node(next_id)

    def get_current_node(self) -> DialogueNode | None:
        """获取当前对话节点。"""
        return self._current_node

    def get_current_script(self) -> DialogueScript | None:
        """获取当前对话脚本。"""
        return self._current_script

    def is_current_node_venting(self) -> bool:
        """检测当前节点是否为倾诉烦恼状态。"""
        return self._current_node is not None and self._current_node.is_venting()

    def end_current(self) -> None:
        """结束当前对话。"""
        self._current_script = None
        self._current_node = None

    def get_script(self, script_id: str) -> DialogueScript | None:
        """获取指定脚本（不启动）。"""
        if not self._script_loaded:
            self.load_all_scripts()
        return self._scripts.get(script_id)

    def list_scripts(self) -> list[str]:
        """获取所有可用脚本 ID 列表。"""
        if not self._script_loaded:
            self.load_all_scripts()
        return list(self._scripts.keys())
