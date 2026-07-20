# 变更日志

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
