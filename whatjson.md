# JSON 文件结构说明

本插件使用 JSON 文件存储角色数据、剧情对话和插件元信息。以下是各个 JSON 文件的详细说明。

---

## 1. 插件元信息 — `_manifest.json`

位于插件根目录，是 MaiBot 插件系统要求的元信息文件。定义了插件的身份、版本、依赖和能力。

| 字段 | 类型 | 说明 |
|------|------|------|
| `manifest_version` | int | 固定为 `2` |
| `version` | string | 三段式语义版本号，如 `"1.1.0"` |
| `id` | string | 反向域名格式的插件唯一标识，如 `"com.daosu.visual-novel"` |
| `name` | string | 插件显示名称 |
| `description` | string | 插件功能描述 |
| `author` | object | 作者信息，含 `name` 和 `url` |
| `license` | string | 开源许可证 |
| `urls` | object | 仓库、主页、文档、Issue 等链接 |
| `changelog` | string | 更新日志文件名 |
| `host_application` | object | 宿主应用版本约束，含 `min_version` / `max_version` |
| `sdk` | object | SDK 版本约束，含 `min_version` / `max_version` |
| `dependencies` | array | Python 包或插件间依赖 |
| `capabilities` | array | 声明的能力列表，如 `["send.text", "send.forward", "config.get"]` |
| `i18n` | object | 国际化配置，含 `default_locale` 和 `supported_locales` |

---

## 2. 角色数据 — `data/characters/*.json`

每个角色一个文件，存储角色的完整设定信息，供 LLM 角色扮演和好感度系统使用。

**文件：** `luoshulv.json`、`xaviel.json`

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 角色全名 |
| `nickname` | string | 角色昵称或常用称呼 |
| `gender` | string | 性别 |
| `age` | int | 年龄 |
| `personality` | array(string) | 性格特征标签列表，如 `["温和", "内向"]` |
| `background` | string | 角色背景故事文本 |
| `dialogue_style` | string | 对话风格描述，供 LLM 角色扮演参考 |
| `likes` | array(string) | 喜欢的事物列表 |
| `dislikes` | array(string) | 厌恶的事物列表 |
| `hobbies` | array(string) | 兴趣爱好列表 |
| `affection_thresholds` | object(string→int) | 好感度阈值事件映射表。key 为事件 ID，value 为触发所需最小好感度。如 `{"event_share_tea": 30}` 表示好感度≥30时触发分享茶的事件 |
| `emotional_triggers` | object | 情绪触发规则。含 `venting_triggers`（触发词列表）和 `venting_emotion`（触发时的情绪标签） |

### 示例

```json
{
  "name": "洛疏律",
  "nickname": "小律",
  "gender": "男",
  "age": 25,
  "personality": ["温和", "内向", "情绪稳定", "温柔", "细腻"],
  "likes": ["蜂蜜柚子茶", "茉莉柚茶", "雨天", "写笔记", "安静"],
  "dislikes": ["别人擅动他的物品", "被人乱翻书", "喧闹", "恶作剧"],
  "hobbies": ["品茶", "写随笔", "听雨", "阅读"],
  "affection_thresholds": {
    "event_share_tea": 30,
    "event_read_notebook": 60,
    "event_confession": 80
  }
}
```

---

## 3. 事件对话脚本 — `data/events/*.json`

定义游戏中可触发的固定剧情对话（如初次相遇、特殊事件），采用节点图结构，支持线性推进和选项分支。

**文件：** `tutorial_intro.json`（新手引导）、`flower_shop_encounter.json`（茶馆雨遇-洛疏律）、`teahouse_fish_encounter.json`（鱼池边的茶客-查维尔）

### 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `script_id` | string | 脚本唯一标识，用于代码中引用 |
| `title` | string | 脚本标题，用于展示 |
| `start_node` | string | 脚本的起始节点 ID |
| `characters` | array(string) | 该脚本中登场的角色名称列表 |
| `nodes` | object | 节点字典，key 为节点 ID，value 为节点对象 |
| `metadata` | object | 额外元数据（如作者、版本） |

### 节点结构 (`nodes` 下的每个条目)

| 字段 | 类型 | 说明 |
|------|------|------|
| `speaker` | string | 说话者名称，`"narrator"` 表示旁白 |
| `text` | string | 对话文本，支持 `\n` 换行 |
| `emotion` | string | 说话时的情绪标签：`neutral`（平静）、`happy`（开心）、`sad`（难过）、`anxious`（焦虑）、`warm`（温馨）、`touched`（感动）等 |
| `choices` | array(object) | 可选分支列表（为空表示无分支，由 `next_node` 自动推进） |
| `next_node` | string 或 null | 无分支时的自动跳转目标 ID，`null` 表示对话结束 |

### 选项结构 (`choices` 下的每个条目)

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string | 选项显示文本 |
| `next_node` | string | 选择后跳转的目标节点 ID |
| `option_id` | string | 好感度规则选项 ID，用于匹配 `AffectionRule`（与 `affection.py` 联动） |
| `affection_change` | int | 直接好感度变动量。正数增加，负数减少，0 表示无影响 |

### 示例

```json
{
  "script_id": "teahouse_encounter",
  "title": "茶馆雨遇",
  "start_node": "start",
  "characters": ["洛疏律"],
  "nodes": {
    "start": {
      "speaker": "narrator",
      "text": "窗外下起了绵绵细雨……",
      "emotion": "neutral",
      "next_node": "greeting"
    },
    "greeting": {
      "speaker": "洛疏律",
      "text": "欢迎。茶单在桌上，自己看就好。",
      "emotion": "neutral",
      "choices": [
        {
          "text": "你在写什么？",
          "next_node": "ask_notebook",
          "option_id": "curious",
          "affection_change": 2
        },
        {
          "text": "来一壶蜂蜜柚子茶。",
          "next_node": "order_tea",
          "option_id": "same_taste",
          "affection_change": 3
        }
      ]
    }
  }
}
```

---

## 4. 分段式剧情对话 — `data/said/*.json`

供 `/dsv said <角色名>` 命令使用的交互式分段剧情，结构与事件脚本类似，但独立管理，专用于角色专属的剧情线。

**文件：** `luoshulv_said.json`、`xaviel_said.json`

### 顶层字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `script_id` | string | 脚本唯一标识 |
| `character_name` | string | 关联的角色名称，用于 `/dsv said <角色名>` 匹配 |
| `title` | string | 剧情标题 |
| `start_node` | string | 起始节点 ID |
| `nodes` | object | 节点字典，key 为节点 ID，value 为节点对象 |

### 节点结构

与事件脚本的节点结构相同，但选项中没有 `option_id` 字段（好感度变化直接通过 `affection_change` 控制）。

终端节点（无 `choices` 且 `next_node` 为 `null`）有特殊命名约定：
- `node_end_good` — 好结局，好感度正向变化后到达
- `node_end_neutral` — 普通结局
- `node_end_bad` — 坏结局，好感度负向变化后到达

### 选项结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | string | 选项文本 |
| `next_node` | string | 跳转目标节点 ID |
| `affection_change` | int | 好感度变化量。正数增加（建议 +3~+8），负数减少（建议 -3~-8），0 表示无变化 |

### 示例

```json
{
  "script_id": "said_luoshulv",
  "character_name": "洛疏律",
  "title": "与洛疏律的茶馆午后",
  "start_node": "node_01",
  "nodes": {
    "node_01": {
      "text": "（你推开茶馆的木门……）",
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
        },
        {
          "text": "「你笔记本里写了什么？让我看看。」",
          "next_node": "node_04",
          "affection_change": -8
        }
      ]
    }
  }
}
```

---

## 文件总览

| 文件路径 | 类型 | 用途 |
|----------|------|------|
| `_manifest.json` | 元信息 | 插件注册与版本声明 |
| `data/characters/luoshulv.json` | 角色数据 | 洛疏律的角色设定 |
| `data/characters/xaviel.json` | 角色数据 | 查维尔的角色设定 |
| `data/events/tutorial_intro.json` | 事件脚本 | 新手引导 |
| `data/events/flower_shop_encounter.json` | 事件脚本 | 洛疏律的茶馆雨遇事件 |
| `data/events/teahouse_fish_encounter.json` | 事件脚本 | 查维尔的鱼池事件 |
| `data/said/luoshulv_said.json` | 分段剧情 | 洛疏律的交互式剧情线（13 节点） |
| `data/said/xaviel_said.json` | 分段剧情 | 查维尔的交互式剧情线（12 节点） |

---

## 好感度变化参考

| 情境 | 建议变化值 |
|------|-----------|
| 选择符合角色性格、投其所好的选项 | **+5 ~ +8** |
| 选择中性的、无伤大雅的选项 | **+0 ~ +3** |
| 选择稍有不妥、但可挽回的选项 | **-3 ~ -5** |
| 选择明显冒犯、违背角色喜好的选项 | **-6 ~ -8** |
