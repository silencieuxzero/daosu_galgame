"""功能模块包。

包含视觉小说插件的七大业务模块，覆盖完整游戏功能：
- character：角色系统，加载与管理角色 prompt 数据
- dialogue：对话系统，管理 JSON 驱动的节点式剧情
- affection：好感度系统，管理角色好感度的数值与等级
- plot：分段式剧情对话系统，支持 /dsv plot 命令的交互式剧情推进
- say_chat：自由聊天系统，支持 /dsv chat 命令的 LLM 驱动实时对话
- save_manager：存档系统，支持多槽位 JSON 持久化
- forward：合并转发消息服务，封装消息发送逻辑

所有模块通过 renderer.py 统一加载与调度，模块间通过交叉引用协作。
"""
