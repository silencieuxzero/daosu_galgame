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

import os
from typing import Any

from maibot_sdk import Command, MaiBotPlugin, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

from .config import VisualNovelPluginConfig
from .modules.forward import ForwardMessageCollector
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
        self._collector: ForwardMessageCollector | None = None
        # 标记当前是否处于收集模式（对话/引导流程中）
        self._collecting_streams: set[str] = set()

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

        self._renderer = VisualNovelRenderer(
            data_dir,
            save_dir,
            tutorial_enabled=self.config.tutorial.enabled,
            tutorial_script_id=self.config.tutorial.script_id,
            affection_initial=self.config.affection.initial_value,
            affection_max=self.config.affection.max_value,
            affection_min=self.config.affection.min_value,
            max_save_slots=self.config.save.max_slots,
        )
        await self._renderer.initialize()

        # 初始化合并转发收集器
        self._collector = ForwardMessageCollector(
            bot_uin="",
            bot_name=self.config.forward.bot_name,
            napcat_url=self.config.forward.napcat_url,
            auto_flush=self.config.forward.auto_flush,
            display_title=self.config.forward.display_title,
            request_timeout=self.config.forward.request_timeout,
        )

    async def on_unload(self) -> None:
        """插件卸载时清理资源。

        调用 renderer 的 shutdown 方法，保存记事本数据并重置状态机。
        """
        if self._renderer:
            await self._renderer.shutdown()
            self._renderer = None
        self._collector = None
        self._collecting_streams.clear()

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

    async def _send_dialogue_display(self, result: dict[str, Any], stream_id: str) -> None:
        """将对话节点结果格式化为用户可读文本并发送。

        根据节点类型（旁白/角色、有选项/无选项）生成不同的展示格式。

        Args:
            result: renderer 返回的对话节点数据。
            stream_id: 消息流 ID。
        """
        speaker = result.get("speaker", "")
        text = result.get("text", "")
        emotion = result.get("emotion", "neutral")
        is_tutorial = result.get("is_tutorial", False)

        # 格式化说话者标签
        if speaker == "narrator":
            header = "📖" if not is_tutorial else "📖 新手引导"
        else:
            header = f"💬 {speaker}"

        lines = [f"{header}\n{text}"]

        choices = result.get("choices")
        if choices:
            lines.append("\n请选择：")
            for c in choices:
                lines.append(f"  /dsv choose {c['index']} — {c['text']}")
        else:
            lines.append("\n—— 输入 /dsv next 继续 ——")

        # 发送消息（通过合并转发管道或直接发送）
        sender = speaker if speaker != "narrator" else self.config.forward.bot_name
        await self._send_msg("\n".join(lines), stream_id, sender)

    # ==================== 合并转发辅助方法 ====================

    def _is_forward_enabled(self) -> bool:
        """检查合并转发是否启用。

        Returns:
            转发功能启用且收集器已初始化时返回 True。
        """
        return (
            self.config.forward.enabled
            and self._collector is not None
        )

    def _start_collecting(self, stream_id: str) -> None:
        """标记指定会话进入收集模式。

        在收集模式下，所有 _send_msg 调用会将消息缓冲到收集器，
        而非直接发送。

        Args:
            stream_id: 消息流 ID。
        """
        self._collecting_streams.add(stream_id)

    async def _flush_collected(self, stream_id: str) -> None:
        """结束收集模式并发送合并转发消息。

        将缓冲区中的所有消息通过 NapCat 合并转发发送，
        然后退出收集模式并清空缓冲区。

        Args:
            stream_id: 消息流 ID。
        """
        self._collecting_streams.discard(stream_id)
        if self._is_forward_enabled() and self._collector:
            result = await self._collector.flush(stream_id)
            if not result.get("success"):
                # 发送失败时降级：不阻塞用户
                pass

    async def _send_msg(self, content: str, stream_id: str, sender: str = "") -> None:
        """发送消息（根据配置选择收集或直发）。

        - 合并转发启用 + 收集模式：缓冲到收集器，等待合并发送
        - 其他情况：直接通过 ctx.send.text 发送

        Args:
            content: 消息文本内容。
            stream_id: 消息流 ID。
            sender: 发送者名称（用于合并转发节点）。
        """
        if self._is_forward_enabled() and stream_id in self._collecting_streams:
            sender_name = sender or self.config.forward.bot_name
            self._collector.add(stream_id, sender_name, content)
        else:
            await self.ctx.send.text(content, stream_id)

    # ==================== Command 命令 ====================

    @Command(
        "dsv_start",
        description="启动视觉小说",
        pattern=r"^/dsv start$",
    )
    async def handle_novel_start(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """启动视觉小说游戏。

        首次游玩时自动进入新手引导，否则直接进入主菜单。

        Returns:
            Command 标准返回值，包含启动结果文本。
        """
        del kwargs
        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.start_game()

        if result.get("is_tutorial"):
            self._start_collecting(stream_id)
            await self._send_dialogue_display(result, stream_id)
            return True, "进入新手引导", True

        # 非首次/非引导：直接发送
        await self.ctx.send.text(
            f"📖 视觉小说已启动！\n"
            f"可用角色：{'、'.join(result.get('characters', []))}\n\n"
            f"输入 /dsv explore <角色名> 开始探索\n"
            f"输入 /dsv status 查看游戏状态",
            stream_id,
        )
        return True, "视觉小说已启动", True

    @Command(
        "dsv_explore",
        description="与指定角色开始日常对话探索",
        pattern=r"^/dsv explore\s+(?P<character>.+)$",
    )
    async def handle_novel_explore(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """进入与指定角色的探索模式。

        切换到 EXPLORATION 状态，显示角色好感度信息和可用指令。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        character_name = str(matched_groups.get("character", "")).strip()

        if not character_name:
            return False, "请指定角色名。用法：/dsv explore <角色名>", True

        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.start_exploration(character_name)
        if not result.get("success"):
            return False, result.get("message", "操作失败。"), True

        await self.ctx.send.text(
            f"💬 与 {character_name} 的日常对话已开始。\n"
            f"好感度等级：{result['affection_level']}（{result['affection_value']}）\n\n"
            f"可用指令：\n"
            f"  /dsv gift <礼物名> — 赠送礼物\n"
            f"  /dsv invite <活动名> — 邀请活动\n"
            f"  /dsv notebook — 查看记事本\n"
            f"  /dsv save <槽位> — 存档\n"
            f"  /dsv status — 状态",
            stream_id,
        )
        return True, f"开始与 {character_name} 探索", True

    @Command(
        "dsv_status",
        description="查看当前游戏状态",
        pattern=r"^/dsv status$",
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
        for name, state_data in status.get("affection_states", {}).items():
            lines.append(f"  {name}：好感度 {state_data['value']}（{state_data['level']}）")

        await self.ctx.send.text("\n".join(lines), stream_id)
        return True, "已显示游戏状态", True

    @Command(
        "dsv_notebook",
        description="查看记事本",
        pattern=r"^/dsv notebook\s*(?P<character>.*)$",
    )
    async def handle_novel_notebook(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """查看记事本中的线索记录。

        可选指定角色名，查看该角色的专属线索。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 matched_groups 中的 character 参数。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        character_name = str(matched_groups.get("character", "")).strip() or None

        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.show_notebook(character_name)
        await self.ctx.send.text(result["summary"], stream_id)
        return True, "已显示记事本", True

    @Command(
        "dsv_gift",
        description="向角色赠送礼物",
        pattern=r"^/dsv gift\s+(?P<character>.+?)\s+(?P<gift>.+)$",
    )
    async def handle_novel_gift(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """赠送礼物给指定角色。

        支持从玩家背包中选择礼物赠送，附带记事本线索提示。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 character 和 gift 参数。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        character_name = str(matched_groups.get("character", "")).strip()
        gift_name = str(matched_groups.get("gift", "")).strip()

        if not character_name or not gift_name:
            return False, "用法：/dsv gift <角色名> <礼物名>", True

        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.give_gift(character_name, gift_name)
        if not result.get("success"):
            return False, result.get("message", "赠送礼物失败。"), True

        hint = result.get("hint")
        msg = result["message"]
        if hint:
            msg += f"\n{hint}"

        await self.ctx.send.text(msg, stream_id)
        return True, msg, True

    @Command(
        "dsv_invite",
        description="邀请角色参加活动",
        pattern=r"^/dsv invite\s+(?P<character>.+?)\s+(?P<activity>.+)$",
    )
    async def handle_novel_invite(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """邀请角色参加活动。

        根据活动类型和角色关系影响好感度。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 character 和 activity 参数。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        character_name = str(matched_groups.get("character", "")).strip()
        activity_name = str(matched_groups.get("activity", "")).strip()

        if not character_name or not activity_name:
            return False, "用法：/dsv invite <角色名> <活动名>", True

        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.invite_activity(character_name, activity_name)
        if not result.get("success"):
            return False, result.get("message", "邀请失败。"), True

        await self.ctx.send.text(result["message"], stream_id)
        return True, result["message"], True

    @Command(
        "dsv_save",
        description="保存游戏进度",
        pattern=r"^/dsv save\s+(?P<slot>\d+)\s*(?P<label>.*)$",
    )
    async def handle_novel_save(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """保存游戏到指定槽位。

        保存内容包括好感度、记事本、互动状态、选择历史等。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 slot 和 label 参数。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        slot_id = int(matched_groups.get("slot", 0))
        label = str(matched_groups.get("label", "")).strip()

        if slot_id < 1 or slot_id > 20:
            return False, "槽位编号范围为 1-20。", True

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
    )
    async def handle_novel_load(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """读取指定槽位的存档。

        恢复好感度、记事本、互动状态等全部数据。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 slot 参数。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        slot_id = int(matched_groups.get("slot", 0))

        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.load_game(slot_id)
        if not result.get("success"):
            return False, result.get("message", "读档失败。"), True

        await self.ctx.send.text(result["message"], stream_id)
        return True, result["message"], True

    @Command(
        "dsv_help",
        description="查看视觉小说插件帮助信息",
        pattern=r"^/dsv help$",
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
            "  /dsv explore <角色名> — 与角色开始日常对话\n"
            "  /dsv next — 推进对话\n"
            "  /dsv choose <编号> — 选择对话选项\n"
            "  /dsv gift <角色名> <礼物名> — 赠送礼物\n"
            "  /dsv invite <角色名> <活动名> — 邀请活动\n"
            "  /dsv notebook [角色名] — 查看记事本\n"
            "  /dsv status — 查看游戏状态\n"
            "  /dsv save <槽位1-20> [标签] — 存档\n"
            "  /dsv load <槽位1-20> — 读档\n"
            "  /dsv skip tutorial — 跳过引导\n"
            "  /dsv help — 显示此帮助"
        )
        await self.ctx.send.text(help_text, stream_id)
        return True, "已显示帮助信息", True

    @Command(
        "dsv_tutorial",
        description="重新进入新手引导",
        pattern=r"^/dsv tutorial$",
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

        self._start_collecting(stream_id)
        await self._send_dialogue_display(result, stream_id)
        return True, "进入新手引导", True

    @Command(
        "dsv_skip_tutorial",
        description="跳过新手引导，直接进入主菜单",
        pattern=r"^/dsv skip tutorial$",
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

        # 跳过引导时：先发送已收集的消息（如果有），再发主菜单提示
        await self._flush_collected(stream_id)
        await self.ctx.send.text(
            f"📖 已进入主菜单。\n"
            f"可用角色：{'、'.join(result.get('characters', []))}\n\n"
            f"输入 /dsv explore <角色名> 开始探索\n"
            f"输入 /dsv tutorial 可重新查看引导",
            stream_id,
        )
        return True, "已跳过新手引导", True

    @Command(
        "dsv_next",
        description="推进当前对话到下一节点",
        pattern=r"^/dsv next$",
    )
    async def handle_novel_next(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """推进对话到下一节点。

        当对话节点没有选项时使用此命令自动推进。
        如果有选项会转为等待选择状态。

        Returns:
            Command 标准返回值。
        """
        del kwargs
        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.advance_dialogue()
        if not result.get("success"):
            return False, result.get("message", "对话推进失败。"), True

        if result.get("dialogue_ended"):
            # 先发送已收集的消息（合并转发）
            await self._flush_collected(stream_id)
            # 再发送结束提示
            chars = result.get("characters")
            if chars:
                await self.ctx.send.text(
                    f"{result['message']}\n\n可用角色：{'、'.join(chars)}",
                    stream_id,
                )
            else:
                await self.ctx.send.text(result["message"], stream_id)
            return True, "对话结束", True

        if result.get("awaiting_choice"):
            # 有选项分支，显示选项
            choices = result.get("choices", [])
            lines = [result.get("text", "")]
            lines.append("\n请选择：")
            for c in choices:
                lines.append(f"  /dsv choose {c['index']} — {c['text']}")
            await self._send_msg("\n".join(lines), stream_id,
                                 self.config.forward.bot_name)
            return True, "等待选择", True

        # 线性推进，显示下一节点
        await self._send_dialogue_display(result, stream_id)
        return True, "对话推进", True

    @Command(
        "dsv_choose",
        description="在对话中选择一个选项",
        pattern=r"^/dsv choose\s+(?P<choice>\d+)$",
    )
    async def handle_novel_choose(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """在对话分支中选择一个选项。

        Args:
            stream_id: 消息流 ID。
            kwargs: 包含 choice 参数（选项索引）。

        Returns:
            Command 标准返回值。
        """
        matched_groups = kwargs.get("matched_groups", {})
        try:
            choice_index = int(matched_groups.get("choice", -1))
        except (ValueError, TypeError):
            return False, "用法：/dsv choose <选项编号>", True

        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.make_choice(choice_index)
        if not result.get("success"):
            return False, result.get("message", "选择无效。"), True

        await self._send_dialogue_display(result, stream_id)
        return True, f"已选择选项 {choice_index}", True

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
        "dsv_gift_hints",
        description="查看赠送礼物给角色时的线索提示。在玩家不确定送什么礼物时使用。",
        parameters=[
            ToolParameterInfo(name="character_name", param_type=ToolParamType.STRING, description="角色名称", required=True),
        ],
    )
    async def tool_gift_hints(self, character_name: str = "", **kwargs: Any) -> dict[str, Any]:
        """LLM 工具：获取记事本中关于角色喜好的礼物线索。

        Args:
            character_name: 角色名称。

        Returns:
            Tool 标准返回值，content 为线索文本。
        """
        del kwargs
        if self._renderer is None:
            return {"name": "dsv_gift_hints", "content": "插件未正确加载。"}

        hints = self._renderer.notebook.get_gift_hints(character_name)
        if hints:
            return {"name": "dsv_gift_hints", "content": "\n".join(hints)}
        return {
            "name": "dsv_gift_hints",
            "content": f"关于 {character_name}，记事本中暂无礼物线索。继续对话了解更多吧！",
        }

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
