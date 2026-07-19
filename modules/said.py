"""分段式剧情对话模块（Said Dialogue Engine）。

实现 "/dsv said" 命令配套的分段式交互对话功能：
- 加载角色专属的 JSON 剧情脚本
- 分段展示剧情内容，每段结束后提供 2-4 个选择项
- 用户选择后根据选项影响好感度
- 支持退出对话模式

JSON 数据文件存储于 data/said/ 目录下，
使用与 dialogue 模块相同的节点图结构，但独立管理脚本目录。

Usage:
    mgr = SaidManage("data/said", affection_manager)
    mgr.load_all_scripts()
    result = mgr.start_script("said_luoshulv")
    result = mgr.make_choice(0)
    result = mgr.end_dialogue()
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


def _strip_json_comments(json_str: str) -> str:
    """移除 JSON 中的 // 和 /* */ 注释（仅在字符串外部）。

    复用与 character.py 相同的实现逻辑，避免跨模块依赖。

    Args:
        json_str: 可能包含注释的原始 JSON 字符串。

    Returns:
        移除注释后的纯净 JSON 字符串。
    """
    import re

    no_block = re.sub(r'/\*[\s\S]*?\*/', '', json_str)
    result: list[str] = []
    i = 0
    in_string = False
    while i < len(no_block):
        c = no_block[i]
        if c == '"' and (i == 0 or no_block[i - 1] != '\\'):
            in_string = not in_string
            result.append(c)
            i += 1
        elif not in_string and c == '/' and i + 1 < len(no_block) and no_block[i + 1] == '/':
            while i < len(no_block) and no_block[i] != '\n':
                i += 1
        else:
            result.append(c)
            i += 1
    return ''.join(result)


@dataclass
class SaidChoice:
    """对话选项。

    Attributes:
        text: 选项显示文本。
        next_node: 选择后跳转的目标节点 ID。
        affection_change: 好感度变化量。
    """

    text: str
    next_node: str
    affection_change: int = 0


@dataclass
class SaidNode:
    """剧情对话节点。

    Attributes:
        node_id: 节点唯一标识。
        text: 剧情文本内容。
        speaker: 说话者（"narrator" 表示旁白）。
        emotion: 情绪标签。
        choices: 可选分支列表（空表示无分支）。
        next_node: 无分支时的自动跳转目标（None 表示对话结束）。
    """

    node_id: str
    text: str
    speaker: str = "narrator"
    emotion: str = "neutral"
    choices: list[SaidChoice] = field(default_factory=list)
    next_node: str | None = None

    def has_choices(self) -> bool:
        """当前节点是否有选项分支。"""
        return len(self.choices) > 0


@dataclass
class SaidScript:
    """分段式剧情脚本。

    Attributes:
        script_id: 脚本唯一标识。
        character_name: 关联的角色名称。
        title: 脚本标题。
        start_node: 起始节点 ID。
        nodes: 节点 ID 到 SaidNode 的映射。
    """

    script_id: str
    character_name: str
    title: str
    start_node: str
    nodes: dict[str, SaidNode] = field(default_factory=dict)


class SaidManager:
    """分段式剧情对话管理器。

    独立于 DialogueManager 管理 said 脚本，支持：
    - 加载/重新加载角色专属 said 脚本
    - 启动/推进/选择/结束对话
    - 与好感度系统联动
    """

    def __init__(self, said_dir: str, affection_manager: Any | None = None) -> None:
        """初始化 said 管理器。

        Args:
            said_dir: data/said/ 目录的绝对路径。
            affection_manager: 好感度管理器实例，用于选项好感度计算。
        """
        self._said_dir = said_dir
        self._affection = affection_manager
        self._scripts: dict[str, SaidScript] = {}
        self._current_script: SaidScript | None = None
        self._current_node: SaidNode | None = None
        self._script_loaded = False

    def set_affection_manager(self, mgr: Any) -> None:
        """设置好感度管理器引用。

        Args:
            mgr: AffectionManager 实例。
        """
        self._affection = mgr

    def load_all_scripts(self) -> None:
        """从磁盘加载所有 said 脚本。"""
        self._scripts.clear()
        if not os.path.isdir(self._said_dir):
            return

        for filename in os.listdir(self._said_dir):
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self._said_dir, filename)
            try:
                with open(filepath, encoding="utf-8") as f:
                    content = f.read()
                data = json.loads(_strip_json_comments(content))
                script = self._parse_script(data)
                self._scripts[script.script_id] = script
            except (json.JSONDecodeError, IOError) as e:
                print(f"[VisualNovel][Said] 加载脚本失败 {filename}: {e}")

        self._script_loaded = True

    def reload(self) -> None:
        """重新加载所有脚本。"""
        self.load_all_scripts()

    def _parse_script(self, data: dict[str, Any]) -> SaidScript:
        """解析 JSON 数据为 SaidScript 对象。

        Args:
            data: 从 JSON 解析出的原始字典。

        Returns:
            构建好的 SaidScript 实例。
        """
        script_id = data.get("script_id", "")
        character_name = data.get("character_name", "")
        title = data.get("title", "")
        start_node = data.get("start_node", "")

        nodes_data = data.get("nodes", {})
        nodes: dict[str, SaidNode] = {}

        for node_id, node_data in nodes_data.items():
            choices_data = node_data.get("choices", [])
            choices = [
                SaidChoice(
                    text=c.get("text", ""),
                    next_node=c.get("next_node", ""),
                    affection_change=c.get("affection_change", 0),
                )
                for c in choices_data
            ]

            nodes[node_id] = SaidNode(
                node_id=node_id,
                text=node_data.get("text", ""),
                speaker=node_data.get("speaker", "narrator"),
                emotion=node_data.get("emotion", "neutral"),
                choices=choices,
                next_node=node_data.get("next_node"),
            )

        return SaidScript(
            script_id=script_id,
            character_name=character_name,
            title=title,
            start_node=start_node,
            nodes=nodes,
        )

    def get_script_for_character(self, character_name: str) -> SaidScript | None:
        """获取指定角色的 said 脚本（通过 character_name 匹配）。

        Args:
            character_name: 角色名称。

        Returns:
            匹配的脚本，不存在则返回 None。
        """
        if not self._script_loaded:
            self.load_all_scripts()
        for script in self._scripts.values():
            if script.character_name == character_name:
                return script
        return None

    def start_script_for_character(self, character_name: str) -> dict[str, Any]:
        """为指定角色启动 said 对话。

        Args:
            character_name: 角色名称。

        Returns:
            启动结果字典，包含起始节点或错误信息。
        """
        script = self.get_script_for_character(character_name)
        if script is None:
            return {"success": False, "message": f"角色 '{character_name}' 没有可用的剧情对话。"}

        self._current_script = script
        return self._go_to_node(script.start_node)

    def _go_to_node(self, node_id: str) -> dict[str, Any]:
        """跳转到指定节点并返回格式化结果。

        Args:
            node_id: 目标节点 ID。

        Returns:
            节点数据字典，包含文本、选项、好感度等信息。
        """
        if self._current_script is None:
            return {"success": False, "message": "当前没有活跃的 said 对话。"}

        node = self._current_script.nodes.get(node_id)
        if node is None:
            return {"success": False, "message": f"节点 '{node_id}' 不存在。"}

        self._current_node = node
        return self._format_node_output(node)

    def _format_node_output(self, node: SaidNode) -> dict[str, Any]:
        """格式化节点输出为统一字典。

        Args:
            node: 当前 SaidNode。

        Returns:
            格式化后的结果字典。
        """
        result: dict[str, Any] = {
            "success": True,
            "said_dialogue": True,
            "speaker": node.speaker,
            "text": node.text,
            "emotion": node.emotion,
            "node_id": node.node_id,
        }

        if node.has_choices():
            choices = [
                {
                    "index": i,
                    "text": c.text,
                    "affection_change": c.affection_change,
                }
                for i, c in enumerate(node.choices)
            ]
            result["choices"] = choices
            result["awaiting_choice"] = True

        if node.next_node is None and not node.has_choices():
            # 终点节点，标记对话结束
            result["dialogue_ended"] = True

        return result

    def make_choice(self, choice_index: int) -> dict[str, Any]:
        """玩家选择选项后推进 said 对话。

        应用好感度变化，跳转到下一节点。

        Args:
            choice_index: 选项索引（从 0 开始）。

        Returns:
            选择后的节点数据或错误信息。
        """
        if self._current_node is None:
            return {"success": False, "message": "当前没有活跃的 said 对话。"}

        if not self._current_node.has_choices():
            return {"success": False, "message": "当前节点没有选项。"}

        if choice_index < 0 or choice_index >= len(self._current_node.choices):
            return {"success": False, "message": f"无效的选项编号。请输入 0-{len(self._current_node.choices) - 1}。"}

        choice = self._current_node.choices[choice_index]

        # 应用好感度变化
        affection_change = choice.affection_change
        character_name = self._current_script.character_name if self._current_script else ""
        if self._affection and character_name and affection_change != 0:
            self._affection.modify(character_name, affection_change)
            total_affection = self._affection.get_value(character_name)
        else:
            character_name = ""
            total_affection = 0

        # 跳转到下一节点
        result = self._go_to_node(choice.next_node)

        # 将好感度信息附加到结果中
        result["affection_change"] = affection_change
        if character_name:
            result["character_name"] = character_name
            result["total_affection"] = total_affection

        return result

    def advance(self) -> dict[str, Any]:
        """自动推进到下一节点（无选项时使用）。

        Returns:
            下一节点数据或结束标记。
        """
        if self._current_node is None:
            return {"success": False, "message": "当前没有活跃的 said 对话。"}

        if self._current_node.has_choices():
            # 有选项时转为等待选择
            result = self._format_node_output(self._current_node)
            result["awaiting_choice"] = True
            return result

        next_id = self._current_node.next_node
        if next_id is None:
            return {"success": True, "said_dialogue": True, "dialogue_ended": True, "message": "对话已结束。"}

        return self._go_to_node(next_id)

    def end_dialogue(self) -> dict[str, Any]:
        """结束当前 said 对话，重置状态。

        Returns:
            操作结果。
        """
        self._current_script = None
        self._current_node = None
        return {"success": True, "message": "已退出剧情对话模式。"}

    def get_current_node(self) -> SaidNode | None:
        """获取当前节点。"""
        return self._current_node

    def get_current_script(self) -> SaidScript | None:
        """获取当前脚本。"""
        return self._current_script

    def is_active(self) -> bool:
        """检查当前是否有活跃的 said 对话。"""
        return self._current_node is not None

    def list_scripts(self) -> list[dict[str, str]]:
        """列出所有可用 said 脚本。

        Returns:
            包含 script_id、character_name、title 的字典列表。
        """
        if not self._script_loaded:
            self.load_all_scripts()
        return [
            {
                "script_id": s.script_id,
                "character_name": s.character_name,
                "title": s.title,
            }
            for s in self._scripts.values()
        ]
