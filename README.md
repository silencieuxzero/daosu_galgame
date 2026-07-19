# 视觉小说插件 (Visual Novel Plugin)

模块化的文字类视觉小说插件，适用于 MaiBot 平台。

## 架构设计

```
plugins/visual_novel/
├── core/                  # 核心基础设施
│   ├── __init__.py
│   ├── fsm.py             # 有限状态机
│   └── exceptions.py      # 自定义异常
├── modules/               # 功能模块
│   ├── __init__.py
│   ├── character.py       # 角色系统
│   ├── dialogue.py        # 对话系统
│   ├── affection.py       # 好感度系统
│   ├── notebook.py        # 记事本与线索系统
│   ├── interaction.py     # 互动行为系统
│   └── save_manager.py    # 存档管理
├── data/                  # 数据文件
│   ├── characters/        # 角色 prompt JSON
│   └── events/            # 对话脚本 JSON
├── tests/                 # 单元测试
├── renderer.py            # 模块加载器与协调器
├── plugin.py              # 插件入口（精简协调层）
├── _manifest.json         # 元信息
├── config.toml            # 配置
├── .gitignore
└── README.md
```

### 分层职责

| 层 | 组件 | 职责 |
|---|------|------|
| **入口** | `plugin.py` | 注册 Command/Tool，委托给 Renderer |
| **协调** | `renderer.py` | 加载模块，管理 FSM，统一反馈 |
| **核心** | `core/fsm.py` | 有限状态机，定义状态转换规则 |
| **模块** | `modules/*.py` | 各功能领域的业务逻辑 |

### 数据流

```
用户输入 → plugin.py (Command/Tool)
         → renderer.py (状态机检查 + 模块调度)
         → modules/*.py (业务逻辑执行)
         → renderer.py (反馈整合)
         → plugin.py (消息发送)
```

## 安装与配置

### 1. 放置插件

将 `plugins/visual_novel/` 目录复制到 MaiBot 项目的 `plugins/` 目录下。

### 2. 编辑配置

`plugins/visual_novel/config.toml`:

```toml
[plugin]
enabled = true          # 启用插件
config_version = "1.0.0"

[game]
default_gifts = ["花束", "手工饼干", "音乐盒", "巧克力"]

[data]
data_dir = "plugins/visual_novel/data"       # 角色数据路径
save_dir = "plugins/visual_novel/data/saves" # 存档路径
```

### 3. 重启 Bot

重启 MaiBot 使其加载插件。

## 使用命令

| 命令 | 说明 |
|------|------|
| `/novel_start` | 启动视觉小说 |
| `/novel_explore <角色名>` | 与角色开始日常对话 |
| `/novel_gift <角色名> <礼物名>` | 赠送礼物 |
| `/novel_invite <角色名> <活动名>` | 邀请角色参加活动 |
| `/novel_notebook [角色名]` | 查看记事本 |
| `/novel_status` | 查看游戏状态 |
| `/novel_save <槽位1-20> [标签]` | 存档 |
| `/novel_load <槽位1-20>` | 读档 |
| `/novel_help` | 显示帮助 |

## 角色数据格式

`data/characters/` 目录下每个 JSON 文件定义一个角色：

```json
{
  "name": "玲",
  "nickname": "小玲",
  "gender": "女",
  "age": 18,
  "personality": ["温柔", "细心", "内向"],
  "background": "经营一家花店的女孩...",
  "dialogue_style": "语速较慢，语气温柔",
  "likes": ["鲜花", "书籍", "甜点"],
  "dislikes": ["噪音", "拥挤"],
  "hobbies": ["园艺", "烘焙"],
  "affection_thresholds": {
    "event_friendship": 30,
    "event_love": 60
  },
  "emotional_triggers": {
    "venting_triggers": ["孤独", "辛苦"],
    "venting_emotion": "sad"
  }
}
```

## 对话脚本格式

`data/events/` 目录下每个 JSON 文件定义一个对话脚本。支持分支选项、好感度变动、倾诉烦恼检测。

```json
{
  "script_id": "flower_shop_encounter",
  "title": "花店相遇",
  "start_node": "start",
  "characters": ["玲"],
  "nodes": {
    "start": {
      "speaker": "narrator",
      "text": "你走进了一家花店...",
      "emotion": "neutral",
      "next_node": "greeting"
    },
    "greeting": {
      "speaker": "玲",
      "text": "欢迎光临！",
      "choices": [
        {
          "text": "随便看看",
          "next_node": "look_around",
          "option_id": "casual",
          "affection_change": 0
        }
      ]
    }
  }
}
```

## 好感度系统

好感度范围：-100 ~ 100

| 等级 | 区间 |
|------|------|
| 冷漠 | -100 ~ -51 |
| 陌生 | -50 ~ -1 |
| 普通 | 0 ~ 30 |
| 友好 | 31 ~ 60 |
| 亲近 | 61 ~ 80 |
| 亲密 | 81 ~ 95 |
| 爱慕 | 96 ~ 100 |

好感度变动规则基于角色性格自动计算。注册规则时可为每个选项设置 `personality_tags`、`reverse_for_tags` 和 `special_multiplier`，实现智能的好感度动态调整。

## 情绪倾诉系统

当对话检测到角色处于倾诉烦恼状态（emotion 为 sad/anxious/frustrated/venting）时，自动在选项中增加"静静听着"选项。选择该选项会触发特定的好感度调整（默认 +5）。

## 记事本与线索系统

- 日常对话中自动检测喜好线索并记录
- 线索分类：喜爱之物、厌恶之物、兴趣爱好、性格特点、过往经历
- 礼物赠送时自动提示是否符合已知线索

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
renderer.affection.register_rules_from_config("玲", rules)
```

## 开发说明

### 运行测试

```bash
cd <project-root>
python -m pytest plugins/visual_novel/tests/ -v
```

### 模块扩展

新增功能模块的步骤：
1. 在 `modules/` 下创建模块文件
2. 在 `renderer.py` 中实例化并注册
3. 在 `plugin.py` 中添加对应的 Command/Tool

## 常见问题

**Q: 插件加载后没有响应？**
A: 检查 `config.toml` 中 `[plugin].enabled = true`。

**Q: 角色数据修改后不生效？**
A: 插件支持热重载，修改数据文件后调用 `on_config_update` 即可。

**Q: 如何查看当前所有角色的好感度？**
A: 使用 `/novel_status` 命令。

## 许可

GPL-v3.0-or-later
