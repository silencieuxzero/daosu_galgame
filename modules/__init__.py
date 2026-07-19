"""功能模块包。

包含视觉小说插件的六大业务模块，覆盖完整游戏功能：
- character：角色系统，加载与管理角色 prompt 数据
- dialogue：对话系统，管理 JSON 驱动的节点式剧情
- affection：好感度系统，管理角色好感度的数值与等级
- notebook：记事本与线索系统，记录对话中发现的喜好线索
- interaction：互动行为系统，支持礼物赠送与邀约活动
- said：分段式剧情对话系统，支持 /dsv said 命令的交互式剧情推进
- save_manager：存档系统，支持多槽位 JSON 持久化

所有模块通过 renderer.py 统一加载与调度，模块间通过交叉引用协作。
"""
