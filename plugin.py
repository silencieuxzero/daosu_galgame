"""视觉小说插件 — 入口与协调层。

plugin.py 仅作为插件入口与核心协调层，负责：
- 模块注册与生命周期管理
- 对外暴露 Command / Tool / EventHandler 接口
- 将请求委托给 renderer.py 处理
具体业务逻辑下沉至各功能模块。

架构约定：
- plugin.py 不直接调用各功能模块，而是通过 renderer.py 统一调度
- 所有命令的处理逻辑保持精简，只做参数校验和结果展示
- 配置模型集中定义于 config.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from maibot_sdk import Command, HookHandler, MaiBotPlugin, Tool
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder, ToolParameterInfo, ToolParamType

from .config import VisualNovelPluginConfig
from .modules.forward import ForwardService
from .renderer import VisualNovelRenderer


# ==================== 插件主类 ====================


class VisualNovelPlugin(MaiBotPlugin):
    """视觉小说插件主类。

    职责限定：
    - 管理插件生命周期（on_load / on_unload / on_config_update）
    - 注册 Command/Tool/EventHandler 到 MaiBot 平台
    - 对请求做参数校验后委托给 renderer
    - 格式化 renderer 返回的结果并发送给用户

    Attributes:
        config_model: 绑定的配置模型类。
        _renderer: VisualNovelRenderer 实例，具体业务入口。
    """

    config_model = VisualNovelPluginConfig

    def __init__(self) -> None:
        super().__init__()
        self._renderer: VisualNovelRenderer | None = None

    # ==================== 生命周期 ====================

    async def on_load(self) -> None:
        """插件加载时初始化渲染器。

        解析配置中的路径（支持相对路径），创建目录结构，
        实例化 VisualNovelRenderer 并传入各段配置。
        """
        # 解析数据目录（支持相对路径）
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        data_dir = self._resolve_path(project_root, self.config.data.data_dir)
        save_dir = self._resolve_path(project_root, self.config.data.save_dir)

        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(save_dir, exist_ok=True)

        # 初始化合并转发服务
        forward_service = ForwardService(
            send_text=self.ctx.send.text,
            send_forward=self.ctx.send.forward,
            enabled=self.config.forward.enabled,
            bot_name=self.config.forward.bot_name,
        )

        self._renderer = VisualNovelRenderer(
            data_dir,
            save_dir,
            forward_service=forward_service,
            tutorial_enabled=self.config.tutorial.enabled,
            tutorial_script_id=self.config.tutorial.script_id,
            affection_initial=self.config.affection.initial_value,
            affection_max=self.config.affection.max_value,
            affection_min=self.config.affection.min_value,
            max_save_slots=self.config.save.max_slots,
        )
        await self._renderer.initialize()

    async def on_unload(self) -> None:
        """插件卸载时清理资源。

        调用 renderer 的 shutdown 方法，保存记事本数据并重置状态机。
        """
        if self._renderer:
            await self._renderer.shutdown()
            self._renderer = None

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        """配置热更新。

        当用户在管理后台修改配置时触发，重新加载数据。

        Args:
            scope: 配置变更的作用域。
            config_data: 变更后的配置数据。
            version: 新的配置版本号。
        """
        del scope, config_data, version
        if self._renderer:
            await self._renderer.reload()

    # ==================== 跳过 Planner ====================

    @HookHandler(
        "chat.receive.before_process",
        name="dsv_chat_handler",
        description="拦截自由聊天模式下的非命令消息，路由至 LLM 对话处理器",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.LOG,
    )
    async def handle_chat_message(self, **kwargs: Any) -> dict[str, Any]:
        """在消息处理前检查用户是否处于自由聊天模式。

        如果用户当前处于 CHAT 状态，将非命令消息路由到 LLM 生成角色回复，
        并阻止消息进入 MaiBot 的 Planner/LLM 处理链。

        Args:
            kwargs: 包含消息内容、stream_id 等。

        Returns:
            abort 阻止消息进入 Planner；非聊天模式返回 continue 放行。
        """
        message = kwargs.get("message", {})
        if not message:
            return {"action": "continue"}

        raw_text = str(message.get("raw_message", "") or "")
        if not raw_text or raw_text.startswith("/dsv"):
            return {"action": "continue"}

        stream_id = str(kwargs.get("stream_id", "") or message.get("stream_id", ""))
        if not stream_id:
            return {"action": "continue"}

        if self._renderer is None:
            return {"action": "continue"}

        # 检查是否处于自由聊天模式
        if not self._renderer.chat.is_active:
            return {"action": "continue"}

        character_name = self._renderer.chat.character_name
        chat_model = self._renderer.chat.model_name
        self.ctx.logger.info(
            "自由聊天: 拦截玩家 %s 的输入 → LLM 角色(%s) 回复", stream_id, character_name
        )

        # 异步调用 LLM，不阻塞主流程
        asyncio.ensure_future(
            self._do_chat_reply(stream_id, raw_text.strip(), chat_model)
        )
        return {"action": "abort"}

    def _resolve_path(self, project_root: str, configured_path: str) -> str:
        """解析配置中的路径。

        相对路径基于项目根目录拼接，绝对路径原样保留。

        Args:
            project_root: 项目根目录绝对路径。
            configured_path: 配置中填写的路径。

        Returns:
            解析后的绝对路径。
        """
        if os.path.isabs(configured_path):
            return configured_path
        return os.path.join(project_root, configured_path)

    # ==================== 自由聊天 LLM 处理 ====================

    def _get_chat_model(self) -> str:
        """获取聊天使用的 LLM 模型名称。

        从 config.toml [chat].default_model 读取模型配置。

        Returns:
            模型名称，默认 "replyer"。
        """
        config_model = getattr(self.config.chat, "default_model", "").strip()
        return config_model or "replyer"

    async def _do_chat_reply(
        self, stream_id: str, user_input: str, model: str
    ) -> None:
        """在自由聊天模式中调用 LLM 生成角色回复并发送。

        使用 SayChatManager 维护的对话历史 + 用户输入调用 LLM，
        将生成的回复发送给用户。如果 LLM 调用失败，发送错误提示。

        Args:
            stream_id: 消息流 ID。
            user_input: 用户输入的文本。
            model: LLM 模型名称。
        """
        if self._renderer is None:
            return

        mgr = self._renderer.chat
        if not mgr.is_active:
            return

        character_name = mgr.character_name
        llm_generate = self.ctx.llm.generate
        result = await mgr.generate_reply(llm_generate, user_input)
        if result.get("success"):
            reply = result["reply"]
            await self.ctx.send.text(
                f"💬 {character_name}\n{reply}\n\n"
                f"（输入 /dsv chat_exit 退出聊天）",
                stream_id,
            )
        else:
            await self.ctx.send.text(
                f"⚠️ 回复生成失败：{result.get('message', '未知错误')}\n"
                f"可输入 /dsv chat_exit 退出聊天模式。",
                stream_id,
            )

    # ==================== Command 命令 ====================

    @Command(
        "dsv_start",
        description="启动视觉小说",
        pattern=r"^/dsv start$",
        intercept_message_level=1,
    )
    async def handle_novel_start(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """启动视觉小说游戏。

        首次游玩时自动进入新手引导，否则直接进入主菜单。

        Returns:
            Command 标准返回值，包含启动结果文本。
        """
        del kwargs
        if self._renderer is None:
            await self.ctx.send.text("插件未正确加载。", stream_id)
            return False, "插件未正确加载。", True

        result = await self._renderer.start_game()

        if result.get("is_tutorial"):
            await self._renderer.send_dialogue_display(stream_id, result)
            return True, "进入新手引导", True

        # 非首次/非引导：直接发送
        await self.ctx.send.text(
            f"📖 视觉小说已启动！\n"
            f"可用角色：{'、'.join(result.get('characters', []))}\n\n"
            f"输入 /dsv plot <角色名> 进入故事模式\n"
            f"输入 /dsv status 查看游戏状态",
            stream_id,
        )
        return True, "视觉小说已启动", True

    @Command(
        "dsv_status",
        description="查看当前游戏状态",
        pattern=r"^/dsv status$",
        intercept_message_level=1,
    )
    async def handle_novel_status(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """查看游戏运行状态。

        显示 FSM 状态、角色列表及各角色好感度。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            return False, "插件未正确加载。", True

        status = await self._renderer.get_game_status()
        lines = [
            f"📊 游戏状态",
            f"当前状态：{status['state']}",
            f"角色：{'、'.join(status['characters'])}",
        ]

        # 如果在 plot 对话模式中，显示当前角色
        if status.get("in_plot_dialogue"):
            plot_char = status.get("plot_character", "")
            plot_title = status.get("plot_title", "")
            lines.append(f"剧情对话：{plot_char} - {plot_title}")

        # 如果在自由聊天模式中，显示当前角色
        if status.get("in_chat"):
            chat_char = status.get("chat_character", "")
            chat_model = status.get("chat_model", "")
            lines.append(f"自由聊天：与 {chat_char}（模型：{chat_model}）")

        for name, state_data in status.get("affection_states", {}).items():
            lines.append(f"  {name}：好感度 {state_data['value']}（{state_data['level']}）")

        await self.ctx.send.text("\n".join(lines), stream_id)
        return True, "已显示游戏状态", True

    @Command(
        "dsv_save",
        description="保存游戏进度",
        pattern=r"^/dsv save\s+(?P<slot>\d+)\s*(?P<label>.*)$",
        intercept_message_level=1,
    )
    async def handle_novel_save(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """保存游戏到指定槽位。

        保存内容包括好感度、选择历史等。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 slot 和 label 参数。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        slot_id = int(matched_groups.get("slot", 0))
        label = str(matched_groups.get("label", "")).strip()

        max_slots = self.config.save.max_slots
        if slot_id < 1 or slot_id > max_slots:
            return False, f"槽位编号范围为 1-{max_slots}。", True

        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.save_game(slot_id, label)
        if not result.get("success"):
            return False, result.get("message", "保存失败。"), True

        await self.ctx.send.text(result["message"], stream_id)
        return True, result["message"], True

    @Command(
        "dsv_load",
        description="读取游戏存档",
        pattern=r"^/dsv load\s+(?P<slot>\d+)$",
        intercept_message_level=1,
    )
    async def handle_novel_load(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """读取指定槽位的存档。

        恢复好感度等全部数据。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 slot 参数。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        slot_id = int(matched_groups.get("slot", 0))

        if self._renderer is None:
            await self.ctx.send.text("插件未正确加载。", stream_id)
            return False, "插件未正确加载。", True

        result = await self._renderer.load_game(slot_id)
        if not result.get("success"):
            msg = result.get("message", "读档失败。")
            await self.ctx.send.text(msg, stream_id)
            return False, msg, True

        await self.ctx.send.text(result["message"], stream_id)
        return True, result["message"], True

    @Command(
        "dsv_ct",
        description="从已加载的存档继续游戏",
        pattern=r"^/dsv ct$",
        intercept_message_level=1,
    )
    async def handle_continue(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """从已加载的存档继续游戏。

        必须先使用 /dsv load <槽位> 加载存档。根据存档中记录的
        脚本和节点位置恢复到游戏进程。

        Args:
            stream_id: 消息流 ID。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            await self.ctx.send.text("插件未正确加载。", stream_id)
            return False, "插件未正确加载。", True

        result = await self._renderer.continue_from_save()
        if not result.get("success"):
            msg = result.get("message", "继续游戏失败。")
            await self.ctx.send.text(msg, stream_id)
            return False, msg, True

        # 构建显示文本（与 handle_plot_start 保持一致）
        lines = [f"📖 {result.get('title', '剧情对话')}\n"]
        speaker = result.get("speaker", "narrator")
        if speaker == "narrator":
            lines.append(f"{result['text']}")
        else:
            lines.append(f"💬 {speaker}\n{result['text']}")

        # 好感度信息
        affection_value = result.get("affection_value", 0)
        affection_level = result.get("affection_level", "普通")
        lines.append(f"\n好感度：{affection_value}（{affection_level}）")

        lines.append("\n—— 输入 /dsv next 继续 ——")
        lines.append("\n可随时使用以下指令进行探索互动：")
        lines.append("  /dsv chat <角色名> / /dsv save <槽位>")
        lines.append("\n输入 /dsv plot_exit 可退出游戏模式返回主菜单。")

        content = "\n".join(lines)
        fwd = self._renderer.forward_service
        if fwd:
            await fwd.send(stream_id, content)
        else:
            await self.ctx.send.text(content, stream_id)
        return True, "已从存档继续游戏", True

    @Command(
        "dsv_help",
        description="查看视觉小说插件帮助信息",
        pattern=r"^/dsv help$",
        intercept_message_level=1,
    )
    async def handle_novel_help(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """显示帮助信息，列出所有可用命令及其用法。

        Args:
            stream_id: 消息流 ID。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        help_text = (
            "📖 视觉小说插件帮助\n\n"
            "可用命令：\n"
            "  /dsv start — 启动游戏（首次自动进入引导）\n"
            "  /dsv tutorial — 重新查看新手引导\n"
            "  /dsv plot <角色名> — 开始剧情章节\n"
            "  /dsv plot_exit — 退出游戏模式，返回主菜单\n"
            "  /dsv chat <角色名> — 与角色进行自由聊天（LLM 驱动）\n"
            "  /dsv chat_exit — 退出自由聊天模式\n"
            "  /dsv next — 推进对话到下一节点；章节结束时输入确认继续下一章\n"
            "  /dsv choose <编号> — 在剧情对话中选择选项分支\n"
            "  /dsv status — 查看游戏状态\n"
            "  /dsv save <槽位1-20> [标签] — 存档\n"
            "  /dsv load <槽位1-20> — 读档\n"
            "  /dsv ct — 从已加载的存档继续游戏\n"
            "  /dsv skip tutorial — 跳过引导\n"
            "  /dsv factory_reset — 重置插件至出厂设置\n"
            "  /dsv help — 显示此帮助"
        )
        await self.ctx.send.text(help_text, stream_id)

        # 如果正在教程中，标记用户已使用 /dsv help（解除 step_help_verify 阻塞）
        if self._renderer is not None:
            self._renderer.mark_tutorial_help_used()

        return True, "已显示帮助信息", True

    # ==================== /dsv plot 命令 ====================

    @Command(
        "dsv_plot",
        description="与指定角色进行分段式剧情对话",
        pattern=r"^/dsv plot\s+(?P<character>.+)$",
        intercept_message_level=1,
    )
    async def handle_plot_start(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """启动与指定角色的分段式剧情对话模式。

        自动加载角色对应剧情脚本并展示第一个剧情节点。
        若有选项分支，显示选项列表供用户选择。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 matched_groups 中的 character 参数。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        character_name = str(matched_groups.get("character", "")).strip()

        if not character_name:
            await self.ctx.send.text("请指定角色名。用法：/dsv plot <角色名>", stream_id)
            return False, "请指定角色名。用法：/dsv plot <角色名>", True

        if self._renderer is None:
            await self.ctx.send.text("插件未正确加载。", stream_id)
            return False, "插件未正确加载。", True

        result = await self._renderer.start_plot(character_name)
        if not result.get("success"):
            msg = result.get("message", "启动剧情对话失败。")
            await self.ctx.send.text(msg, stream_id)
            return False, msg, True

        # 构建显示文本
        lines = [f"📖 {result.get('title', '剧情对话')}\n"]
        speaker = result.get("speaker", "narrator")
        if speaker == "narrator":
            lines.append(f"{result['text']}")
        else:
            lines.append(f"💬 {speaker}\n{result['text']}")

        # 好感度信息
        affection_value = result.get("affection_value", 0)
        affection_level = result.get("affection_level", "普通")
        lines.append(f"\n好感度：{affection_value}（{affection_level}）")

        lines.append("\n—— 输入 /dsv next 继续 ——")
        lines.append("\n可随时使用以下指令进行探索互动：")
        lines.append("  /dsv chat <角色名> / /dsv save <槽位>")
        lines.append("\n输入 /dsv plot_exit 可退出游戏模式返回主菜单。")

        content = "\n".join(lines)
        fwd = self._renderer.forward_service
        if fwd:
            await fwd.send(stream_id, content)
        else:
            await self.ctx.send.text(content, stream_id)
        return True, "剧情对话已启动", True

    @Command(
        "dsv_plot_exit",
        description="退出当前剧情对话模式",
        pattern=r"^/dsv plot_exit$",
        intercept_message_level=1,
    )
    async def handle_plot_exit(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """退出当前的游戏模式，返回主菜单。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            await self.ctx.send.text("插件未正确加载。", stream_id)
            return False, "插件未正确加载。", True

        result = await self._renderer.plot_end()
        if not result.get("success"):
            msg = result.get("message", "退出失败。")
            await self.ctx.send.text(msg, stream_id)
            return False, msg, True

        await self.ctx.send.text(result["message"], stream_id)
        return True, result["message"], True

    # ==================== /dsv choose 命令 ====================

    @Command(
        "dsv_choose",
        description="在剧情对话中选择选项分支",
        pattern=r"^/dsv choose\s+(?P<index>\d+)$",
        intercept_message_level=1,
    )
    async def handle_plot_choose(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """在剧情对话中选择选项分支。

        仅在剧情模式（PLOT_SCRIPT）中可用，新手引导和自由探索对话中不可使用。
        选项编号从 1 开始。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 matched_groups 中的 index 参数。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        try:
            choice_index = int(matched_groups.get("index", 0))
        except (ValueError, TypeError):
            await self.ctx.send.text("无效的选项编号。用法：/dsv choose <编号>", stream_id)
            return False, "无效的选项编号。用法：/dsv choose <编号>", True

        if choice_index < 1:
            await self.ctx.send.text("选项编号必须大于 0。用法：/dsv choose <编号>", stream_id)
            return False, "选项编号必须大于 0。用法：/dsv choose <编号>", True

        if self._renderer is None:
            await self.ctx.send.text("插件未正确加载。", stream_id)
            return False, "插件未正确加载。", True

        # 仅在剧情模式可用
        if self._renderer.fsm.current_state.name != "PLOT_SCRIPT":
            await self.ctx.send.text("选项选择仅在剧情模式中可用。请先使用 /dsv plot <角色名> 进入剧情。", stream_id)
            return False, "选项选择仅在剧情模式中可用。请先使用 /dsv plot <角色名> 进入剧情。", True

        # 转为 0-based 索引
        result = await self._renderer.plot_make_choice(choice_index - 1)

        if not result.get("success"):
            msg = result.get("message", "选择失败。")
            await self.ctx.send.text(msg, stream_id)
            return False, msg, True

        if result.get("dialogue_ended"):
            if result.get("waiting_next_confirm"):
                # 章节结束，等待玩家确认是否继续下一章
                next_title = result.get("next_script_title", "下一章")
                msg = (
                    f"📖 本章剧情已完成！\n\n"
                    f"下一章节《{next_title}》已就绪。\n"
                    f"输入 /dsv next 继续剧情……"
                )
                await self.ctx.send.text(msg, stream_id)
                return True, "章节结束，等待继续", True

            # 所有剧情已完成
            script_completed = result.get("script_completed", False)
            if script_completed:
                msg = result.get("message", "剧情章节已完成。")
                msg += "\n\n该角色的所有剧情已全部完成。"
                await self.ctx.send.text(msg, stream_id)
            else:
                await self.ctx.send.text(result.get("message", "对话已结束。"), stream_id)
            return True, "对话结束", True

        # 显示下一节点
        await self._renderer.send_dialogue_display(stream_id, result)
        return True, "已选择选项", True

    # ==================== /dsv chat 命令 ====================

    @Command(
        "dsv_chat",
        description="与指定角色进行自由聊天（LLM 驱动）",
        pattern=r"^/dsv chat\s+(?P<character>.+)$",
        intercept_message_level=1,
    )
    async def handle_chat_start(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """启动与指定角色的自由聊天模式。

        角色 prompt 自动从 data/characters 加载，LLM 模型由 config.toml 配置。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 matched_groups 中的 character 参数。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        character_name = str(matched_groups.get("character", "")).strip()

        if not character_name:
            return False, "请指定角色名。用法：/dsv chat <角色名>", True

        if self._renderer is None:
            return False, "插件未正确加载。", True

        model = self._get_chat_model()

        result = await self._renderer.start_chat(character_name, model)
        if not result.get("success"):
            return False, result.get("message", "启动聊天失败。"), True

        await self.ctx.send.text(
            f"💬 已进入与 {character_name} 的自由聊天模式。\n"
            f"模型：{model}\n"
            f"发送任意消息与角色对话，输入 /dsv chat_exit 退出。",
            stream_id,
        )

        # 异步生成开场白
        asyncio.ensure_future(
            self._do_chat_reply(stream_id, "", model)
        )
        return True, f"开始与 {character_name} 自由聊天", True

    @Command(
        "dsv_chat_exit",
        description="退出当前自由聊天模式",
        pattern=r"^/dsv chat_exit$",
        intercept_message_level=1,
    )
    async def handle_chat_exit(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """退出当前的自由聊天模式。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.end_chat()
        if not result.get("success"):
            return False, result.get("message", "退出聊天失败。"), True

        await self.ctx.send.text(result["message"], stream_id)
        return True, result["message"], True

    @Command(
        "dsv_tutorial",
        description="重新进入新手引导",
        pattern=r"^/dsv tutorial$",
        intercept_message_level=1,
    )
    async def handle_novel_tutorial(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """重新进入新手引导（从主菜单调用）。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.start_tutorial()
        if not result.get("success"):
            return False, result.get("message", "进入引导失败。"), True

        await self._renderer.send_dialogue_display(stream_id, result)
        return True, "进入新手引导", True

    @Command(
        "dsv_skip_tutorial",
        description="跳过新手引导，直接进入主菜单",
        pattern=r"^/dsv skip tutorial$",
        intercept_message_level=1,
    )
    async def handle_novel_skip_tutorial(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """跳过新手引导进入主菜单。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.skip_tutorial()
        if not result.get("success"):
            return False, result.get("message", "跳过引导失败。"), True

        await self.ctx.send.text(
            f"📖 已进入主菜单。\n"
            f"可用角色：{'、'.join(result.get('characters', []))}\n\n"
            f"输入 /dsv plot <角色名> 进入故事模式\n"
            f"输入 /dsv tutorial 可重新查看引导",
            stream_id,
        )
        return True, "已跳过新手引导", True

    @Command(
        "dsv_next",
        description="推进当前对话到下一节点",
        pattern=r"^/dsv next$",
        intercept_message_level=1,
    )
    async def handle_novel_next(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """推进对话到下一节点。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            await self.ctx.send.text("插件未正确加载。", stream_id)
            return False, "插件未正确加载。", True

        result = await self._renderer.advance_dialogue()
        if not result.get("success"):
            msg = result.get("message", "对话推进失败。")
            await self.ctx.send.text(msg, stream_id)
            return False, msg, True

        # 教程帮助验证：用户尚未使用 /dsv help，显示提醒
        if result.get("tutorial_help_required"):
            reminder = (
                f"{result.get('text', '')}\n\n"
                f"⚠️ {result.get('message', '请先输入 /dsv help 查看命令列表。')}"
            )
            fwd = self._renderer.forward_service
            if fwd:
                await fwd.send(stream_id, reminder)
            else:
                await self.ctx.send.text(reminder, stream_id)
            return True, "等待用户使用 /dsv help", True

        if result.get("waiting_next_confirm"):
            # 章节结束，等待玩家确认是否继续下一章
            next_title = result.get("next_script_title", "下一章")
            msg = (
                f"📖 本章剧情已完成！\n\n"
                f"下一章节《{next_title}》已就绪。\n"
                f"输入 /dsv next 继续剧情……"
            )
            fwd = self._renderer.forward_service
            if fwd:
                await fwd.send(stream_id, msg)
            else:
                await self.ctx.send.text(msg, stream_id)
            return True, "章节结束，等待继续", True

        if result.get("dialogue_ended"):
            chars = result.get("characters")
            fwd = self._renderer.forward_service
            if chars and fwd:
                await fwd.send(
                    stream_id,
                    f"{result['message']}\n\n可用角色：{'、'.join(chars)}",
                )
            elif fwd:
                await fwd.send(stream_id, result["message"])
            elif chars:
                await self.ctx.send.text(
                    f"{result['message']}\n\n可用角色：{'、'.join(chars)}",
                    stream_id,
                )
            else:
                await self.ctx.send.text(result["message"], stream_id)
            return True, "对话结束", True

        # 显示下一节点
        await self._renderer.send_dialogue_display(stream_id, result)
        return True, "对话推进", True

    # ==================== 出厂设置命令 ====================

    @Command(
        "dsv_factory_reset",
        description="重置插件至出厂设置（第一步：查看警告）",
        pattern=r"^/dsv factory_reset$",
        intercept_message_level=1,
    )
    async def handle_factory_reset_warning(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """出厂设置第一步：显示操作警告与确认指引。

        告知用户此操作的影响范围，要求用户输入确认指令
        '/dsv factory_reset confirm' 以继续。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            await self.ctx.send.text("插件未正确加载。", stream_id)
            return False, "插件未正确加载。", True

        warning_text = (
            "⚠️ 出厂设置操作确认\n\n"
            "此操作将永久清除以下所有用户数据：\n"
            "  1. 所有存档文件（data/saves/）\n"
            "  2. 所有剧情进度（data/plot/.progress.json）\n"
            "  3. 所有角色好感度数据\n"
            "  4. 所有选择记录\n"
            "  5. 当前游戏会话状态\n\n"
            "操作前会自动创建备份到 data/backups/<时间戳>/ 目录。\n"
            "清除后插件将回到首次安装时的初始状态。\n\n"
            "请输入 /dsv factory_reset confirm 确认执行此操作。\n"
            "输入其他命令或等待 60 秒可取消操作。"
        )
        await self.ctx.send.text(warning_text, stream_id)
        return True, "已显示出厂设置警告", True

    @Command(
        "dsv_factory_reset_confirm",
        description="确认执行出厂设置（第二步：执行清除）",
        pattern=r"^/dsv factory_reset confirm$",
        intercept_message_level=1,
    )
    async def handle_factory_reset_confirm(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """出厂设置第二步：执行备份与数据清除。

        先备份用户数据，再清除所有用户数据，最后验证结果。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            await self.ctx.send.text("插件未正确加载。", stream_id)
            return False, "插件未正确加载。", True

        # 第一步：备份
        backup_result = self._renderer.backup_user_data()
        if not backup_result.get("success"):
            await self.ctx.send.text(
                f"❌ 备份失败：{backup_result.get('message', '未知错误')}\n操作已中止，数据未被修改。",
                stream_id,
            )
            return False, backup_result.get("message", "备份失败"), True

        backup_path = backup_result.get("backup_path", "未知路径")

        # 第二步：执行清除
        reset_result = await self._renderer.factory_reset()
        if not reset_result.get("success"):
            await self.ctx.send.text(
                f"⚠️ 出厂设置部分失败。\n"
                f"已清除：{'、'.join(reset_result.get('cleared_items', []))}\n"
                f"错误：{'；'.join(reset_result.get('errors', []))}\n"
                f"备份位置：{backup_path}",
                stream_id,
            )
            return False, "出厂设置部分失败", True

        # 第三步：验证并报告
        cleared_items = "、".join(reset_result.get("cleared_items", []))
        verify_text = (
            f"✅ 出厂设置已完成\n\n"
            f"已清除：{cleared_items}\n"
            f"备份位置：{backup_path}\n"
            f"当前状态：{reset_result.get('state', 'IDLE')}\n\n"
            f"输入 /dsv start 可重新开始游戏。"
        )
        await self.ctx.send.text(verify_text, stream_id)
        return True, "出厂设置完成", True

    # ==================== Tool 工具（供 LLM 调用） ====================

    @Tool(
        "dsv_character_info",
        description="查看指定角色的详细信息，包括性格、背景、好感度等。在玩家询问角色情况时使用。",
        parameters=[
            ToolParameterInfo(name="character_name", param_type=ToolParamType.STRING, description="角色名称", required=True),
        ],
    )
    async def tool_character_info(self, character_name: str = "", **kwargs: Any) -> dict[str, Any]:
        """LLM 工具：获取指定角色的完整信息。

        包含角色设定、性格标签、好感度、喜好厌恶等数据。

        Args:
            character_name: 角色名称。

        Returns:
            Tool 标准返回值，content 为格式化的角色信息文本。
        """
        del kwargs
        if self._renderer is None:
            return {"name": "dsv_character_info", "content": "插件未正确加载。"}

        try:
            char = self._renderer.character.get_character(character_name)
            aff_value = self._renderer.affection.get_value(character_name)
            aff_level = self._renderer.affection.get_level(character_name)
            lines = [
                f"角色：{char.name}（{char.nickname}）",
                f"性格：{'、'.join(char.personality)}",
                f"背景：{char.background}",
                f"对话风格：{char.dialogue_style}",
                f"好感度：{aff_value}（{aff_level}）",
                f"喜好：{'、'.join(char.likes)}",
                f"厌恶：{'、'.join(char.dislikes)}",
                f"爱好：{'、'.join(char.hobbies)}",
            ]
            return {"name": "dsv_character_info", "content": "\n".join(lines)}
        except Exception as e:
            return {"name": "dsv_character_info", "content": f"获取角色信息失败：{e}"}

    @Tool(
        "dsv_game_status",
        description="查看当前视觉小说的游戏运行状态，包含当前状态、角色好感度等。在玩家询问游戏进度时使用。",
        parameters=[],
    )
    async def tool_game_status(self, **kwargs: Any) -> dict[str, Any]:
        """LLM 工具：获取游戏运行状态总览。

        Returns:
            Tool 标准返回值，content 为状态文本。
        """
        del kwargs
        if self._renderer is None:
            return {"name": "dsv_game_status", "content": "插件未正确加载。"}

        status = await self._renderer.get_game_status()
        lines = [
            f"当前游戏状态：{status['state']}",
        ]
        for name, state_data in status.get("affection_states", {}).items():
            lines.append(f"  {name}：好感度 {state_data['value']}（{state_data['level']}）")
        return {"name": "dsv_game_status", "content": "\n".join(lines)}

    @Tool(
        "dsv_list_characters",
        description="列出视觉小说中所有可攻略角色。在玩家想了解可选角色时使用。",
        parameters=[],
    )
    async def tool_list_characters(self, **kwargs: Any) -> dict[str, Any]:
        """LLM 工具：列出所有可攻略角色及其当前好感度。

        Returns:
            Tool 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            return {"name": "dsv_list_characters", "content": "插件未正确加载。"}

        characters = self._renderer.character.list_characters()
        if not characters:
            return {"name": "dsv_list_characters", "content": "暂无可攻略角色。"}
        lines = ["可攻略角色："]
        for name in characters:
            aff_value = self._renderer.affection.get_value(name)
            aff_level = self._renderer.affection.get_level(name)
            lines.append(f"  · {name}（好感度：{aff_value} - {aff_level}）")
        return {"name": "dsv_list_characters", "content": "\n".join(lines)}


# ==================== 工厂函数 ====================


def create_plugin() -> VisualNovelPlugin:
    """创建视觉小说插件实例。

    MaiBot 插件系统要求的工厂函数，返回插件主类的实例。

    Returns:
        初始化完成的 VisualNovelPlugin 实例。
    """
    return VisualNovelPlugin()
