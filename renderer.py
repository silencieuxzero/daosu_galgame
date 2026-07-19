"""模块加载器与统一调度器。

renderer.py 负责统一加载各功能模块（角色、对话、好感度、记事本、互动、存档），
通过标准化接口将模块反馈整合后传递给 plugin.py，实现模块间解耦与统一调度。

职责：
- 加载并初始化所有功能模块
- 管理有限状态机，控制游戏流程
- 提供统一的接口供 plugin.py 调用
- 整合各模块反馈数据，返回统一格式的结果字典
"""

from __future__ import annotations

import os
from datetime import datetime
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

    作为 plugin.py 和各功能模块之间的中间层，集中管理模块 lifecycle、
    状态转换和接口编排。

    模块间依赖关系：
    - affection 依赖 character（获取性格标签）
    - interaction 依赖 affection 和 notebook
    - dialogue 独立
    - notebook 独立
    - save_manager 依赖所有模块的状态导出

    Usage:
        renderer = VisualNovelRenderer("data", "data/saves")
        await renderer.initialize()
        result = await renderer.start_game()
        result = await renderer.start_exploration("洛疏律")
    """

    def __init__(self, data_dir: str, save_dir: str, **config: Any) -> None:
        """初始化渲染器并实例化所有模块。

        Args:
            data_dir: 数据目录的绝对路径（包含 characters/ 和 events/ 子目录）。
            save_dir: 存档目录的绝对路径。
            config: 额外配置项：
                - max_save_slots: 最大存档槽位数（默认 20）。
                - tutorial_enabled: 是否启用新手引导（默认 True）。
                - tutorial_script_id: 引导脚本 ID（默认 "tutorial_intro"）。
                - affection_initial: 初始好感度值（默认 0）。
                - affection_max: 好感度上限（默认 100）。
                - affection_min: 好感度下限（默认 -100）。
        """
        self._data_dir = data_dir
        self._save_dir = save_dir

        # 提取配置
        self._tutorial_enabled: bool = config.get("tutorial_enabled", True)
        self._tutorial_script_id: str = config.get("tutorial_script_id", "tutorial_intro")
        affection_initial: int = config.get("affection_initial", 0)
        affection_max: int = config.get("affection_max", 100)
        affection_min: int = config.get("affection_min", -100)
        max_save_slots: int = config.get("max_save_slots", 20)

        # 状态机：初始为 IDLE 状态
        self._fsm = StateMachine(GameState.IDLE)

        # 模块实例化（不依赖注入顺序）
        self._character_mgr = CharacterManager(os.path.join(data_dir, "characters"))
        self._affection_mgr = AffectionManager(
            default_value=affection_initial,
            max_value=affection_max,
            min_value=affection_min,
        )
        self._notebook_mgr = NotebookManager(save_dir)
        self._dialogue_mgr = DialogueManager(os.path.join(data_dir, "events"))
        self._interaction_mgr = InteractionManager(self._affection_mgr, self._notebook_mgr)
        self._save_mgr = SaveManager(save_dir, slot_count=max_save_slots)

        # 注入交叉引用：好感度管理器需要角色管理器获取性格标签
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
        """加载所有模块数据。

        一次性加载角色数据、对话脚本和记事本存档。
        幂等操作，多次调用不会重复加载。
        """
        if self._initialized:
            return

        self._character_mgr.load_all()
        self._dialogue_mgr.load_all_scripts()
        self._notebook_mgr.load()

        self._initialized = True

    async def shutdown(self) -> None:
        """卸载所有模块，清理资源。

        保存记事本数据到磁盘，重置状态机。
        插件卸载时调用。
        """
        self._notebook_mgr.save()
        self._fsm.reset()
        self._initialized = False

    async def reload(self) -> None:
        """热重载所有数据。

        配置更新后调用，重新加载角色和对话数据。
        """
        self._character_mgr.reload()
        self._dialogue_mgr.reload()
        self._initialized = True

    # ==================== 游戏流程控制 ====================

    async def start_game(self, label: str = "") -> dict[str, Any]:
        """开始新游戏。

        首次游玩时自动进入新手引导（TUTORIAL 状态），
        非首次直接进入 MAIN_MENU。

        Args:
            label: 存档标签（暂未使用）。

        Returns:
            包含角色列表的启动结果字典。首次游玩时返回引导对话内容。
        """
        if not self._initialized:
            await self.initialize()

        # 检测首次游玩（且引导已启用）
        if self._tutorial_enabled and self._save_mgr.is_first_time():
            return await self._start_tutorial_internal()

        self._fsm.transition_to(GameState.MAIN_MENU)

        return {
            "success": True,
            "state": self._fsm.current_state.name,
            "characters": self._character_mgr.list_characters(),
            "message": "视觉小说已启动，进入主菜单。",
        }

    async def _start_tutorial_internal(self) -> dict[str, Any]:
        """内部方法：启动新手引导。

        切换到 TUTORIAL 状态并加载引导对话脚本的起始节点。
        """
        self._fsm.transition_to(GameState.TUTORIAL)

        node = self._dialogue_mgr.start_script(self._tutorial_script_id)
        if node is None:
            # 引导脚本缺失，直接进入主菜单（避免递归）
            self._fsm.transition_to(GameState.MAIN_MENU)
            return {
                "success": True,
                "state": self._fsm.current_state.name,
                "characters": self._character_mgr.list_characters(),
                "message": "视觉小说已启动，进入主菜单。",
            }

        result = self._format_dialogue_node(node)
        result["is_tutorial"] = True
        result["state"] = GameState.TUTORIAL.name
        return result

    async def start_tutorial(self) -> dict[str, Any]:
        """重新进入新手引导（从主菜单调用）。

        Returns:
            引导对话的起始节点数据，或错误信息。
        """
        if not self._fsm.can_transition_to(GameState.TUTORIAL):
            return {"success": False, "message": "当前状态下无法进入引导。"}

        return await self._start_tutorial_internal()

    async def skip_tutorial(self) -> dict[str, Any]:
        """跳过新手引导，直接进入主菜单。

        Returns:
            包含角色列表的跳过结果字典。
        """
        if self._fsm.current_state != GameState.TUTORIAL:
            return {"success": False, "message": "当前不在引导模式中。"}

        self._dialogue_mgr.end_current()
        self._fsm.transition_to(GameState.MAIN_MENU)

        return {
            "success": True,
            "state": self._fsm.current_state.name,
            "characters": self._character_mgr.list_characters(),
            "message": "引导已跳过，进入主菜单。",
        }

    async def start_exploration(self, character_name: str) -> dict[str, Any]:
        """进入与指定角色的探索/日常对话模式。

        切换到 EXPLORATION 状态，返回角色 prompt 和当前好感度。

        Args:
            character_name: 角色名称。

        Returns:
            包含角色信息和好感度的结果字典。
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

        加载指定脚本，定位到起始节点，返回第一个节点的内容。

        Args:
            script_id: 脚本 ID。

        Returns:
            对话节点数据或错误信息。
        """
        if not self._fsm.can_transition_to(GameState.DIALOGUE):
            return {"success": False, "message": "当前状态下无法开始对话。"}

        node = self._dialogue_mgr.start_script(script_id)
        if node is None:
            return {"success": False, "message": f"对话脚本 '{script_id}' 不存在。"}

        self._fsm.transition_to(GameState.DIALOGUE)

        return self._format_dialogue_node(node)

    async def make_choice(self, choice_index: int) -> dict[str, Any]:
        """玩家选择选项后推进对话。

        处理流程：
        1. 根据选项推进到下一节点
        2. 记录玩家选择到存档管理器
        3. 应用好感度变动（对话脚本中定义的 direct affection_change）
        4. 更新 FSM 状态

        Args:
            choice_index: 选项索引（从 0 开始）。

        Returns:
            选择后的对话节点或错误信息。
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
            "timestamp": datetime.now().isoformat(),
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
        elif next_node.next_node is None:
            # 选择后到达终点节点，自动结束对话
            return await self.advance_dialogue()

        return self._format_dialogue_node(next_node)

    async def advance_dialogue(self) -> dict[str, Any]:
        """自动推进对话（无选项时的线性推进）。

        如果当前节点有选项，则返回 AWAITING_CHOICE 状态等待玩家选择。
        如果对话结束，回到 EXPLORATION 状态并扫描线索。

        Returns:
            推进后的结果，包含下一节点、等待选择或对话结束标记。
        """
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

            # 引导模式结束后进入主菜单，正常模式回到探索
            if self._fsm.current_state == GameState.TUTORIAL:
                self._fsm.transition_to(GameState.MAIN_MENU)
                return {
                    "success": True,
                    "dialogue_ended": True,
                    "state": GameState.MAIN_MENU.name,
                    "characters": self._character_mgr.list_characters(),
                    "message": "新手引导完成！输入 /dsv explore <角色名> 开始你的茶馆之旅吧。",
                }
            else:
                self._fsm.transition_to(GameState.EXPLORATION)

            # 扫描当前节点的文本，提取线索
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
        """增强选项列表：检测倾诉烦恼状态时动态添加"静静听着"选项。

        当角色的 emotion 标签为 sad/anxious/frustrated/venting 时，
        表明角色处于倾诉烦恼状态，此时自动在对话选项中增加"静静听着"选项。
        选择该选项会触发特定角色情绪反馈与好感度调整。

        Args:
            node: 当前对话节点。

        Returns:
            增强后的选项列表，每个选项包含 index、text、option_id 等字段。
        """
        choices = [
            {"index": i, "text": c.text, "option_id": c.option_id, "affection_change": c.affection_change}
            for i, c in enumerate(node.choices)
        ]

        if node.is_venting():
            # 添加"静静听着"选项，好感度 +5
            choices.append({
                "index": len(choices),
                "text": "静静听着",
                "option_id": "listen_quietly",
                "affection_change": 5,
                "is_listen_option": True,
            })

        return choices

    def _format_dialogue_node(self, node: Any) -> dict[str, Any]:
        """格式化对话节点为统一的字典输出格式。

        将 DialogueNode 转换为字典，包含成功标记、对话内容、
        说话者、情绪、选项等信息。

        Args:
            node: DialogueNode 实例。

        Returns:
            统一格式的字典。
        """
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
        """结束当前对话，返回上一个模式。

        由 TUTORIAL 发起的对话跳转到 MAIN_MENU，
        由 EXPLORATION 发起的对话切回 EXPLORATION，
        否则退回 MAIN_MENU。

        Returns:
            操作结果。
        """
        self._dialogue_mgr.end_current()
        if self._fsm.current_state == GameState.TUTORIAL:
            self._fsm.transition_to(GameState.MAIN_MENU)
        elif self._fsm.can_transition_to(GameState.EXPLORATION):
            self._fsm.transition_to(GameState.EXPLORATION)
        else:
            self._fsm.transition_to(GameState.MAIN_MENU)

        return {"success": True, "state": self._fsm.current_state.name, "message": "对话已结束。"}

    # ==================== 互动操作 ====================

    async def give_gift(self, character_name: str, gift_name: str) -> dict[str, Any]:
        """赠送礼物给角色。

        委托给 InteractionManager，切换 FSM 到 GIFT_MENU 状态。

        Args:
            character_name: 目标角色。
            gift_name: 礼物名称。

        Returns:
            赠送结果字典。
        """
        if self._fsm.current_state not in (GameState.EXPLORATION, GameState.GIFT_MENU):
            return {"success": False, "message": "当前状态下无法赠送礼物。"}

        result = self._interaction_mgr.give_gift(character_name, gift_name)
        self._fsm.transition_to(GameState.GIFT_MENU)
        return result

    async def invite_activity(self, character_name: str, activity_name: str) -> dict[str, Any]:
        """邀请角色参加活动。

        委托给 InteractionManager，切换 FSM 到 INVITE_MENU 状态。

        Args:
            character_name: 目标角色。
            activity_name: 活动名称。

        Returns:
            邀请结果字典。
        """
        if self._fsm.current_state not in (GameState.EXPLORATION, GameState.INVITE_MENU):
            return {"success": False, "message": "当前状态下无法发起邀约。"}

        result = self._interaction_mgr.invite(character_name, activity_name)
        self._fsm.transition_to(GameState.INVITE_MENU)
        return result

    # ==================== 存档操作 ====================

    async def save_game(self, slot_id: int, label: str = "") -> dict[str, Any]:
        """保存游戏。

        收集好感度、记事本、互动状态数据，委托 SaveManager 持久化。

        Args:
            slot_id: 槽位编号。
            label: 存档标签。

        Returns:
            存档结果字典。
        """
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
        """加载存档。

        读取存档数据并恢复到各模块。

        Args:
            slot_id: 槽位编号。

        Returns:
            读档结果字典。
        """
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
        """显示记事本内容。

        Args:
            character_name: 可选，指定角色的线索。

        Returns:
            包含格式化摘要的结果。
        """
        summary = self._notebook_mgr.summarize(character_name)
        return {
            "success": True,
            "summary": summary,
            "character": character_name,
        }

    # ==================== 查询接口 ====================

    async def get_game_status(self) -> dict[str, Any]:
        """获取当前游戏状态总览。

        包含 FSM 状态、角色列表、各角色好感度、当前对话信息、
        可用脚本和存档槽位扫描结果。

        Returns:
            游戏状态字典。
        """
        return {
            "state": self._fsm.current_state.name,
            "previous_state": self._fsm.previous_state.name if self._fsm.previous_state else None,
            "characters": self._character_mgr.list_characters(),
            "affection_states": self._affection_mgr.dump_state(),
            "in_dialogue": self._dialogue_mgr.get_current_node() is not None,
            "available_scripts": self._dialogue_mgr.list_scripts(),
            "save_slots": self._save_mgr.scan_slots(),
        }
