"""视觉小说插件 — 入口与协调层。

plugin.py 仅作为插件入口与核心协调层，负责：
- 模块注册与生命周期管理
- 对外暴露 Command / Tool / EventHandler 接口
- 将请求委托给 renderer.py 处理
具体业务逻辑下沉至各功能模块。
"""

from __future__ import annotations

import os
from typing import Any

from maibot_sdk import Command, EventHandler, Field, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

from .renderer import VisualNovelRenderer

# ==================== 配置模型 ====================


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=False, description="是否启用插件")
    config_version: str = Field(default="1.0.0", description="配置版本")


class GameConfig(PluginConfigBase):
    """游戏运行配置。"""

    __ui_label__ = "游戏"
    __ui_icon__ = "gamepad-2"
    __ui_order__ = 1

    default_gifts: list[str] = Field(
        default=["花束", "手工饼干", "音乐盒", "巧克力"],
        description="初始赠送的礼物列表",
    )


class DataConfig(PluginConfigBase):
    """数据路径配置。"""

    __ui_label__ = "数据"
    __ui_icon__ = "folder"
    __ui_order__ = 2

    data_dir: str = Field(
        default="plugins/visual_novel/data",
        description="角色数据与事件数据目录（相对项目根）",
    )
    save_dir: str = Field(
        default="plugins/visual_novel/data/saves",
        description="存档文件存放目录",
    )


class VisualNovelPluginConfig(PluginConfigBase):
    """视觉小说插件配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    game: GameConfig = Field(default_factory=GameConfig)
    data: DataConfig = Field(default_factory=DataConfig)


# ==================== 插件主类 ====================


class VisualNovelPlugin(MaiBotPlugin):
    """视觉小说插件主类。

    职责限定：
    - 管理插件生命周期
    - 注册 Command/Tool/EventHandler
    - 委托请求给 renderer
    """

    config_model = VisualNovelPluginConfig

    def __init__(self) -> None:
        super().__init__()
        self._renderer: VisualNovelRenderer | None = None

    # ==================== 生命周期 ====================

    async def on_load(self) -> None:
        """插件加载时初始化渲染器。"""
        # 解析数据目录（支持相对路径）
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        data_dir = self._resolve_path(project_root, self.config.data.data_dir)
        save_dir = self._resolve_path(project_root, self.config.data.save_dir)

        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(save_dir, exist_ok=True)

        self._renderer = VisualNovelRenderer(data_dir, save_dir)
        await self._renderer.initialize()

    async def on_unload(self) -> None:
        """插件卸载时清理资源。"""
        if self._renderer:
            await self._renderer.shutdown()
            self._renderer = None

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        """配置热更新。"""
        del scope, config_data, version
        if self._renderer:
            await self._renderer.reload()

    def _resolve_path(self, project_root: str, configured_path: str) -> str:
        """解析配置路径（相对路径基于项目根，绝对路径原样保留）。"""
        if os.path.isabs(configured_path):
            return configured_path
        return os.path.join(project_root, configured_path)

    # ==================== Command 命令 ====================

    @Command(
        "novel_start",
        description="启动视觉小说",
        pattern=r"^/novel_start$",
    )
    async def handle_novel_start(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """启动视觉小说游戏。"""
        del kwargs
        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.start_game()
        await self.ctx.send.text(
            f"📖 视觉小说已启动！\n"
            f"可用角色：{'、'.join(result.get('characters', []))}\n\n"
            f"输入 /novel_explore <角色名> 开始探索\n"
            f"输入 /novel_status 查看游戏状态",
            stream_id,
        )
        return True, "视觉小说已启动", True

    @Command(
        "novel_explore",
        description="与指定角色开始日常对话探索",
        pattern=r"^/novel_explore\s+(?P<character>.+)$",
    )
    async def handle_novel_explore(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """进入探索模式。"""
        matched_groups = kwargs.get("matched_groups", {})
        character_name = str(matched_groups.get("character", "")).strip()

        if not character_name:
            return False, "请指定角色名。用法：/novel_explore <角色名>", True

        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.start_exploration(character_name)
        if not result.get("success"):
            return False, result.get("message", "操作失败。"), True

        await self.ctx.send.text(
            f"💬 与 {character_name} 的日常对话已开始。\n"
            f"好感度等级：{result['affection_level']}（{result['affection_value']}）\n\n"
            f"可用指令：\n"
            f"  /novel_gift <礼物名> — 赠送礼物\n"
            f"  /novel_invite <活动名> — 邀请活动\n"
            f"  /novel_notebook — 查看记事本\n"
            f"  /novel_save <槽位> — 存档\n"
            f"  /novel_status — 状态",
            stream_id,
        )
        return True, f"开始与 {character_name} 探索", True

    @Command(
        "novel_status",
        description="查看当前游戏状态",
        pattern=r"^/novel_status$",
    )
    async def handle_novel_status(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """查看游戏状态。"""
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
        "novel_notebook",
        description="查看记事本",
        pattern=r"^/novel_notebook\s*(?P<character>.*)$",
    )
    async def handle_novel_notebook(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """查看记事本。"""
        matched_groups = kwargs.get("matched_groups", {})
        character_name = str(matched_groups.get("character", "")).strip() or None

        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.show_notebook(character_name)
        await self.ctx.send.text(result["summary"], stream_id)
        return True, "已显示记事本", True

    @Command(
        "novel_gift",
        description="向角色赠送礼物",
        pattern=r"^/novel_gift\s+(?P<character>.+?)\s+(?P<gift>.+)$",
    )
    async def handle_novel_gift(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """赠送礼物。"""
        matched_groups = kwargs.get("matched_groups", {})
        character_name = str(matched_groups.get("character", "")).strip()
        gift_name = str(matched_groups.get("gift", "")).strip()

        if not character_name or not gift_name:
            return False, "用法：/novel_gift <角色名> <礼物名>", True

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
        "novel_invite",
        description="邀请角色参加活动",
        pattern=r"^/novel_invite\s+(?P<character>.+?)\s+(?P<activity>.+)$",
    )
    async def handle_novel_invite(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """邀请角色参加活动。"""
        matched_groups = kwargs.get("matched_groups", {})
        character_name = str(matched_groups.get("character", "")).strip()
        activity_name = str(matched_groups.get("activity", "")).strip()

        if not character_name or not activity_name:
            return False, "用法：/novel_invite <角色名> <活动名>", True

        if self._renderer is None:
            return False, "插件未正确加载。", True

        result = await self._renderer.invite_activity(character_name, activity_name)
        if not result.get("success"):
            return False, result.get("message", "邀请失败。"), True

        await self.ctx.send.text(result["message"], stream_id)
        return True, result["message"], True

    @Command(
        "novel_save",
        description="保存游戏进度",
        pattern=r"^/novel_save\s+(?P<slot>\d+)\s*(?P<label>.*)$",
    )
    async def handle_novel_save(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """存档。"""
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
        "novel_load",
        description="读取游戏存档",
        pattern=r"^/novel_load\s+(?P<slot>\d+)$",
    )
    async def handle_novel_load(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """读档。"""
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
        "novel_help",
        description="查看视觉小说插件帮助信息",
        pattern=r"^/novel_help$",
    )
    async def handle_novel_help(self, stream_id: str = "", **kwargs: Any) -> bool | tuple[bool, str, bool]:
        """帮助。"""
        del kwargs
        help_text = (
            "📖 视觉小说插件帮助\n\n"
            "可用命令：\n"
            "  /novel_start — 启动游戏\n"
            "  /novel_explore <角色名> — 与角色开始日常对话\n"
            "  /novel_gift <角色名> <礼物名> — 赠送礼物\n"
            "  /novel_invite <角色名> <活动名> — 邀请活动\n"
            "  /novel_notebook [角色名] — 查看记事本\n"
            "  /novel_status — 查看游戏状态\n"
            "  /novel_save <槽位1-20> [标签] — 存档\n"
            "  /novel_load <槽位1-20> — 读档\n"
            "  /novel_help — 显示此帮助"
        )
        await self.ctx.send.text(help_text, stream_id)
        return True, "已显示帮助信息", True

    # ==================== Tool 工具（供 LLM 调用） ====================

    @Tool(
        "novel_character_info",
        description="查看指定角色的详细信息，包括性格、背景、好感度等。在玩家询问角色情况时使用。",
        parameters=[
            ToolParameterInfo(name="character_name", param_type=ToolParamType.STRING, description="角色名称", required=True),
        ],
    )
    async def tool_character_info(self, character_name: str = "", **kwargs: Any) -> dict[str, Any]:
        """LLM 工具：获取角色信息。"""
        del kwargs
        if self._renderer is None:
            return {"name": "novel_character_info", "content": "插件未正确加载。"}

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
            return {"name": "novel_character_info", "content": "\n".join(lines)}
        except Exception as e:
            return {"name": "novel_character_info", "content": f"获取角色信息失败：{e}"}

    @Tool(
        "novel_game_status",
        description="查看当前视觉小说的游戏运行状态，包含当前状态、角色好感度等。在玩家询问游戏进度时使用。",
        parameters=[],
    )
    async def tool_game_status(self, **kwargs: Any) -> dict[str, Any]:
        """LLM 工具：获取游戏状态。"""
        del kwargs
        if self._renderer is None:
            return {"name": "novel_game_status", "content": "插件未正确加载。"}

        status = await self._renderer.get_game_status()
        lines = [
            f"当前游戏状态：{status['state']}",
        ]
        for name, state_data in status.get("affection_states", {}).items():
            lines.append(f"  {name}：好感度 {state_data['value']}（{state_data['level']}）")
        return {"name": "novel_game_status", "content": "\n".join(lines)}

    @Tool(
        "novel_gift_hints",
        description="查看赠送礼物给角色时的线索提示。在玩家不确定送什么礼物时使用。",
        parameters=[
            ToolParameterInfo(name="character_name", param_type=ToolParamType.STRING, description="角色名称", required=True),
        ],
    )
    async def tool_gift_hints(self, character_name: str = "", **kwargs: Any) -> dict[str, Any]:
        """LLM 工具：获取礼物线索。"""
        del kwargs
        if self._renderer is None:
            return {"name": "novel_gift_hints", "content": "插件未正确加载。"}

        hints = self._renderer.notebook.get_gift_hints(character_name)
        if hints:
            return {"name": "novel_gift_hints", "content": "\n".join(hints)}
        return {
            "name": "novel_gift_hints",
            "content": f"关于 {character_name}，记事本中暂无礼物线索。继续对话了解更多吧！",
        }

    @Tool(
        "novel_list_characters",
        description="列出视觉小说中所有可攻略角色。在玩家想了解可选角色时使用。",
        parameters=[],
    )
    async def tool_list_characters(self, **kwargs: Any) -> dict[str, Any]:
        """LLM 工具：列出角色。"""
        del kwargs
        if self._renderer is None:
            return {"name": "novel_list_characters", "content": "插件未正确加载。"}

        characters = self._renderer.character.list_characters()
        if not characters:
            return {"name": "novel_list_characters", "content": "暂无可攻略角色。"}
        lines = ["可攻略角色："]
        for name in characters:
            aff_value = self._renderer.affection.get_value(name)
            aff_level = self._renderer.affection.get_level(name)
            lines.append(f"  · {name}（好感度：{aff_value} - {aff_level}）")
        return {"name": "novel_list_characters", "content": "\n".join(lines)}


# ==================== 工厂函数 ====================


def create_plugin() -> VisualNovelPlugin:
    """创建视觉小说插件实例。"""
    return VisualNovelPlugin()
