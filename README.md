# 悼溯茶馆 — 视觉小说插件

基于 MaiBot 平台的文字类视觉小说插件，背景设定于 **悼溯茶馆**。
玩家可在茶馆中邂逅形形色色的角色，通过日常对话和剧情选择培养好感度，逐步解锁角色的过往故事。

## 目录

- [故事背景](#故事背景)
- [角色介绍](#角色介绍)
- [安装与配置](#安装与配置)
- [使用命令](#使用命令)
- [系统机制](#系统机制)
  - [新手引导系统](#新手引导系统)
  - [好感度系统](#好感度系统)
  - [分段式剧情对话](#分段式剧情对话系统)
  - [自由聊天模式](#自由聊天模式)
  - [Planner 阻止机制](#planner-阻止机制)
  - [情绪倾诉系统](#情绪倾诉系统)
  - [存档系统](#存档系统)
  - [合并转发消息](#合并转发消息)
- [架构设计](#架构设计)
- [数据格式](#数据格式)
  - [角色数据格式](#角色数据格式)
  - [对话脚本格式](#对话脚本格式)
- [配置文件](#配置文件)
- [自定义配置](#自定义配置)
- [开发说明](#开发说明)
- [常见问题](#常见问题)
- [许可](#许可)

## 故事背景

> 悼溯茶馆坐落于一座无名小镇的街角，灰墙黛瓦，檐下挂着一盏旧风灯。
> 推开木门，茶香扑面而来，窗外的雨声和沸水的咕噜声交织成一片安宁。
>
> 这里收留无处可去的人，也藏匿不能言说的秘密。
> 每个人都有一段不愿提起的过往——而你，将在这座茶馆中，慢慢走近他们的故事。

## 角色介绍

### 洛疏律

悼溯茶馆的常居者。因某些原因在茶馆长期居留，偶尔帮忙打理。喜欢雨天时点一杯蜂蜜柚子茶，坐在窗前听雨声写笔记。性格温和内向，不擅长开玩笑，总是会把别人的玩笑话当真。很讨厌别人擅动他的物品，尤其是书本。

- **性格标签**：温和、内向、情绪稳定、温柔、细腻
- **喜好**：蜂蜜柚子茶、茉莉柚茶、雨天、写笔记、安静
- **厌恶**：别人擅动他的物品、喧闹、恶作剧
- **好感度事件**：共饮一壶茶（30）→ 分享笔记（60）→ 告白（80）

> 初次邂逅：**「茶馆雨遇」** — 点击 `/dsv start` 进入游戏，在雨天推开茶馆的木门，遇见那个低头写着什么的人。

### 查维尔

悼溯茶馆的神秘常客，自称「卖渔翁」或「养鱼的」。疑似无处可去于是常住茶馆内。在后院小水池里养了几条蓝鳞丝绸鱼，视若珍宝。喜欢坐在靠窗的位置，杯里永远泡着茉莉花茶或龙井，配一碟绿豆糕。似乎活了很久很久，久到连自己都遗忘了年龄。

- **性格标签**：神秘、内敛、随性、细腻、温柔
- **喜好**：茉莉花茶、龙井、绿豆糕、养鱼、雨天、靠窗的座位
- **厌恶**：被人开玩笑、被人过问过往、喧闹、水池被弄脏
- **好感度事件**：带你看鱼（30）→ 请你喝茶（60）→ 敞开心扉（80）

> 初次邂逅：**「鱼池边的茶客」** — 午后的阳光透过窗棂，靠窗的位置坐着一个看上去有些特别的人。

## 安装与配置

### 1. 放置插件

将 `plugins/daosu_galgame/` 目录复制到 MaiBot 项目的 `plugins/` 目录下。

### 2. 编辑配置

编辑 `plugins/daosu_galgame/config.toml`：

```toml
[plugin]
enabled = true
config_version = "1.1.0"

[data]
data_dir = "plugins/daosu_galgame/data"       # 角色数据路径
save_dir = "plugins/daosu_galgame/data/saves" # 存档路径

[tutorial]
enabled = true                                # 首次进入时自动引导
script_id = "tutorial_intro"

[affection]
initial_value = 0                             # 新角色初始好感度
max_value = 100
min_value = -100

[save]
max_slots = 20                                # 存档槽位数量

[forward]
enabled = false                               # 合并转发开关
bot_name = "悼溯茶馆"

[chat]
default_model = "replyer"                     # 自由聊天默认 LLM 模型
```

### 3. 重启 Bot

重启 MaiBot 使其加载插件。

## 使用命令

| 命令 | 说明 |
|------|------|
| `/dsv start` | 启动视觉小说（首次自动进入引导） |
| `/dsv tutorial` | 重新进入新手引导 |
| `/dsv next` | 推进当前对话到下一节点 |
| `/dsv plot <角色名>` | 与角色进行分段式剧情对话 |
| `/dsv plot_exit` | 退出剧情对话模式 |
| `/dsv chat <角色名>` | 与角色进行自由聊天（LLM 驱动） |
| `/dsv chat_exit` | 退出自由聊天模式 |
| `/dsv status` | 查看游戏状态（FSM 状态、各角色好感度） |
| `/dsv save <槽位1-20> [标签]` | 保存游戏进度到指定槽位 |
| `/dsv load <槽位1-20>` | 读取指定槽位的存档 |
| `/dsv skip tutorial` | 跳过引导进入主菜单 |
| `/dsv help` | 显示帮助信息 |

此外，插件提供 `@Tool` 供 LLM 调用：
- **dsv_character_info** — 获取角色详细信息（性格、背景、好感度等）
- **dsv_game_status** — 获取游戏运行状态总览
- **dsv_list_characters** — 列出所有可攻略角色及其好感度

## 系统机制

### 新手引导系统

首次进入游戏时自动触发交互式新手引导：

1. 检测玩家是否首次游玩（基于存档槽位全空判断）
2. 自动进入 `TUTORIAL` FSM 状态，播放引导对话脚本
3. 引导内容：世界观介绍 → 角色介绍（可循环浏览）→ 玩法指南 → 开始游戏
4. 引导结束后自动进入主菜单

可通过 `config.toml` 中 `[tutorial]` 段控制开关和引导脚本 ID。
随时通过 `/dsv tutorial` 重新查看，或 `/dsv skip tutorial` 跳过。

### 好感度系统

好感度范围：-100 ~ 100，共 7 个等级。上下限和初始值可通过 `[affection]` 配置段调整。

| 等级 | 区间 |
|------|------|
| 冷漠 | -100 ~ -51 |
| 陌生 | -50 ~ -1 |
| 普通 | 0 ~ 30 |
| 友好 | 31 ~ 60 |
| 亲近 | 61 ~ 80 |
| 亲密 | 81 ~ 95 |
| 爱慕 | 96 ~ 100 |

好感度变动规则基于角色性格自动计算。支持三种智能调整机制：
- **基础变动**：选项直接指定的好感度变化
- **性格反转**：某些性格（如傲娇）会使原本正向的变动反转
- **性格倍率**：特定性格对某些行为反应更敏感，变动值乘以倍率

好感度达到特定阈值时自动触发对应角色事件。

### 分段式剧情对话系统

通过 `/dsv plot <角色名>` 命令进入，加载角色专属的预编 JSON 剧情脚本。
每段剧情由节点图构成，包含好、中、坏三种结局，用户通过选项分支推进剧情。
选项会实时影响角色好感度，FSM 切换到 `PLOT_SCRIPT` 状态。
配套 `/dsv plot_exit` 随时退出。

剧情脚本存储于 `data/plot/` 目录下，每位角色拥有独立子目录：
- `data/plot/luoshulv/` — 洛疏律（5 章）
- `data/plot/xaviel/` — 查维尔（5 章）

每章独立 JSON 文件，系统自动扫描、验证并加载。目前已为每位角色配备了 5 章专属剧情线。

### 自由聊天模式

通过 `/dsv chat <角色名>` 命令进入，与角色进行 LLM 驱动的实时自由对话。
角色 prompt 从 `data/characters/` JSON 自动加载，构建为 LLM system prompt。
对话历史维护最近 20 条消息，支持上下文连续的对话体验。

- **模型配置**：通过 `config.toml [chat].default_model` 指定，默认 `"replyer"`
- 好感度联动：LLM prompt 中注入当前好感度等级，影响角色回复风格
- FSM 切换到 `CHAT` 状态，退出后回到 `PLOT_SCRIPT`

### Planner 阻止机制

为防止自由聊天模式下的消息被 MaiBot 的 Planner/LLM 处理链再次处理，
系统部署了三层防御：

1. **消息拦截**（`chat.receive.before_process`）：CHAT 状态下非命令消息 →
   返回 `{"action": "abort"}` 彻底阻止消息进入处理链，异步调用 LLM 生成回复
2. **命令拦截**（`chat.command.after_execute`）：所有 `/dsv` 命令 →
   设置 `intercept_message_level = 1` 阻止后续 Planner 处理
3. **异步非阻塞**：LLM 调用通过 `asyncio.ensure_future` 异步执行，不阻塞主流程

### 情绪倾诉系统

当对话检测到角色处于倾诉烦恼状态（`emotion` 为 `sad` / `anxious` / `frustrated` / `venting`）时，系统自动在选项中增加 **「静静听着」** 选项。选择该选项会触发特定的好感度调整（默认 +5），并推动角色情感表达。

### 存档系统

- 支持 20 个独立存档槽位（数量可通过 `[save]` 配置段调整）
- 存档内容：好感度、选择历史、当前对话进度
- 原子写入策略（先写临时文件再重命名），防止写入中断导致存档损坏
- JSON 格式存储，可读性强

### 合并转发消息

支持通过 Host 的 `send.forward` 能力将多段对话/引导内容合并为一条转发消息发送。

- **单条转发**：每条对话/节点即时包装为单个转发节点发送，不延迟缓冲
- **降级机制**：转发不可用时自动降级为直接文本发送，不影响体验
- **配置控制**：通过 `[forward]` 配置段开关，可配置机器人显示名称

## 架构设计

```
plugins/daosu_galgame/
├── core/                  # 核心基础设施
│   ├── __init__.py
│   ├── fsm.py             # 有限状态机（9 种状态，预定义转换规则）
│   └── exceptions.py      # 自定义异常类型体系
├── modules/               # 功能模块
│   ├── __init__.py
│   ├── character.py       # 角色系统：加载与管理角色 prompt 数据
│   ├── dialogue.py        # 对话系统：节点式剧情脚本引擎
│   ├── affection.py       # 好感度系统：7 级好感度体系
│   ├── plot.py            # 分段式剧情对话引擎（/dsv plot，多章节支持）
│   ├── say_chat.py        # 自由聊天引擎（/dsv chat，LLM 驱动）
│   ├── save_manager.py    # 存档管理：可配置槽位 JSON 持久化
│   └── forward.py         # 合并转发消息服务（基于 Host send.forward）
├── data/                  # 数据文件
│   ├── characters/        # 角色 prompt JSON（支持注释）
│   ├── events/            # 对话脚本 JSON（支持注释）
│   └── plot/              # 分段式剧情对话 JSON（/dsv plot 使用）
├── config.py              # 配置模型定义（供 plugin.py 与后台 UI 使用）
├── renderer.py            # 模块加载器与协调器
├── plugin.py              # 插件入口（精简协调层）
├── _manifest.json         # 插件元信息
├── config.toml            # 运行配置
├── .gitignore
└── README.md
```

### 分层职责

| 层 | 组件 | 职责 |
|---|------|------|
| **入口** | `plugin.py` | 注册 Command/Tool，委托给 Renderer |
| **协调** | `renderer.py` | 加载模块，管理 FSM，整合模块反馈 |
| **配置** | `config.py` | 集中定义所有配置模型 |
| **核心** | `core/fsm.py`、`core/exceptions.py` | 状态机与异常类型 |
| **模块** | `modules/*.py` | 各功能领域的业务逻辑 |

### 数据流

```
用户输入 → plugin.py (Command/Tool)
         → renderer.py (状态机检查 + 模块调度)
         → modules/*.py (业务逻辑执行)
         → renderer.py (反馈整合)
         → plugin.py (消息发送 / 收集器缓冲)
         → Host send.forward (合并转发) 或 ctx.send.text (直发)
```

### 有限状态机

游戏流程由 9 种状态驱动，所有状态转换须符合预定义的合法规则：

```
IDLE → {MAIN_MENU, TUTORIAL}
MAIN_MENU → {EXPLORATION, SAVE_MENU, TUTORIAL}
TUTORIAL → {DIALOGUE, MAIN_MENU}
EXPLORATION → {DIALOGUE, EVENT, SAVE_MENU, CHAT, PLOT_SCRIPT}
DIALOGUE → {EXPLORATION, EVENT, SAVE_MENU}
EVENT → {DIALOGUE, EXPLORATION, PLOT_SCRIPT}
CHAT → {EXPLORATION, MAIN_MENU}
```

## 数据格式

### 角色数据格式

`data/characters/` 目录下每个 JSON 文件定义一个角色，支持 `//` 行注释和 `/* */` 块注释：

```json
{
  /* 角色：洛疏律 — 茶馆常居者 */
  "name": "洛疏律",            // 角色名称（唯一标识）
  "nickname": "小律",          // 日常称呼
  "gender": "男",
  "age": 25,
  "personality": ["温和", "内向", "情绪稳定", "温柔", "细腻"],
  "background": "因某些原因而在茶馆长期居留...",
  "dialogue_style": "语调平缓温和，说话慢条斯理",
  "likes": ["蜂蜜柚子茶", "雨天", "写笔记"],
  "dislikes": ["喧闹", "恶作剧"],
  "hobbies": ["品茶", "写随笔", "听雨"],
  "affection_thresholds": {
    "event_share_tea": 30,     // 好感度 >= 30 触发
    "event_read_notebook": 60,
    "event_confession": 80
  },
  "emotional_triggers": {
    "venting_triggers": ["茶馆", "下雨", "笔记本"],
    "venting_emotion": "sad"
  }
}
```

### 对话脚本格式

`data/events/` 目录下每个 JSON 文件定义一个对话脚本。采用节点图结构，支持线性推进和分支选择：

```json
{
  "script_id": "teahouse_encounter",     // 脚本唯一标识
  "title": "茶馆雨遇",                   // 脚本标题
  "start_node": "start",                 // 起始节点 ID
  "characters": ["洛疏律"],              // 登场角色
  "nodes": {
    "start": {
      "speaker": "narrator",
      "text": "窗外下起了绵绵细雨...",
      "emotion": "neutral",
      "next_node": "greeting"
    },
    "greeting": {
      "speaker": "洛疏律",
      "text": "欢迎光临。",
      "choices": [
        {
          "text": "你在写什么？",
          "next_node": "ask_notebook",
          "option_id": "curious",        // 关联好感度规则
          "affection_change": 2          // 直接好感度变动
        }
      ]
    }
  }
}
```

### 分段式剧情对话格式

`data/plot/` 目录下每个 JSON 文件定义一个分段式剧情脚本，供 `/dsv plot` 命令使用。
结构与事件脚本类似，但按角色归属，并支持三种结局（好/中/坏）：

```json
{
  "script_id": "said_luoshulv_01",          // 脚本唯一标识
  "character_name": "洛疏律",            // 关联的角色名
  "title": "与洛疏律的茶馆午后",         // 剧情标题
  "start_node": "node_01",               // 起始节点 ID
  "nodes": {
    "node_01": {
      "text": "（你推开茶馆的木门...）",
      "speaker": "洛疏律",
      "emotion": "neutral",
      "choices": [
        {
          "text": "「和往常一样，蜂蜜柚子茶。」",
          "next_node": "node_02",
          "affection_change": 3
        },
        {
          "text": "「你推荐什么？」",
          "next_node": "node_03",
          "affection_change": 5
        }
      ]
    },
    "node_end_good": {                   // 好结局节点（无 choices 且无 next_node）
      "text": "今天和你聊天很开心。",
      "speaker": "洛疏律",
      "emotion": "happy"
    }
  }
}
```

分段式剧情脚本与事件脚本结构相似，但有以下区别：
- 选项不含 `option_id` 字段（好感度直接通过 `affection_change` 控制）
- 终点节点命名约定为 `node_end_good` / `node_end_neutral` / `node_end_bad`，分别对应好/中/坏三种结局
- 顶层通过 `character_name` 字段关联角色，用于 `/dsv plot <角色名>` 匹配

## 配置文件

所有配置模型集中定义于 `config.py`，可通过后台 UI 渲染配置面板。实际运行值由 `config.toml` 提供。共分 7 个配置段：

| 配置段 | 功能 |
|--------|------|
| `[plugin]` | 插件启用开关、配置版本 |
| `[data]` | 数据目录、存档目录路径 |
| `[tutorial]` | 新手引导开关、脚本 ID |
| `[affection]` | 好感度初始值、上下限 |
| `[save]` | 存档槽位数 |
| `[forward]` | 合并转发开关、机器人名称 |
| `[chat]` | 自由聊天默认 LLM 模型 |

## 自定义配置

### 添加角色

1. 在 `data/characters/` 下创建 JSON 文件
2. 配置角色属性、好感度阈值和情绪触发规则
3. 重启或通过 `on_config_update` 热重载

### 添加对话脚本

1. 在 `data/events/` 下创建 JSON 文件
2. 按上述格式定义节点、选项和分支
3. 重启或热重载

### 自定义好感度规则

在插件代码中通过 `affection_manager.register_rules_from_config()` 批量注册：

```python
rules = [
    {
        "option_id": "praise",
        "description": "赞美",
        "base_change": 5,
        "personality_tags": ["温和"],
        "reverse_for_tags": ["傲娇"],
        "special_multiplier": {"内向": 2.0}
    }
]
renderer.affection.register_rules_from_config("洛疏律", rules)
```

## 开发说明

### 模块扩展

新增功能模块的步骤：
1. 在 `modules/` 下创建模块文件
2. 在 `renderer.py` 中实例化并注册
3. 在 `plugin.py` 中添加对应的 Command/Tool

### 编码规范

参见 [AGENTS.md](AGENTS.md) 获取完整开发规范，包括：
- 组件选用指南（`@Command` / `@Tool` / `@EventHandler` 等）
- 导入规则与类结构约定
- 配置模型与生命周期要求
- 自检清单

## 常见问题

**Q: 插件加载后没有响应？**
A: 检查 `config.toml` 中 `[plugin].enabled = true`，并确认插件目录已正确放置到 MaiBot 的 `plugins/` 下。

**Q: 角色数据/对话脚本修改后不生效？**
A: 插件支持热重载，修改数据文件后调用 `on_config_update` 即可，无需重启 Bot。

**Q: 如何查看当前所有角色的好感度？**
A: 使用 `/dsv status` 命令，或让 LLM 调用 `dsv_game_status` 工具。

**Q: 存档存在哪里？可以手动编辑吗？**
A: 存档存储在 `data/saves/` 目录下，文件名为 `save_01.json` ~ `save_20.json`。JSON 格式可读，但不建议在游戏运行时手动编辑。

**Q: 对话脚本 JSON 中可以加注释吗？**
A: 可以。脚本 JSON 和角色 JSON 均支持 `//` 行注释和 `/* */` 块注释，解析时会自动过滤。

**Q: 总是发多条消息，能不能合并到一起发？**
A: 可以。`config.toml` 中 `[forward].enabled = true` 即可启用合并转发。对话/引导流程中的多段文本会自动合成为一条转发消息发送。

**Q: `/dsv plot` 和 `/dsv chat` 有什么区别？**
A: `/dsv plot` 使用预编的 JSON 剧情脚本，提供固定剧情分支和好感度反馈，体验类似传统视觉小说。`/dsv chat` 由 LLM 实时驱动，可以自由对话没有固定剧本，模型由 `config.toml [chat].default_model` 配置。

**Q: 自由聊天模式的回复太慢了怎么办？**
A: 可以在 `config.toml` 的 `[chat]` 段中换用响应更快的 LLM 模型。默认模型为 `"replyer"`（MaiBot 内置回复任务），也可指定其他模型。

**Q: 如何修改自由聊天使用的 LLM 模型？**
A: 编辑 `config.toml`，在 `[chat]` 段中设置 `default_model = "模型名称"`。模型仅通过配置控制，用户命令中无法指定。

## 许可

GPL-v3.0-or-later
