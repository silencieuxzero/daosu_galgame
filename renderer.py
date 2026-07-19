"""模块加载器与统一调度器。

renderer.py 负责统一加载各功能模块（角色、对话、好感度、记事本、互动、存档），
通过标准化接口将模块反馈整合后传递给 plugin.py，实现模块间解耦与统一调度。
"""

from __future__ import annotations

import os
from typing import Any

from .core.fsm import GameState, StateMachine
from .modules.affection import AffectionManager
from .modules.character import CharacterManager
from .modules.dialogue import DialogueManager
from .modules.interaction import InteractionManager
from .modules.notebook import NotebookManager
from .modules.save_manager import SaveManager


class VisualNovelRenderer:
    """视觉小说渲染器/协调器。

    职责：
    - 加载并初始化所有功能模块
    - 管理有限状态机，控制游戏流程
    - 提供统一的接口供 plugin.py 调用
    - 整合各模块反馈数据
    """

    def __init__(self, data_dir: str, save_dir: str) -> None:
        """
        Args:
            data_dir: 数据目录（包含 characters/ 和 events/）。
            save_dir: 存档目录。
        """
        self._data_dir = data_dir
        self._save_dir = save_dir

        # 状态机
        self._fsm = StateMachine(GameState.IDLE)

        # 模块实例化（不依赖注入顺序）
        self._character_mgr = CharacterManager(os.path.join(data_dir, "characters"))
        self._affection_mgr = AffectionManager()
        self._notebook_mgr = NotebookManager(save_dir)
        self._dialogue_mgr = DialogueManager(os.path.join(data_dir, "events"))
        self._interaction_mgr = InteractionManager(self._affection_mgr, self._notebook_mgr)
        self._save_mgr = SaveManager(save_dir)

        # 注入交叉引用
        self._affection_mgr.set_character_manager(self._character_mgr)

        # 初始化标记
        self._initialized = False

    @property
    def fsm(self) -> StateMachine:
        """获取状态机引用。"""
        return self._fsm

    @property
    def character(self) -> CharacterManager:
        return self._character_mgr

    @property
    def affection(self) -> AffectionManager:
        return self._affection_mgr

    @property
    def dialogue(self) -> DialogueManager:
        return self._dialogue_mgr

    @property
    def notebook(self) -> NotebookManager:
        return self._notebook_mgr

    @property
    def interaction(self) -> InteractionManager:
        return self._interaction_mgr

    @property
    def save_manager(self) -> SaveManager:
        return self._save_mgr

    # ==================== 生命周期 ====================

    async def initialize(self) -> None:
        """加载所有模块数据。"""
        if self._initialized:
            return

        self._character_mgr.load_all()
        self._dialogue_mgr.load_all_scripts()
        self._notebook_mgr.load()

        self._initialized = True

    async def shutdown(self) -> None:
        """卸载所有模块，清理资源。"""
        self._notebook_mgr.save()
        self._fsm.reset()
        self._initialized = False

    async def reload(self) -> None:
        """热重载所有数据。"""
        self._character_mgr.reload()
        self._dialogue_mgr.reload()
        self._initialized = True

    # ==================== 游戏流程控制 ====================

    async def start_game(self, label: str = "") -> dict[str, Any]:
        """开始新游戏。

        Args:
            label: 存档标签。

        Returns:
            启动结果。
        """
        if not self._initialized:
            await self.initialize()

        self._fsm.transition_to(GameState.MAIN_MENU)

        return {
            "success": True,
            "state": self._fsm.current_state.name,
            "characters": self._character_mgr.list_characters(),
            "message": "视觉小说已启动，进入主菜单。",
        }

    async def start_exploration(self, character_name: str) -> dict[str, Any]:
        """进入与指定角色的探索/日常对话模式。

        Args:
            character_name: 角色名称。

        Returns:
            进入结果。
        """
        if not self._fsm.can_transition_to(GameState.EXPLORATION):
            return {"success": False, "message": "当前状态下无法进入探索模式。"}

        try:
            char_data = self._character_mgr.get_character(character_name)
        except Exception as e:
            return {"success": False, "message": str(e)}

        self._fsm.transition_to(GameState.EXPLORATION)

        return {
            "success": True,
            "state": GameState.EXPLORATION.name,
            "character": character_name,
            "character_prompt": char_data.get_full_prompt(),
            "affection_level": self._affection_mgr.get_level(character_name),
            "affection_value": self._affection_mgr.get_value(character_name),
            "message": f"你开始与 {character_name} 的日常对话。",
        }

    async def start_dialogue(self, script_id: str) -> dict[str, Any]:
        """开始一个对话脚本。

        Args:
            script_id: 脚本 ID。

        Returns:
            对话起始结果。
        """
        if not self._fsm.can_transition_to(GameState.DIALOGUE):
            return {"success": False, "message": "当前状态下无法开始对话。"}

        node = self._dialogue_mgr.start_script(script_id)
        if node is None:
            return {"success": False, "message": f"对话脚本 '{script_id}' 不存在。"}

        result = self._fsm.can_transition_to(GameState.DIALOGUE)
        if result:
            self._fsm.transition_to(GameState.DIALOGUE)

        return self._format_dialogue_node(node)

    async def make_choice(self, choice_index: int) -> dict[str, Any]:
        """玩家选择选项后推进对话。

        Args:
            choice_index: 选项索引。

        Returns:
            选择结果。
        """
        current_node = self._dialogue_mgr.get_current_node()
        if current_node is None:
            return {"success": False, "message": "当前没有活跃的对话。"}

        # 检测倾诉烦恼状态，在选项中增加"静静听着"选项
        choice_text = current_node.choices[choice_index].text if choice_index < len(current_node.choices) else ""

        next_node = self._dialogue_mgr.choose(choice_index)
        if next_node is None:
            return {"success": False, "message": "无效的选项。"}

        # 记录选择
        self._save_mgr.add_choice_record({
            "node_id": current_node.node_id,
            "choice_index": choice_index,
            "choice_text": choice_text,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        })

        # 应用好感度变动
        if choice_index < len(current_node.choices):
            choice = current_node.choices[choice_index]
            if choice.affection_change != 0:
                if current_node.speaker != "narrator":
                    self._affection_mgr.modify(current_node.speaker, choice.affection_change)

        # FSM 状态转换
        if next_node.has_choices():
            self._fsm.transition_to(GameState.AWAITING_CHOICE)

        return self._format_dialogue_node(next_node)

    async def advance_dialogue(self) -> dict[str, Any]:
        """自动推进对话（无选项时）。"""
        current_node = self._dialogue_mgr.get_current_node()
        if current_node is None:
            return {"success": False, "message": "当前没有活跃的对话。"}

        if current_node.has_choices():
            self._fsm.transition_to(GameState.AWAITING_CHOICE)
            # 检测是否需要添加"静静听着"选项
            choices = self._enhance_choices_with_listen_option(current_node)
            return {
                "success": True,
                "awaiting_choice": True,
                "choices": choices,
                "message": "请做出选择。",
            }

        next_node = self._dialogue_mgr.advance()
        if next_node is None:
            # 对话结束
            char_name = current_node.speaker
            self._dialogue_mgr.end_current()
            self._fsm.transition_to(GameState.EXPLORATION)

            # 扫描线索
            clues_found = 0
            if char_name != "narrator":
                new_clues = self._notebook_mgr.scan_text_for_clues(
                    current_node.text, char_name
                )
                clues_found = len(new_clues)

            return {
                "success": True,
                "dialogue_ended": True,
                "character": char_name,
                "clues_found": clues_found,
                "message": "对话已结束。",
            }

        return self._format_dialogue_node(next_node)

    def _enhance_choices_with_listen_option(self, node: Any) -> list[dict[str, Any]]:
        """增强选项列表：检测倾诉烦恼状态时添加"静静听着"选项。

        当角色处于倾诉烦恼状态（emotion 为 sad/anxious/frustrated/venting）时，
        自动在对话选项中增加"静静听着"交互选项。
        选择该选项会触发特定角色情绪反馈与好感度调整。
        """
        choices = [
            {"index": i, "text": c.text, "option_id": c.option_id, "affection_change": c.affection_change}
            for i, c in enumerate(node.choices)
        ]

        if node.is_venting():
            # 添加"静静听着"选项
            choices.append({
                "index": len(choices),
                "text": "静静听着",
                "option_id": "listen_quietly",
                "affection_change": 5,  # 默认好感度增加
                "is_listen_option": True,
            })

        return choices

    def _format_dialogue_node(self, node: Any) -> dict[str, Any]:
        """格式化对话节点为统一字典输出。"""
        result = {
            "success": True,
            "dialogue": True,
            "speaker": node.speaker,
            "text": node.text,
            "emotion": node.emotion,
            "node_id": node.node_id,
        }

        if node.has_choices():
            choices = self._enhance_choices_with_listen_option(node)
            result["choices"] = choices
            result["awaiting_choice"] = True

        return result

    async def end_dialogue(self) -> dict[str, Any]:
        """结束当前对话，返回探索模式。"""
        self._dialogue_mgr.end_current()
        if self._fsm.can_transition_to(GameState.EXPLORATION):
            self._fsm.transition_to(GameState.EXPLORATION)
        else:
            self._fsm.transition_to(GameState.MAIN_MENU)

        return {"success": True, "state": self._fsm.current_state.name, "message": "对话已结束。"}

    # ==================== 互动操作 ====================

    async def give_gift(self, character_name: str, gift_name: str) -> dict[str, Any]:
        """赠送礼物。"""
        if self._fsm.current_state not in (GameState.EXPLORATION, GameState.GIFT_MENU):
            return {"success": False, "message": "当前状态下无法赠送礼物。"}

        result = self._interaction_mgr.give_gift(character_name, gift_name)
        self._fsm.transition_to(GameState.GIFT_MENU)
        return result

    async def invite_activity(self, character_name: str, activity_name: str) -> dict[str, Any]:
        """邀请角色参加活动。"""
        if self._fsm.current_state not in (GameState.EXPLORATION, GameState.INVITE_MENU):
            return {"success": False, "message": "当前状态下无法发起邀约。"}

        result = self._interaction_mgr.invite(character_name, activity_name)
        self._fsm.transition_to(GameState.INVITE_MENU)
        return result

    # ==================== 存档操作 ====================

    async def save_game(self, slot_id: int, label: str = "") -> dict[str, Any]:
        """保存游戏。"""
        try:
            slot = self._save_mgr.save(
                slot_id=slot_id,
                label=label,
                game_state=self._fsm.current_state.name,
                current_script=self._dialogue_mgr.get_current_script().script_id
                if self._dialogue_mgr.get_current_script()
                else None,
                current_node=self._dialogue_mgr.get_current_node().node_id
                if self._dialogue_mgr.get_current_node()
                else None,
                affection_data=self._affection_mgr.dump_state(),
                notebook_data=self._notebook_mgr.dump_state(),
                interaction_data=self._interaction_mgr.dump_state(),
            )
            return {"success": True, "slot_id": slot_id, "timestamp": slot.timestamp, "message": f"存档已保存到槽位 {slot_id}。"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def load_game(self, slot_id: int) -> dict[str, Any]:
        """加载存档。"""
        try:
            slot = self._save_mgr.load(slot_id)
        except Exception as e:
            return {"success": False, "message": str(e)}

        # 恢复各模块状态
        self._affection_mgr.load_state(slot.affection_data)
        self._notebook_mgr.load_state(slot.notebook_data)
        self._interaction_mgr.load_state(slot.interaction_data)

        return {
            "success": True,
            "slot_id": slot_id,
            "timestamp": slot.timestamp,
            "game_state": slot.game_state,
            "message": f"已从槽位 {slot_id} 加载存档。",
        }

    # ==================== 记事本 ====================

    async def show_notebook(self, character_name: str | None = None) -> dict[str, Any]:
        """显示记事本。"""
        summary = self._notebook_mgr.summarize(character_name)
        return {
            "success": True,
            "summary": summary,
            "character": character_name,
        }

    # ==================== 查询接口 ====================

    async def get_game_status(self) -> dict[str, Any]:
        """获取当前游戏状态总览。"""
        return {
            "state": self._fsm.current_state.name,
            "previous_state": self._fsm.previous_state.name if self._fsm.previous_state else None,
            "characters": self._character_mgr.list_characters(),
            "affection_states": self._affection_mgr.dump_state(),
            "in_dialogue": self._dialogue_mgr.get_current_node() is not None,
            "available_scripts": self._dialogue_mgr.list_scripts(),
            "save_slots": self._save_mgr.scan_slots(),
        }
