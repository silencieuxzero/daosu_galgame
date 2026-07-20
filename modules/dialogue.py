"""对话系统模块。

管理剧情对话流程，包括对话脚本加载、选项分支处理、
以及情绪状态检测（如"倾诉烦恼"状态）。

对话脚本以 JSON 格式存储于 data/events/ 目录下，
采用节点图结构，支持线性推进和分支选择。
每个脚本由一系列节点（DialogueNode）构成，节点通过 next_node 或 choices 连接。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from ..core.exceptions import DialogueScriptError
from ..core.json_utils import strip_json_comments as _strip_json_comments


@dataclass
class DialogueChoice:
    """对话选项。

    代表玩家在当前对话节点可以做出的一个选择。

    Attributes:
        text: 选项显示文本，展示给玩家。
        next_node: 选择后跳转的目标节点 ID。
        option_id: 关联的好感度规则选项 ID，用于匹配 AffectionRule。
        affection_change: 直接好感度变动量（不经过性格计算）。
        conditions: 该选项的触发条件字典，用于条件性显示。
    """

    text: str
    next_node: str
    option_id: str | None = None
    affection_change: int = 0
    conditions: dict[str, Any] = field(default_factory=dict)


@dataclass
class DialogueNode:
    """对话节点。

    对话脚本的基本组成单元，代表一次对话回合。
    节点通过 next_node（线性推进）或 choices（分支选择）连接到下一个节点。

    Attributes:
        node_id: 节点唯一标识，在同一脚本内唯一。
        speaker: 说话者名称，使用 "narrator" 表示旁白。
        text: 对话文本，支持模板变量如 {player_name}。
        emotion: 说话时伴随的情绪标签（neutral, happy, sad, anxious 等）。
        choices: 玩家可选分支列表。为空表示无分支，由 next_node 自动推进。
        next_node: 无分支时的自动跳转目标节点 ID。None 表示对话结束。
        conditions: 节点触发条件字典。
    """

    node_id: str
    speaker: str
    text: str
    emotion: str = "neutral"
    choices: list[DialogueChoice] = field(default_factory=list)
    next_node: str | None = None
    conditions: dict[str, Any] = field(default_factory=dict)

    def has_choices(self) -> bool:
        """当前节点是否有选项分支。

        Returns:
            存在至少一个选项时返回 True。
        """
        return len(self.choices) > 0

    def is_venting(self) -> bool:
        """检测当前节点是否为倾诉烦恼状态。

        当节点的 emotion 标签为 sad、anxious、frustrated 或 venting 时，
        判定角色处于需要被倾听的状态，UI 层会动态添加"静静听着"选项。

        Returns:
            如果是倾诉烦恼状态返回 True。
        """
        return self.emotion in ("sad", "anxious", "frustrated", "venting")


@dataclass
class DialogueScript:
    """对话脚本。

    包含一系列对话节点，构成一个完整的剧情对话场景。

    Attributes:
        script_id: 脚本唯一标识，对应 JSON 中的 script_id 字段。
        title: 脚本标题，用于展示。
        start_node: 脚本的起始节点 ID。
        characters: 该脚本中登场的角色名称列表。
        nodes: 节点 ID 到 DialogueNode 的映射字典。
        metadata: 额外元数据，如作者、版本等。
    """

    script_id: str
    title: str
    start_node: str
    characters: list[str] = field(default_factory=list)
    nodes: dict[str, DialogueNode] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class DialogueManager:
    """对话管理器。

    负责加载对话脚本、管理对话流程推进、追踪当前对话状态。
    支持同时管理多个脚本，但同一时间只能处于一个活跃对话中。

    Usage:
        mgr = DialogueManager("data/events")
        mgr.load_all_scripts()
        node = mgr.start_script("flower_shop_encounter")
        # 如果没有选项，自动推进
        next_node = mgr.advance()
        # 如果有选项，让玩家选择
        next_node = mgr.choose(0)
    """

    def __init__(self, events_dir: str) -> None:
        """初始化对话管理器。

        Args:
            events_dir: 事件/对话脚本目录的绝对路径。
        """
        self._events_dir = events_dir
        self._scripts: dict[str, DialogueScript] = {}
        self._current_script: DialogueScript | None = None  # 当前活跃脚本
        self._current_node: DialogueNode | None = None      # 当前所在节点
        self._visited_nodes: set[str] = set()               # 本次对话已访问的节点集合
        self._script_loaded = False

    def load_all_scripts(self) -> None:
        """从磁盘加载所有对话脚本。

        扫描 events_dir 下所有 .json 文件，逐一解析为 DialogueScript 对象并缓存。
        加载失败的脚本会打印错误日志，不影响其他脚本的加载。
        """
        self._scripts.clear()
        if not os.path.isdir(self._events_dir):
            return

        for filename in os.listdir(self._events_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self._events_dir, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    content = f.read()
                data = json.loads(_strip_json_comments(content))
                script = self._parse_script(data)
                self._scripts[script.script_id] = script
            except (json.JSONDecodeError, IOError, DialogueScriptError) as e:
                print(f"[VisualNovel] 加载脚本失败 {filename}: {e}")

        self._script_loaded = True

    def reload(self) -> None:
        """重新加载所有脚本。

        在插件运行时配置更新后调用。
        """
        self.load_all_scripts()

    def _parse_script(self, data: dict[str, Any]) -> DialogueScript:
        """解析 JSON 数据为 DialogueScript 对象。

        遍历 JSON 中的 nodes 字段，将每个节点数据转换为 DialogueNode 对象，
        同时将 choices 转换为 DialogueChoice 对象列表。

        Args:
            data: 从 JSON 解析出的原始字典。

        Returns:
            构建好的 DialogueScript 实例。

        Raises:
            DialogueScriptError: 如果缺少必需的 script_id 字段。
        """
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

        设置指定脚本为当前活跃脚本，清除上次对话的访问记录，
        定位到脚本的起始节点并返回。

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
        """跳转到指定节点。

        内部工具方法，更新 current_node 并将节点 ID 记录到已访问集合。

        Args:
            node_id: 目标节点 ID。

        Returns:
            目标节点，如果不存在则返回 None。
        """
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
            选择后跳转到的节点，如果当前没有选项或索引无效则返回 None。
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
        如果当前节点有选项分支（需玩家选择）、或 next_node 为 None（对话结束），则返回 None。

        Returns:
            下一个对话节点，无法推进时返回 None。
        """
        if self._current_node is None:
            return None

        if self._current_node.has_choices():
            return None  # 有选项时需玩家选择，不能自动推进

        next_id = self._current_node.next_node
        if next_id is None:
            return None  # 对话结束

        return self._go_to_node(next_id)

    def get_current_node(self) -> DialogueNode | None:
        """获取当前对话节点。

        Returns:
            当前节点，如果没有活跃对话则返回 None。
        """
        return self._current_node

    def get_current_script(self) -> DialogueScript | None:
        """获取当前对话脚本。

        Returns:
            当前脚本，如果没有活跃对话则返回 None。
        """
        return self._current_script

    def is_current_node_venting(self) -> bool:
        """检测当前节点是否为倾诉烦恼状态。

        用于 UI 层判断是否需要在选项列表中动态添加"静静听着"选项。

        Returns:
            如果当前节点是倾诉烦恼状态返回 True。
        """
        return self._current_node is not None and self._current_node.is_venting()

    def end_current(self) -> None:
        """结束当前对话。

        清除当前脚本和节点引用，重置对话状态。
        """
        self._current_script = None
        self._current_node = None

    def get_script(self, script_id: str) -> DialogueScript | None:
        """获取指定脚本（不启动对话）。

        Args:
            script_id: 脚本 ID。

        Returns:
            脚本对象，不存在时返回 None。
        """
        if not self._script_loaded:
            self.load_all_scripts()
        return self._scripts.get(script_id)

    def list_scripts(self) -> list[str]:
        """获取所有可用脚本 ID 列表。

        Returns:
            脚本 ID 列表，如 ["flower_shop_encounter", "teahouse_fish_encounter"]。
        """
        if not self._script_loaded:
            self.load_all_scripts()
        return list(self._scripts.keys())
