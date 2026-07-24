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
import shutil
from datetime import datetime
from typing import Any

from .core.fsm import GameState, StateMachine
from .modules.affection import AffectionManager
from .modules.forward import ForwardService
from .modules.character import CharacterManager
from .modules.dialogue import DialogueManager
from .modules.plot import PlotManager
from .modules.save_manager import SaveManager
from .modules.say_chat import SayChatManager


class VisualNovelRenderer:
    """视觉小说渲染器/协调器。

    作为 plugin.py 和各功能模块之间的中间层，集中管理模块 lifecycle、
    状态转换和接口编排。

    模块间依赖关系：
    - affection 依赖 character（获取性格标签）
    - dialogue 独立
    - save_manager 依赖所有模块的状态导出

    Usage:
        renderer = VisualNovelRenderer("data", "data/saves")
        await renderer.initialize()
        result = await renderer.start_game()
    """

    def __init__(self, data_dir: str, save_dir: str,
                 forward_service: ForwardService | None = None, **config: Any) -> None:
        """初始化渲染器并实例化所有模块。

        Args:
            data_dir: 数据目录的绝对路径（包含 characters/ 和 events/ 子目录）。
            save_dir: 存档目录的绝对路径。
            forward_service: ForwardService 实例，用于合并转发/直发消息。为 None 时
                             调用方需自行处理消息发送（兼容旧模式）。
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
        self._forward_service = forward_service

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
        self._dialogue_mgr = DialogueManager(os.path.join(data_dir, "events"))
        self._plot_mgr = PlotManager(os.path.join(data_dir, "plot"), self._affection_mgr)
        self._save_mgr = SaveManager(save_dir, slot_count=max_save_slots)
        self._say_chat_mgr = SayChatManager(self._character_mgr, self._affection_mgr)

        # 注入交叉引用：好感度管理器需要角色管理器获取性格标签
        self._affection_mgr.set_character_manager(self._character_mgr)

        # 初始化标记
        self._initialized = False
        self._is_tutorial = False  # 标记当前是否处于教程模式，用于结束时正确转换状态
        self._loaded_slot = None  # 当前加载的存档槽（SaveSlot 或 None）
        self._tutorial_help_used = False  # 教程中用户是否已使用 /dsv help

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
    def plot(self) -> PlotManager:
        return self._plot_mgr

    @property
    def save_manager(self) -> SaveManager:
        return self._save_mgr

    @property
    def forward_service(self) -> ForwardService | None:
        """获取 ForwardService 实例。"""
        return self._forward_service

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
        self._plot_mgr.load_all_scripts()

        self._initialized = True

    async def shutdown(self) -> None:
        """卸载所有模块，清理资源。

        重置状态机。
        插件卸载时调用。
        """
        self._fsm.reset()
        self._initialized = False

    async def reload(self) -> None:
        """热重载所有数据。

        配置更新后调用，重新加载角色、对话和剧情脚本。
        如果当前有活跃的 chat 会话，自动结束它。
        """
        self._character_mgr.reload()
        self._dialogue_mgr.reload()
        self._plot_mgr.reload()
        if self._say_chat_mgr.is_active:
            self._say_chat_mgr.end_chat()
        self._initialized = True

    # ==================== 出厂设置 ====================

    def backup_user_data(self) -> dict[str, Any]:
        """备份所有用户数据到时间戳目录。

        将 saves/ 目录和 .progress.json 打包复制到
        data/backups/<timestamp>/ 下，便于用户在误操作后手动恢复。

        Returns:
            备份结果字典，包含备份路径和文件列表。
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = os.path.join(self._data_dir, "backups", timestamp)

        try:
            os.makedirs(backup_dir, exist_ok=True)
        except OSError as e:
            return {"success": False, "message": f"创建备份目录失败：{e}"}

        backed_up: list[str] = []

        # 备份存档目录
        if os.path.isdir(self._save_dir):
            dest_saves = os.path.join(backup_dir, "saves")
            try:
                shutil.copytree(self._save_dir, dest_saves)
                backed_up.append(f"saves/ ({os.path.basename(self._save_dir)})")
            except (OSError, shutil.Error) as e:
                return {"success": False, "message": f"备份存档目录失败：{e}"}

        # 备份剧情进度文件
        progress_path = os.path.join(self._data_dir, "plot", ".progress.json")
        if os.path.isfile(progress_path):
            dest_progress_dir = os.path.join(backup_dir, "plot")
            try:
                os.makedirs(dest_progress_dir, exist_ok=True)
                shutil.copy2(progress_path, os.path.join(dest_progress_dir, ".progress.json"))
                backed_up.append(".progress.json")
            except OSError as e:
                return {"success": False, "message": f"备份进度文件失败：{e}"}

        return {
            "success": True,
            "backup_path": backup_dir,
            "backed_up": backed_up,
            "message": f"数据已备份到 {backup_dir}",
        }

    async def factory_reset(self) -> dict[str, Any]:
        """执行出厂设置操作。

        依次执行以下步骤：
        1. 结束当前所有活跃会话（聊天、对话、剧情）
        2. 重置内存状态（好感度、剧情进度、选择历史）
        3. 清除磁盘上的存档文件
        4. 清除剧情进度文件
        5. 重置 FSM 并标记需要重新初始化

        Returns:
            操作结果字典，包含各步骤的执行状态。
        """
        cleared_items: list[str] = []
        errors: list[str] = []

        # 1. 结束所有活跃会话
        if self._say_chat_mgr.is_active:
            self._say_chat_mgr.end_chat()
        if self._dialogue_mgr.get_current_node() is not None:
            self._dialogue_mgr.end_current()
        if self._plot_mgr.is_active():
            self._plot_mgr.end_dialogue()

        # 2. 重置内存状态
        # 清空好感度数据
        self._affection_mgr._states.clear()
        cleared_items.append("好感度数据")

        # 清空剧情进度（内存）
        self._plot_mgr._completed_scripts.clear()
        cleared_items.append("剧情进度（内存）")

        # 清空选择历史
        self._save_mgr.clear_choice_history()
        cleared_items.append("选择记录")

        # 清除已加载的存档标记
        self._loaded_slot = None

        # 3. 清除磁盘上的存档文件
        if os.path.isdir(self._save_dir):
            for filename in os.listdir(self._save_dir):
                if filename.startswith("save_") and (filename.endswith(".json") or filename.endswith(".tmp")):
                    filepath = os.path.join(self._save_dir, filename)
                    try:
                        os.remove(filepath)
                    except OSError as e:
                        errors.append(f"删除存档文件失败 {filename}: {e}")
            cleared_items.append("存档文件")
            # 重新扫描槽位，更新内存缓存
            self._save_mgr.scan_slots()

        # 4. 清除剧情进度文件（磁盘）
        progress_path = os.path.join(self._data_dir, "plot", ".progress.json")
        if os.path.isfile(progress_path):
            try:
                os.remove(progress_path)
                cleared_items.append("剧情进度文件")
            except OSError as e:
                errors.append(f"删除进度文件失败: {e}")

        # 5. 重置 FSM 状态
        self._fsm.reset()

        if errors:
            return {
                "success": False,
                "cleared_items": cleared_items,
                "errors": errors,
                "message": f"部分数据清除失败：{'；'.join(errors)}",
            }

        return {
            "success": True,
            "cleared_items": cleared_items,
            "message": f"出厂设置完成。已清除：{'、'.join(cleared_items)}。",
            "state": self._fsm.current_state.name,
        }

    # ==================== 教程帮助验证 ====================

    def mark_tutorial_help_used(self) -> None:
        """标记用户已在教程中使用过 /dsv help 命令。

        由 plugin.py 在 handle_novel_help 中调用，
        用于解除 step_help_verify 节点的阻塞。
        """
        self._tutorial_help_used = True

    def is_tutorial_help_used(self) -> bool:
        """检查用户是否已在教程中使用过 /dsv help 命令。"""
        return self._tutorial_help_used

    # ==================== 游戏流程控制 ====================

    async def start_game(self) -> dict[str, Any]:
        """开始新游戏。

        首次游玩时自动进入新手引导（TUTORIAL 状态），
        非首次直接进入 MAIN_MENU。

        Returns:
            包含角色列表的启动结果字典。首次游玩时返回引导对话内容。
        """
        if not self._initialized:
            await self.initialize()

        # 开始新游戏时清除全部剧情进度
        self._plot_mgr.reset_progress()

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
        self._is_tutorial = True
        self._tutorial_help_used = False  # 重置帮助验证标记

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

    async def advance_dialogue(self) -> dict[str, Any]:
        """自动推进对话。

        支持常规对话和 plot 对话两种模式，根据当前 FSM 状态自动路由。
        plot 模式（PLOT_SCRIPT）下路由到 plot_advance。

        如果当前节点有选项，自动选择第一个选项推进。
        如果对话结束，回到 PLOT_SCRIPT 状态。

        Returns:
            推进后的结果，包含下一节点或对话结束标记。
        """
        # 剧情模式路由
        _plot_route_states = {GameState.PLOT_SCRIPT, GameState.SAVE_MENU}
        if self._fsm.current_state in _plot_route_states and self._plot_mgr.is_active():
            if self._fsm.current_state != GameState.PLOT_SCRIPT:
                self._fsm.transition_to(GameState.PLOT_SCRIPT)
            return await self.plot_advance()

        current_node = self._dialogue_mgr.get_current_node()
        if current_node is None:
            return {"success": False, "message": "当前没有活跃的对话。"}

        # 教程帮助验证：在 step_help_verify 节点阻塞，直到用户使用 /dsv help
        if self._is_tutorial and current_node.node_id == "step_help_verify" and not self._tutorial_help_used:
            return {
                "success": True,
                "dialogue": True,
                "tutorial_help_required": True,
                "speaker": current_node.speaker,
                "text": current_node.text,
                "emotion": current_node.emotion,
                "node_id": current_node.node_id,
                "message": "请先输入 /dsv help 查看完整命令列表，确认了解后再输入 /dsv next 继续。",
            }

        if current_node.has_choices():
            # 自动选择第一个选项
            return await self._auto_select_choice(current_node)

        next_node = self._dialogue_mgr.advance()
        if next_node is None:
            # 对话结束
            char_name = current_node.speaker
            self._dialogue_mgr.end_current()

            # 引导模式结束后进入主菜单，正常模式回到探索
            if self._is_tutorial:
                self._is_tutorial = False
                self._fsm.transition_to(GameState.MAIN_MENU)
                return {
                    "success": True,
                    "dialogue_ended": True,
                    "state": GameState.MAIN_MENU.name,
                    "characters": self._character_mgr.list_characters(),
                    "message": "新手引导完成！输入 /dsv plot <角色名> 开始你的茶馆之旅吧。",
                }
            else:
                self._fsm.transition_to(GameState.PLOT_SCRIPT)

            return {
                "success": True,
                "dialogue_ended": True,
                "character": char_name,
                "message": "对话已结束。",
            }

        # 新手引导：到达"选择了解的人物"步骤（step_outro）时宣告引导结束
        _tutorial_complete = self._is_tutorial and next_node.node_id == "step_outro"
        if _tutorial_complete:
            self._is_tutorial = False
            try:
                self._save_mgr.save(
                    slot_id=1,
                    label="引导完成",
                    game_state=self._fsm.current_state.name,
                    affection_data=self._affection_mgr.dump_state(),
                )
            except Exception:
                pass  # 存档失败不影响引导流程

        result = self._format_dialogue_node(next_node)
        if _tutorial_complete:
            result["tutorial_complete"] = True
        return result

    async def _auto_select_choice(self, current_node: Any) -> dict[str, Any]:
        """自动选择第一个选项推进对话。

        当对话节点有选项时，自动选择第一个选项并推进。
        处理好感度变化、选择记录、对话结束等逻辑。

        Args:
            current_node: 当前对话节点。

        Returns:
            选择后的结果。
        """
        choice_index = 0
        choice_text = current_node.choices[choice_index].text

        next_node = self._dialogue_mgr.choose(choice_index)
        if next_node is None:
            return {"success": False, "message": "无法自动选择选项。"}

        # 记录选择
        self._save_mgr.add_choice_record({
            "node_id": current_node.node_id,
            "choice_index": choice_index,
            "choice_text": choice_text,
            "timestamp": datetime.now().isoformat(),
        })

        # 应用好感度变动
        choice = current_node.choices[choice_index]
        if choice.affection_change != 0 and current_node.speaker != "narrator":
            self._affection_mgr.modify(current_node.speaker, choice.affection_change)

        # FSM 状态转换
        if next_node.has_choices():
            # 下一节点仍有选项，递归处理
            return await self._auto_select_choice(next_node)
        elif next_node.next_node is None:
            # 到达终点节点
            result: dict[str, Any] = {"success": True, "dialogue_ended": True}
            self._dialogue_mgr.end_current()

            if self._is_tutorial:
                self._fsm.transition_to(GameState.MAIN_MENU)
                speaker_label = "📖 新手引导" if next_node.speaker == "narrator" else f"💬 {next_node.speaker}"
                result["message"] = (
                    f"{speaker_label}\n{next_node.text}\n\n"
                    "新手引导完成！输入 /dsv plot <角色名> 开始你的茶馆之旅吧。"
                )
                result["characters"] = self._character_mgr.list_characters()
                self._is_tutorial = False
            else:
                self._fsm.transition_to(GameState.PLOT_SCRIPT)
                speaker_label = "📖" if next_node.speaker == "narrator" else f"💬 {next_node.speaker}"
                lines = [f"{speaker_label}\n{next_node.text}"]
                lines.append("\n对话已结束。")
                result["message"] = "\n".join(lines)

            return result

        if self._fsm.current_state != GameState.DIALOGUE:
            self._fsm.transition_to(GameState.DIALOGUE)

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

    def _enhance_plot_choices_with_listen_option(self, node: Any) -> list[dict[str, Any]]:
        """增强剧情选项列表：检测倾诉烦恼状态时动态添加"静静听着"选项。

        与 _enhance_choices_with_listen_option 逻辑相同，
        但适用于 PlotNode（plot 模块）。

        Args:
            node: PlotNode 实例。

        Returns:
            增强后的选项列表。
        """
        choices = [
            {"index": i, "text": c.text, "affection_change": c.affection_change}
            for i, c in enumerate(node.choices)
        ]

        if node.is_venting():
            choices.append({
                "index": len(choices),
                "text": "静静听着",
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
            "is_tutorial": self._is_tutorial,
        }

        if node.has_choices():
            choices = self._enhance_choices_with_listen_option(node)
            result["choices"] = choices
            result["awaiting_choice"] = True

        return result

    async def send_dialogue_display(
        self,
        stream_id: str,
        result: dict[str, Any],
    ) -> None:
        """格式化对话节点数据并通过 ForwardService 发送。

        由 plugin.py 调用，将 renderer 返回的对话节点数据格式化为用户可读文本
        并通过 ForwardService 发送（转发或直发）。

        Args:
            stream_id: 消息流 ID。
            result: renderer 返回的对话节点数据（如 advance_dialogue / make_choice 结果）。
        """
        if self._forward_service is None:
            return
        bot_name = self._forward_service.bot_name
        await self._forward_service.send_dialogue(stream_id, result, bot_name)

    async def end_dialogue(self) -> dict[str, Any]:
        """结束当前对话，返回上一个模式。

        由 TUTORIAL 发起的对话跳转到 MAIN_MENU，
        由 PLOT_SCRIPT 发起的对话切回 PLOT_SCRIPT，
        由 EXPLORATION 发起的对话切回 EXPLORATION，
        否则退回 MAIN_MENU。

        Returns:
            操作结果。
        """
        self._dialogue_mgr.end_current()
        if self._fsm.current_state == GameState.TUTORIAL:
            self._fsm.transition_to(GameState.MAIN_MENU)
        elif self._fsm.previous_state == GameState.PLOT_SCRIPT and self._fsm.can_transition_to(GameState.PLOT_SCRIPT):
            self._fsm.transition_to(GameState.PLOT_SCRIPT)
        elif self._fsm.can_transition_to(GameState.EXPLORATION):
            self._fsm.transition_to(GameState.EXPLORATION)
        else:
            self._fsm.transition_to(GameState.MAIN_MENU)

        return {"success": True, "state": self._fsm.current_state.name, "message": "对话已结束。"}

    # ==================== 存档操作 ====================

    async def save_game(self, slot_id: int, label: str = "") -> dict[str, Any]:
        """保存游戏。

        收集好感度数据，委托 SaveManager 持久化。

        Args:
            slot_id: 槽位编号。
            label: 存档标签。

        Returns:
            存档结果字典。
        """
        try:
            # 根据当前状态选择正确的管理器获取脚本/节点
            if self._fsm.current_state == GameState.PLOT_SCRIPT and self._plot_mgr.is_active():
                current_script = self._plot_mgr.get_current_script()
                current_node = self._plot_mgr.get_current_node()
            else:
                current_script = self._dialogue_mgr.get_current_script()
                current_node = self._dialogue_mgr.get_current_node()
            slot = self._save_mgr.save(
                slot_id=slot_id,
                label=label,
                game_state=self._fsm.current_state.name,
                current_script=current_script.script_id if current_script else None,
                current_node=current_node.node_id if current_node else None,
                affection_data=self._affection_mgr.dump_state(),
                completed_scripts=self._plot_mgr.dump_progress(),
            )
            return {"success": True, "slot_id": slot_id, "timestamp": slot.timestamp, "message": f"存档已保存到槽位 {slot_id}。"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def load_game(self, slot_id: int) -> dict[str, Any]:
        """加载存档。

        读取存档数据并恢复到各模块，包括 FSM 状态。

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

        # 恢复剧情进度数据
        if slot.completed_scripts:
            self._plot_mgr.restore_progress(slot.completed_scripts)

        # 恢复 FSM 状态
        try:
            target_state = GameState[slot.game_state] if slot.game_state else GameState.MAIN_MENU
            if self._fsm.current_state != target_state:
                self._fsm.transition_to(target_state)
        except Exception:
            # 状态转换不合法时，回退到主菜单
            try:
                self._fsm.transition_to(GameState.MAIN_MENU)
            except Exception:
                pass

        # 记录已加载的存档槽，供 /dsv ct 继续游戏使用
        self._loaded_slot = slot

        return {
            "success": True,
            "slot_id": slot_id,
            "timestamp": slot.timestamp,
            "game_state": slot.game_state,
            "message": f"已从槽位 {slot_id} 加载存档。",
        }

    async def continue_from_save(self) -> dict[str, Any]:
        """从已加载的存档继续游戏。

        要求先通过 load_game() 加载存档。根据存档中记录的
        script_id 和 node_id 恢复 PlotManager 状态并返回当前节点。

        Returns:
            恢复后的剧情节点数据，或错误信息。
        """
        if self._loaded_slot is None:
            return {"success": False, "message": "没有已加载的存档。请先使用 /dsv load <槽位> 加载存档。"}

        slot = self._loaded_slot

        if not slot.current_script or not slot.current_node:
            return {"success": False, "message": "该存档不包含剧情进度数据，无法继续游戏。请使用 /dsv plot <角色名> 开始新剧情。"}

        # 切换到 PLOT_SCRIPT 状态
        if self._fsm.current_state != GameState.PLOT_SCRIPT:
            try:
                self._fsm.transition_to(GameState.PLOT_SCRIPT)
            except Exception:
                return {"success": False, "message": f"无法从当前状态（{self._fsm.current_state.name}）切换到游戏模式。"}

        # 结束当前活跃的剧情对话
        if self._plot_mgr.is_active():
            self._plot_mgr.end_dialogue()

        # 恢复到存档记录的脚本和节点
        result = self._plot_mgr.resume_script(slot.current_script, slot.current_node)
        if result.get("success"):
            result["state"] = GameState.PLOT_SCRIPT.name
            # 附加好感度信息
            script = self._plot_mgr.get_current_script()
            if script:
                affection_value = self._affection_mgr.get_value(script.character_name)
                affection_level = self._affection_mgr.get_level(script.character_name)
                result["affection_value"] = affection_value
                result["affection_level"] = affection_level

        return result

    # ==================== 分段式剧情对话（/dsv plot） ====================

    async def start_plot(self, character_name: str) -> dict[str, Any]:
        """启动与指定角色的分段式剧情对话。

        验证角色存在且有所属的剧情脚本，切换到 PLOT_SCRIPT 状态，
        返回第一个剧情节点。

        Args:
            character_name: 角色名称。

        Returns:
            首个剧情节点数据，或错误信息。
        """
        if not self._initialized:
            await self.initialize()

        # 验证角色是否存在
        try:
            self._character_mgr.get_character(character_name)
        except Exception as e:
            return {"success": False, "message": str(e)}

        # 检查是否有剧情脚本
        script = self._plot_mgr.get_script_for_character(character_name)
        if script is None:
            return {"success": False, "message": f"角色 '{character_name}' 暂无可用的剧情对话。"}

        # 如果有进行中的对话，先结束
        if self._plot_mgr.is_active():
            self._plot_mgr.end_dialogue()

        # 启动新剧情时清除已加载的存档标记
        self._loaded_slot = None

        # 切换状态
        if self._fsm.current_state != GameState.PLOT_SCRIPT:
            self._fsm.transition_to(GameState.PLOT_SCRIPT)

        # 启动脚本
        result = self._plot_mgr.start_script_for_character(character_name)
        if result.get("success"):
            result["state"] = GameState.PLOT_SCRIPT.name
            result["title"] = script.title
            # 附加好感度信息
            affection_value = self._affection_mgr.get_value(character_name)
            affection_level = self._affection_mgr.get_level(character_name)
            result["affection_value"] = affection_value
            result["affection_level"] = affection_level

        return result

    async def plot_advance(self) -> dict[str, Any]:
        """推进剧情对话。

        当遇到有选项的节点时，展示当前节点文本和选项列表，
        等待玩家使用 /dsv choose <编号> 选择选项。

        如果当前章节结束且有后续章节，设置 pending_next 状态
        并返回过渡提示，等待玩家输入 /dsv next 确认继续。

        Returns:
            下一节点数据或结束标记。
        """
        if self._plot_mgr.has_pending_next():
            # 优先检查待确认的下一章节（此时 is_active 因 pending 返回 True）
            return await self._confirm_and_start_next()

        if not self._plot_mgr.is_active():
            return {"success": False, "message": "当前没有活跃的剧情对话。"}

        result = self._plot_mgr.advance()
        if not result.get("success"):
            return result

        # 有选项的节点：增强选项列表（含"静静听着"），等待玩家选择
        if result.get("awaiting_choice"):
            current_node = self._plot_mgr.get_current_node()
            if current_node and current_node.has_choices():
                choices = self._enhance_plot_choices_with_listen_option(current_node)
                result["choices"] = choices
            return result

        if result.get("dialogue_ended"):
            return self._handle_chapter_end(result)

        return result

    def _handle_chapter_end(self, result: dict[str, Any]) -> dict[str, Any]:
        """处理章节结束逻辑。

        标记当前脚本为已完成。如果该角色还有后续章节，
        设置 pending_next 状态并返回过渡提示；
        否则正常结束对话。

        Args:
            result: 当前节点结果字典。

        Returns:
            处理后的结果字典。
        """
        completed_info = self._plot_mgr.mark_current_completed()
        result["script_completed"] = True
        character = completed_info.get("character_name", "") if completed_info.get("success") else ""

        # 结束当前对话状态（使 is_active 恢复 False，下轮 /dsv next 走 pending 路由）
        self._plot_mgr.end_dialogue()

        if character and self._plot_mgr.has_more_scripts(character):
            # 还有后续章节：设置 pending 状态
            self._plot_mgr.set_pending_next_character(character)
            result["waiting_next_confirm"] = True
            next_script = self._plot_mgr.get_next_script_for_character(character)
            if next_script:
                result["next_script_title"] = next_script.title
                result["next_script_id"] = next_script.script_id
            return result

        # 没有更多章节
        if self._fsm.current_state != GameState.PLOT_SCRIPT:
            self._fsm.transition_to(GameState.PLOT_SCRIPT)
        return result

    async def _confirm_and_start_next(self) -> dict[str, Any]:
        """玩家确认继续后启动下一章节。

        获取待确认的角色名，结束当前（已完结的）对话状态，
        启动该角色的下一章节脚本。

        Returns:
            下一章节的起始节点数据。
        """
        character = self._plot_mgr.get_pending_next_character()
        if not character:
            return {"success": False, "message": "没有待确认的下一章节。"}

        # 结束当前已完结的对话状态
        self._plot_mgr.end_dialogue()

        # 启动下一章节
        result = self._plot_mgr.start_next_script(character)
        if not result.get("success"):
            return result

        # 确保状态机处于 PLOT_SCRIPT
        if self._fsm.current_state != GameState.PLOT_SCRIPT:
            self._fsm.transition_to(GameState.PLOT_SCRIPT)

        result["state"] = GameState.PLOT_SCRIPT.name
        script = self._plot_mgr.get_current_script()
        if script:
            result["title"] = script.title

        # 附加好感度信息
        affection_value = self._affection_mgr.get_value(character)
        affection_level = self._affection_mgr.get_level(character)
        result["affection_value"] = affection_value
        result["affection_level"] = affection_level

        return result

    async def plot_end(self) -> dict[str, Any]:
        """结束当前剧情对话，返回主菜单。

        Returns:
            操作结果。
        """
        if not self._plot_mgr.is_active():
            return {"success": False, "message": "当前没有活跃的剧情对话。"}

        self._plot_mgr.end_dialogue()
        if self._fsm.current_state == GameState.PLOT_SCRIPT:
            self._fsm.transition_to(GameState.MAIN_MENU)

        return {"success": True, "message": "已退出游戏模式，返回主菜单。可输入 /dsv plot <角色名> 重新开始。"}

    async def plot_make_choice(self, choice_index: int) -> dict[str, Any]:
        """在剧情模式（PLOT_SCRIPT）中处理玩家选项选择。

        验证当前处于剧情模式且节点有选项。处理普通选项和"静静听着"
        特殊选项，应用好感度变化并记录选择历史。

        Args:
            choice_index: 选项索引（0-based）。

        Returns:
            选择后的结果，包含下一节点或错误信息。
        """
        # 仅剧情模式可用
        if self._fsm.current_state != GameState.PLOT_SCRIPT:
            return {"success": False, "message": "选项选择仅在剧情模式中可用。"}

        if not self._plot_mgr.is_active():
            return {"success": False, "message": "当前没有活跃的剧情对话。"}

        current_node = self._plot_mgr.get_current_node()
        if current_node is None or not current_node.has_choices():
            return {"success": False, "message": "当前节点没有选项可供选择。"}

        # 构建增强选项列表（含"静静听着"）
        enhanced_choices = self._enhance_plot_choices_with_listen_option(current_node)

        if choice_index < 0 or choice_index >= len(enhanced_choices):
            return {"success": False, "message": f"无效的选项编号。请输入 1-{len(enhanced_choices)}。"}

        chosen = enhanced_choices[choice_index]
        chosen_text = chosen["text"]

        # 处理"静静听着"特殊选项（虚拟选项，不映射到 PlotChoice）
        if chosen.get("is_listen_option"):
            character_name = ""
            script = self._plot_mgr.get_current_script()
            if script:
                character_name = script.character_name

            # 应用好感度变化
            if character_name:
                self._affection_mgr.modify(character_name, chosen["affection_change"])

            # 记录选择
            self._save_mgr.add_choice_record({
                "node_id": current_node.node_id,
                "choice_index": choice_index,
                "choice_text": chosen_text,
                "is_listen_option": True,
                "timestamp": datetime.now().isoformat(),
            })

            # 跳转到下一节点
            if current_node.next_node:
                # _go_to_node 是私有方法但 Python 允许访问
                result = self._plot_mgr._go_to_node(current_node.next_node)
            else:
                self._plot_mgr.end_dialogue()
                self._fsm.transition_to(GameState.PLOT_SCRIPT)
                result = {
                    "success": True,
                    "plot_dialogue": True,
                    "dialogue_ended": True,
                    "message": "对话已结束。",
                }
        else:
            # 普通选项：交由 PlotManager 处理
            result = self._plot_mgr.make_choice(choice_index)
            if not result.get("success"):
                return result

            # 记录选择
            self._save_mgr.add_choice_record({
                "node_id": current_node.node_id,
                "choice_index": choice_index,
                "choice_text": chosen_text,
                "timestamp": datetime.now().isoformat(),
            })

        # 从 plot_mgr.make_choice 的返回值中提取好感度信息
        affection_change = result.get("affection_change", 0)
        if affection_change != 0:
            char_name = result.get("character_name", "")
            if char_name:
                result["affection_value"] = self._affection_mgr.get_value(char_name)
                result["affection_level"] = self._affection_mgr.get_level(char_name)

        # 如果对话结束（章节末尾节点），处理章节过渡逻辑
        if result.get("dialogue_ended") and not result.get("waiting_next_confirm"):
            result = self._handle_chapter_end(result)

        return result

    # ==================== 自由聊天模式（/dsv chat） ====================

    @property
    def chat(self) -> SayChatManager:
        """获取自由聊天管理器。"""
        return self._say_chat_mgr

    async def start_chat(self, character_name: str, model: str = "replyer") -> dict[str, Any]:
        """进入与指定角色的自由聊天模式。

        切换到 CHAT 状态，加载角色 prompt 并返回启动结果。

        Args:
            character_name: 角色名称。
            model: LLM 模型名称，默认 "replyer"。

        Returns:
            启动结果，包含聊天模式信息和角色 prompt 摘要。
        """
        if not self._fsm.can_transition_to(GameState.CHAT):
            return {"success": False, "message": "当前状态下无法进入聊天模式。"}

        result = self._say_chat_mgr.start_chat(character_name, model)
        if not result.get("success"):
            return result

        self._fsm.transition_to(GameState.CHAT)
        return {
            "success": True,
            "state": GameState.CHAT.name,
            "character_name": character_name,
            "model": model,
            "message": f"已进入与 {character_name} 的自由聊天模式（模型：{model}）。\n"
                       f"发送任意消息与角色对话，输入 /dsv chat_exit 退出。",
        }

    async def end_chat(self) -> dict[str, Any]:
        """退出自由聊天模式，回到游戏模式。

        Returns:
            操作结果。
        """
        if not self._say_chat_mgr.is_active:
            return {"success": False, "message": "当前没有活跃的聊天会话。"}

        character_name = self._say_chat_mgr.character_name
        self._say_chat_mgr.end_chat()

        if self._fsm.current_state == GameState.CHAT:
            if self._fsm.can_transition_to(GameState.PLOT_SCRIPT):
                self._fsm.transition_to(GameState.PLOT_SCRIPT)
            elif self._fsm.can_transition_to(GameState.EXPLORATION):
                self._fsm.transition_to(GameState.EXPLORATION)
            else:
                self._fsm.transition_to(GameState.MAIN_MENU)

        return {
            "success": True,
            "character_name": character_name,
            "message": f"已退出与 {character_name} 的自由聊天模式。",
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
            "in_plot_dialogue": self._plot_mgr.is_active(),
            "plot_character": self._plot_mgr.get_current_script().character_name
                if self._plot_mgr.get_current_script() else None,
            "plot_title": self._plot_mgr.get_current_script().title
                if self._plot_mgr.get_current_script() else None,
            "in_chat": self._say_chat_mgr.is_active,
            "chat_character": self._say_chat_mgr.character_name if self._say_chat_mgr.is_active else None,
            "chat_model": self._say_chat_mgr.model_name if self._say_chat_mgr.is_active else None,
            "available_scripts": self._dialogue_mgr.list_scripts(),
            "save_slots": self._save_mgr.scan_slots(),
        }
