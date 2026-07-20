"""视觉小说插件 — 配置模型。

集中定义插件的所有配置段，包括：
- PluginSectionConfig: 插件基础开关
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

    enabled: bool = Field(default=False, description="是否启用插件",
                          json_schema_extra={"label": "启用插件"})
    config_version: str = Field(default="1.1.0", description="配置版本",
                                json_schema_extra={"label": "配置版本"})


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
        default="plugins/daosu_galgame/data",
        description="角色数据与事件数据目录（相对项目根）",
        json_schema_extra={"label": "数据目录"},
    )
    save_dir: str = Field(
        default="plugins/daosu_galgame/data/saves",
        description="存档文件存放目录",
        json_schema_extra={"label": "存档目录"},
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

    enabled: bool = Field(default=True, description="是否启用新手引导",
                          json_schema_extra={"label": "启用新手引导"})
    script_id: str = Field(default="tutorial_intro", description="引导对话脚本 ID",
                           json_schema_extra={"label": "引导脚本 ID"})


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

    initial_value: int = Field(default=0, description="新角色初始好感度",
                               json_schema_extra={"label": "初始好感度"})
    max_value: int = Field(default=100, description="好感度上限",
                           json_schema_extra={"label": "好感度上限"})
    min_value: int = Field(default=-100, description="好感度下限",
                           json_schema_extra={"label": "好感度下限"})


class SaveConfig(PluginConfigBase):
    """存档参数配置。

    Attributes:
        max_slots: 最大存档槽位数量。
    """

    __ui_label__ = "存档"
    __ui_icon__ = "save"
    __ui_order__ = 5

    max_slots: int = Field(default=20, description="最大存档槽位数",
                           json_schema_extra={"label": "最大存档槽位"})


class ForwardConfig(PluginConfigBase):
    """合并转发消息配置。

    控制消息是否通过 Host send.forward 以合并转发格式发送。
    启用后，每条消息包装为单个转发节点即时发送；关闭时直接发送文本。

    Attributes:
        enabled: 是否启用合并转发。关闭时消息直接发送。
        bot_name: 机器人在转发消息中的显示名称。
    """

    __ui_label__ = "合并转发"
    __ui_icon__ = "forward"
    __ui_order__ = 6

    enabled: bool = Field(default=False, description="是否启用合并转发（关闭时消息逐条发送，便于阅读）",
                          json_schema_extra={"label": "启用合并转发"})
    bot_name: str = Field(default="悼溯茶馆", description="机器人显示名称",
                          json_schema_extra={"label": "机器人名称"})


class ChatConfig(PluginConfigBase):
    """自由聊天模式配置。

    Attributes:
        default_model: 默认 LLM 模型名称，留空则使用 "replyer"。
    """

    __ui_label__ = "自由聊天"
    __ui_icon__ = "message-square"
    __ui_order__ = 7

    default_model: str = Field(default="replyer", description="默认 LLM 模型（留空自动回退 replyer）",
                                json_schema_extra={"label": "默认模型"})


class VisualNovelPluginConfig(PluginConfigBase):
    """视觉小说插件配置。

    聚合插件、数据、引导、好感度、存档、合并转发、自由聊天七部分配置。
    """

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig, description="插件基础配置（启用开关、配置版本）",
                                        json_schema_extra={"label": "插件"})
    data: DataConfig = Field(default_factory=DataConfig, description="数据路径配置（数据目录、存档目录）",
                             json_schema_extra={"label": "数据"})
    tutorial: TutorialConfig = Field(default_factory=TutorialConfig, description="新手引导配置（启用开关、引导脚本）",
                                     json_schema_extra={"label": "新手引导"})
    affection: AffectionConfig = Field(default_factory=AffectionConfig, description="好感度参数配置（初始值、上下限）",
                                       json_schema_extra={"label": "好感度"})
    save: SaveConfig = Field(default_factory=SaveConfig, description="存档参数配置（最大槽位数）",
                             json_schema_extra={"label": "存档"})
    forward: ForwardConfig = Field(default_factory=ForwardConfig, description="合并转发消息配置（启用、自动发送、标题、机器人名）",
                                   json_schema_extra={"label": "合并转发"})
    chat: ChatConfig = Field(default_factory=ChatConfig, description="自由聊天模式配置（LLM 模型）",
                             json_schema_extra={"label": "自由聊天"})
