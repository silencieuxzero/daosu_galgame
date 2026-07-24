# 变更日志

## 1.2.4 (2026-07-24)

### 新增功能

- **新增 `/dsv ct` 命令**：从已加载的存档继续游戏。玩家先使用 `/dsv load <槽位>` 加载存档，再执行 `/dsv ct` 即可恢复到存档时的脚本和节点位置继续游玩
- **存档包含剧情进度**：`SaveSlot` 新增 `completed_scripts` 字段，存档时自动记录各角色已完成的章节进度
- **`/dsv start` 清除全部进度**：开始新游戏时自动清空 `data/plot/.progress.json`，确保从头开始
- **`/dsv load` 恢复剧情进度**：加载存档时自动将存档中的已完成章节列表写回 `.progress.json`，实现进度完整恢复
- **PlotManager 新增公开方法**：`resume_script(script_id, node_id)` 从指定节点恢复剧情；`get_script_by_id()` 按 ID 查找脚本；`dump_progress()` / `restore_progress()` 导出/恢复进度

### Bug 修复

- **修复 `/dsv plot` 失败时无用户可见输出**：所有剧情相关命令（`dsv_plot`、`dsv_plot_exit`、`dsv_choose`、`dsv_next`、`dsv_load`）的错误消息现在正确发送给用户，此前仅写入框架日志
- **修复 PLOT_SCRIPT 状态下存档不记录剧情位置**：`save_game()` 现在根据 FSM 状态自动选择 `plot_mgr` 或 `dialogue_mgr` 获取当前脚本/节点，确保剧情模式下存档包含正确的脚本进度数据

### 变更

- **`/dsv plot` 帮助文本**：从"开始/继续剧情章节"改为"开始剧情章节"，继续功能由 `/dsv ct` 独立承担
- **帮助命令**：新增 `/dsv ct` 条目；读档/继续流程说明
- **`start_plot` 清除已加载存档标记**：开始新剧情时自动清除 `_loaded_slot`，防止与 `/dsv ct` 产生状态交叉
- **版本号**：更新为 1.2.4

## 1.2.3 (2026-07-20)

### 新增功能

- **恢复 `/dsv choose <编号>` 命令**：在剧情模式（`/dsv plot`）中可选择选项分支，非剧情模式不可用
- **剧情选项增强**：倾诉烦恼状态的节点（sad/anxious/frustrated/venting）自动添加"静静听着"选项，选择后好感度 +5

### 变更

- **剧情推进不再自动选第一项**：`PlotManager.advance()` 遇到有选项的节点仅展示选项列表，等待玩家通过 `/dsv choose` 手动选择
- **选项展示带编号**：选项列表改为 `1. 选项文本` 格式，并增加 `/dsv choose <编号>` 提示
- **版本号**：更新为 1.2.3

## 1.2.2 (2026-07-20)

### 移除功能

- **移除 `/dsv choose` 命令**：删除选项选择命令，所有对话中的选项分支自动选择第一项推进
- **删除 `AWAITING_CHOICE` FSM 状态**：移除等待玩家选择状态及所有相关转换规则
- **移除 `renderer.make_choice()` 和 `renderer.plot_make_choice()`**：删除选择调度器
- **移除 `PlotManager.make_choice()`**：删除剧情引擎的选择方法，`advance()` 改为自动选第一项
- **移除 `dialogue.py` 中过时的选择提示**：更新 `send_dialogue` 中 `/dsv choose` 提示文本
- **更新命令描述**：`/dsv next` 改为通用推进命令（自动处理有选项的节点）
- **FSM 精简**：状态从 10 种减少到 9 种
- **更新文档**：同步更新 README 和 CHANGELOG

## 1.2.1 (2026-07-20)

### 移除功能

- **移除 `/dsv explore` 命令**：删除探索模式入口，用户可通过 `/dsv plot` 进入游戏模式
- **移除 `/dsv notebook` 命令及相关模块**：删除记事本与线索系统（`modules/notebook.py`），不再记录对话线索
- **移除 `/dsv gift` 命令及相关模块**：删除礼物赠送系统（`modules/interaction.py` 中的礼物部分），不再支持送礼
- **移除 `/dsv invite` 命令及相关模块**：删除邀约活动系统（`modules/interaction.py` 中的邀约部分），不再支持邀约
- **移除 `dsv_gift_hints` LLM 工具**：删除礼物线索提示功能
- **删除 FSM 状态**：移除 `GIFT_MENU`、`INVITE_MENU`、`NOTEBOOK` 三个状态及相关转换规则
- **清理存档字段**：从 `SaveSlot` 中移除 `notebook_data` 和 `interaction_data` 字段
- **更新文档**：同步更新 README 和 CHANGELOG，移除所有已删除功能的描述

## 1.2.0 (2026-07-20)

### 新增功能

- **自由聊天模式（LLM 驱动）**：新增 `/dsv chat <角色名>` 命令，与角色进行 LLM 驱动的实时对话
  - 角色 prompt 从 `data/characters/` JSON 自动加载，构建为 LLM system prompt
  - 对话历史维护最近 20 条消息，支持上下文连续对话
  - 支持通过 `config.toml [chat].default_model` 配置使用的 LLM 模型（默认 `"replyer"`）
  - 模型选择仅通过配置控制，禁止用户在命令中指定
  - FSM 新增 `CHAT` 状态，EXPLORATION ↔ CHAT 双向转换
  - 配套 `/dsv chat_exit` 退出聊天模式，回到 EXPLORATION 状态
  - 好感度联动：LLM prompt 中注入当前好感度等级，影响角色回复风格
- **Planner 阻止机制**：三层防御防止自由聊天消息进入 MaiBot Planner 处理链
  - 新增 `chat.receive.before_process` 拦截 CHAT 状态非命令消息 → 返回 `{"action": "abort"}`
  - 新增 `chat.command.after_execute` 拦截所有 `/dsv` 命令 → 设置 `intercept_message_level = 1`
  - 异步非阻塞：LLM 调用通过 `asyncio.ensure_future` 异步执行，不阻塞主流程
- **分段式剧情对话**：新增 `/dsv plot <角色名>` 命令，加载预编剧情脚本进行交互式对话
  - JSON 节点图结构，支持选项分支与好感度联动，好/中/坏三种结局
  - FSM 新增 `SAID_SCRIPT` / `AWAITING_CHOICE` 状态，通过 `/dsv choose` 和 `/dsv next` 交互
  - 配套 `/dsv plot_exit` 退出剧情模式
  - 支持多章节子目录结构：每位角色拥有独立的剧情文件夹（如 `data/plot/luoshulv/`）
  - 系统自动扫描、验证并加载 `data/plot/<角色名>/` 下所有章节 JSON
- **命令重命名**：`/dsv said` → `/dsv plot`，`/dsv say` → `/dsv chat`，同步更新所有内部引用
- **配置热更新增强**：`reload()` 新增 plot 脚本重载和 chat 会话自动清理
- **配置 UI 标签增强**：所有配置字段添加 `json_schema_extra={"label": ...}`，支持后台管理面板友好渲染

### Bug 修复

- **修复节点引用错误**：修正剧情对话脚本中的节点跳转引用，确保 `/dsv plot` 和 `/dsv said` 模式下选项分支正确推进

### 重构

- **ForwardService 替代 ForwardMessageCollector**：
  - 移除 NapCat API 直接调用（`_call_napcat_api`、`send_direct`、`_http_post`、`_parse_stream_id`）
  - 改用 Host `send.forward` 能力，每条消息包装为单个转发节点即时发送
  - 转发不可用时自动降级为直接文本发送
  - 配置项精简：移除 `auto_flush`、`display_title`、`napcat_url`、`request_timeout`
- **对话展示移至 Renderer**：`send_dialogue_display()` 从 `plugin.py` 迁至 `renderer.py`，统一对话展示逻辑
- **数据路径统一**：配置路径从 `plugins/visual_novel/data` 全部更新为 `plugins/daosu_galgame/data`
- **`said.py` → `plot.py`**：模块重命名，新增多章节进度追踪和子目录扫描能力

### 变更

- `data/said/` 目录重命名为 `data/plot/`，每位角色拥有独立子目录（`data/plot/luoshulv/`、`data/plot/xaviel/`）
- 移除 `[game]` 配置段（含 `default_gifts`）
- `[forward]` 配置段精简：移除 NapCat 相关字段
- `config.py`：移除 `GameConfig` 类，所有配置段字段添加 `json_schema_extra`

### 技术改进

- 新增 `modules/say_chat.py` 自由聊天引擎模块（`SayChatManager`）
- 新增 `core/json_utils.py` 共享 JSON 注释清洗工具函数
- 重构 `_strip_json_comments` 为统一工具，消除 `character.py` / `plot.py` 中的代码重复
- 所有 data JSON 文件添加完整字段注释（角色数据、事件脚本、剧情脚本）
- 配置文件新增 `[chat]` 配置段（`default_model` 字段）
- `_manifest.json` 声明 `llm.generate` 能力
- FSM 扩展至 12 种状态：新增 `SAID_SCRIPT`、`CHAT` 状态及合法转换规则

### 可攻略角色（新增剧情）

- **洛疏律** — 5 章分段式剧情（`data/plot/luoshulv/`），每章好/中/坏三结局
- **查维尔** — 5 章分段式剧情（`data/plot/xaviel/`），每章好/中/坏三结局

### 命令列表

| 命令 | 功能 |
|------|------|
| `/dsv plot <角色名>` | 分段式剧情对话 |
| `/dsv plot_exit` | 退出剧情模式 |
| `/dsv chat <角色名>` | 自由聊天（LLM 驱动） |
| `/dsv chat_exit` | 退出自由聊天 |
| `/dsv choose <编号>` | 在对话框分支中选择选项 |
| `/dsv next` | 推进当前对话到下一节点 |

## 1.0.1 (2026-07-19)

「悼溯茶馆」视觉小说插件首个正式版本。在此版本中，所有历史迭代内容已完成统一整合。

### 新增功能

- **新手引导系统**：首次进入游戏时自动触发交互式教程，引导玩家了解世界观、角色与玩法
  - FSM 新增 `TUTORIAL` 状态
  - 新增 `/dsv tutorial` 重新查看引导、`/dsv skip tutorial` 跳过引导命令
  - 可配置开关（`config.toml` 中 `[tutorial].enabled`）
- **对话交互命令**：新增 `/dsv next` 推进对话、`/dsv choose <编号>` 选择分支选项
- **合并转发消息**：支持通过 NapCat 将多段对话内容合并为一条 QQ 转发消息发送
  - 新增 `ForwardMessageCollector` 模块（`modules/forward.py`）
  - 按 `stream_id` 隔离会话缓冲，支持自动/手动发送
  - 发送失败时自动降级，不影响主流程
- **配置模块化**：全部配置模型提取至独立 `config.py`，支持后台 UI 配置渲染
- **可配置参数扩展**：
  - `[tutorial]` — 引导开关与脚本 ID
  - `[affection]` — 初始好感度、上下限阈值
  - `[save]` — 存档槽位数量
  - `[forward]` — 合并转发开关与 NapCat 地址
- **角色系统**：基于 JSON 的角色 prompt 加载与管理，支持动态性格标签
- **对话系统**：节点式剧情脚本引擎，支持分支选项、好感度变动、倾诉烦恼检测
- **好感度系统**：7 级好感度体系（冷漠→爱慕），基于角色性格的智能计算规则
- **记事本与线索系统**：日常对话中自动检测并记录角色喜好线索
- **互动行为系统**：礼物赠送与邀约活动，支持与线索系统联动
- **存档系统**：20 槽位存档/读档，JSON 持久化与原子写入保护
- **有限状态机**：10 种游戏状态，预定义合法转换规则，确保流程合法性

### 可攻略角色

- **洛疏律** — 茶馆常居者，温和内向，喜欢雨天品茶写笔记
- **查维尔** — 神秘养鱼人，内敛随性，视后院鱼池为珍宝

### 对话脚本

- **「茶馆雨遇」** — 与洛疏律在雨天的初次邂逅
- **「鱼池边的茶客」** — 与查维尔的茶馆相遇

### 命令列表

| 命令 | 功能 |
|------|------|
| `/dsv start` | 启动游戏 |
| `/dsv explore <角色名>` | 与角色对话 |
| `/dsv gift <角色名> <礼物名>` | 赠送礼物 |
| `/dsv invite <角色名> <活动名>` | 邀请活动 |
| `/dsv notebook [角色名]` | 查看记事本 |
| `/dsv status` | 游戏状态 |
| `/dsv save <槽位> [标签]` | 存档 |
| `/dsv load <槽位>` | 读档 |
| `/dsv help` | 帮助 |

LLM 工具：`dsv_character_info`、`dsv_game_status`、`dsv_gift_hints`、`dsv_list_characters`

### 技术细节

- **分层架构**：`plugin.py` → `renderer.py` → `modules/*.py`，职责清晰
- **模块间解耦**：有限状态机确保游戏流程合法性，各模块通过标准化接口协作
- **配置热重载**：支持运行时通过 `on_config_update` 热重载角色数据和对话脚本
- **JSON 注释**：角色数据和对话脚本均支持 `//` 和 `/* */` 注释
- **原子写入**：存档采用先写临时文件再重命名策略，防止存档损坏
- **完整注释**：全部 Python 源文件含详细文档字符串与类型注解

## 1.0.0 (2026-07-19)

- 正式定名为「悼溯茶馆」视觉小说插件
- 重写 README，完整呈现悼溯茶馆背景设定与角色介绍
- 更新 _manifest.json 元信息（名称、描述）
- 角色数据全面本地化：洛疏律（茶馆居留者）、查维尔（神秘养鱼人）
- 新增茶馆主题对话脚本：茶馆雨遇、鱼池边的茶客
- 废弃测试机制，移除 tests/ 目录
