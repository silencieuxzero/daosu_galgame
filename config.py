"""视觉小说插件 — 配置模型。

集中定义插件的所有配置段，包括：
- PluginSectionConfig: 插件基础开关
- GameConfig: 游戏运行参数
- DataConfig: 数据路径
- TutorialConfig: 新手引导
- AffectionConfig: 好感度参数
- SaveConfig: 存档参数
- ForwardConfig: 合并转发消息
- VisualNovelPluginConfig: 聚合入口
"""

from __future__ import annotations

from maibot_sdk import Field, PluginConfigBase


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置。

    控制插件的启用状态和配置版本。

    Attributes:
        enabled: 是否启用插件。
        config_version: 配置版本号，用于热更新兼容性判断。
    """

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=False, description="是否启用插件")
    config_version: str = Field(default="1.0.1", description="配置版本")


class GameConfig(PluginConfigBase):
    """游戏运行配置。

    控制游戏初始运行参数。

    Attributes:
        default_gifts: 初始添加到玩家背包的默认礼物列表。
    """

    __ui_label__ = "游戏"
    __ui_icon__ = "gamepad-2"
    __ui_order__ = 1

    default_gifts: list[str] = Field(
        default=["花束", "手工饼干", "音乐盒", "巧克力"],
        description="初始赠送的礼物列表",
    )


class DataConfig(PluginConfigBase):
    """数据路径配置。

    指定插件数据的磁盘路径。

    Attributes:
        data_dir: 角色数据与事件数据目录路径。
        save_dir: 存档文件存放目录路径。
    """

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


class TutorialConfig(PluginConfigBase):
    """新手引导配置。

    Attributes:
        enabled: 是否启用首次进入时的新手引导。
        script_id: 引导对话脚本 ID。
    """

    __ui_label__ = "引导"
    __ui_icon__ = "book-open"
    __ui_order__ = 3

    enabled: bool = Field(default=True, description="是否启用新手引导")
    script_id: str = Field(default="tutorial_intro", description="引导对话脚本 ID")


class AffectionConfig(PluginConfigBase):
    """好感度参数配置。

    Attributes:
        initial_value: 新角色初始好感度数值。
        max_value: 好感度上限。
        min_value: 好感度下限。
    """

    __ui_label__ = "好感度"
    __ui_icon__ = "heart"
    __ui_order__ = 4

    initial_value: int = Field(default=0, description="新角色初始好感度")
    max_value: int = Field(default=100, description="好感度上限")
    min_value: int = Field(default=-100, description="好感度下限")


class SaveConfig(PluginConfigBase):
    """存档参数配置。

    Attributes:
        max_slots: 最大存档槽位数量。
    """

    __ui_label__ = "存档"
    __ui_icon__ = "save"
    __ui_order__ = 5

    max_slots: int = Field(default=20, description="最大存档槽位数")


class ForwardConfig(PluginConfigBase):
    """合并转发消息配置。

    控制多段消息是否通过 NapCat 合并转发发送。
    启用后，同一命令产生的多条消息将被收集并合并为一条转发消息。

    Attributes:
        enabled: 是否启用合并转发。关闭时消息逐条发送。
        auto_flush: 是否在对话/引导结束时自动合并发送。
        display_title: 合并转发消息显示的标题摘要。
        bot_name: 机器人在转发消息中的显示名称。
        napcat_url: NapCat HTTP API 地址。
        request_timeout: HTTP 请求超时秒数。
    """

    __ui_label__ = "合并转发"
    __ui_icon__ = "forward"
    __ui_order__ = 6

    enabled: bool = Field(default=True, description="是否启用合并转发")
    auto_flush: bool = Field(default=True, description="对话/引导结束时自动合并发送")
    display_title: str = Field(default="悼溯茶馆 · 消息记录", description="转发消息标题摘要")
    bot_name: str = Field(default="悼溯茶馆", description="机器人显示名称")
    napcat_url: str = Field(default="http://127.0.0.1:3000", description="NapCat HTTP API 地址")
    request_timeout: int = Field(default=10, description="HTTP 请求超时秒数")


class VisualNovelPluginConfig(PluginConfigBase):
    """视觉小说插件配置。

    聚合插件、游戏、数据、引导、好感度、存档、合并转发七部分配置。
    """

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    game: GameConfig = Field(default_factory=GameConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    tutorial: TutorialConfig = Field(default_factory=TutorialConfig)
    affection: AffectionConfig = Field(default_factory=AffectionConfig)
    save: SaveConfig = Field(default_factory=SaveConfig)
    forward: ForwardConfig = Field(default_factory=ForwardConfig)
