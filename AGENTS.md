# AGENTS.md — MaiBot 插件项目

> 你正在为 MaiBot 编写第三方插件。请使用 maibot-plugin-sdk，入口文件为 `plugin.py`，元信息文件为 `_manifest.json`。必须实现 `on_load`、`on_unload`、`on_config_update` 和 `create_plugin`。优先使用 `@Tool`、`@Command`、`@HookHandler`、`@EventHandler`、`@API`、`@MessageGateway`；不要给新插件使用 `@Action`。所有用户可见文本优先使用简体中文。请保持改动边界清晰，并给出测试方式。

## 项目定位

本项目是 MaiBot 第三方插件。所有开发限定在 `plugins/<plugin-name>/` 内，**严禁修改** `src/`、`dashboard/`、`config/` 等主程序目录及根目录 `.gitignore`。

## 文件结构

```
plugins/<plugin-name>/
├── _manifest.json    # 元信息（manifest_version 固定为 2）
├── plugin.py         # 入口，须实现 create_plugin() 工厂函数
├── config.toml       # 运行配置
├── README.md
└── .gitignore        # 插件独有忽略规则
```

## 编码规范

### 导入

- 仅从标准库、第三方库和 `maibot_sdk` 导入，顺序为：标准库 → 第三方库 → `maibot_sdk`。

### 类结构

- 插件类继承 `MaiBotPlugin`，声明 `config_model`。
- 必须实现四个方法：`on_load()`、`on_unload()`、`on_config_update()`、`create_plugin()`。

### 配置

- 配置模型继承 `PluginConfigBase`，字段用 `Field(default=..., description="...")`。
- 保留 `[plugin]` 分组，含 `enabled` 和 `config_version`。
- 读取配置优先用 `self.config.<section>.<field>`，热重载逻辑放 `on_config_update()`。

### 通用约束

- 所有用户可见文本使用**简体中文**。
- 禁止硬编码 token、密钥、绝对路径、QQ 号、群号及私有 URL。
- 网络请求必须设超时并捕获异常。
- 定时任务、后台连接、文件句柄必须在 `on_unload()` 中清理。
- 不提交日志、临时文件、数据库、`.venv/`、`__pycache__/` 到仓库。

## 组件选用

| 场景 | 组件 | 文档 |
|------|------|------|
| LLM 主动调用 | `@Tool` | [docs](https://docs.mai-mai.org/plugin/tools) |
| 用户命令触发 | `@Command` | [docs](https://docs.mai-mai.org/plugin/commands) |
| 拦截/观察流程 | `@HookHandler` | [docs](https://docs.mai-mai.org/plugin/hooks) |
| 监听事件 | `@EventHandler` | [docs](https://docs.mai-mai.org/plugin/event-handlers) |
| 供其他插件调用 | `@API` | [docs](https://docs.mai-mai.org/plugin/api-components) |
| 接入聊天平台 | `@MessageGateway` | [docs](https://docs.mai-mai.org/plugin/message-gateway) |
| 自定义 LLM 后端 | `LLMProvider` | [docs](https://docs.mai-mai.org/plugin/llmprovider) |
| ~~兼容旧代码~~ | ~~`@Action`~~ | **新插件禁止使用** |

### Tool 规范

- `description`：写明使用时机、参数含义、限制与副作用。
- 参数用 `ToolParameterInfo` + `ToolParamType` 声明。
- 返回值用 `dict`，LLM 可读文本放 `content`；媒体用 `content_items`，不内嵌 base64。
- 内部异常必须捕获并返回可读错误，不得泄漏。
- 默认不入核心池；仅高频低风险工具设 `core_tool=True`。

### 消息发送

- 文本：`await self.ctx.send.text(content, stream_id)`
- 图片 / 表情 / 转发 / 混合消息：通过 `self.ctx.send` 和 `self.ctx.emoji` 代理。
- 始终使用上下文传入的 `stream_id`，不自行计算会话 ID。

## Manifest 校验

| 字段 | 约束 |
|------|------|
| `manifest_version` | 固定 `2` |
| `id` | 反向域名格式，如 `com.example.my-plugin` |
| `version` | 三段式语义版本，如 `1.0.0` |
| URL 字段 | 必须以 `http://` 或 `https://` 开头 |
| `host_application` / `sdk` | 均需 `min_version` 和 `max_version` |
| `dependencies` | Python 包用 `python_package`，插件间用 `plugin` |
| `capabilities` | 仅声明实际需要的 |
| `i18n.default_locale` | 推荐 `zh-CN` |

## 操作模板

### 新建插件

> 在 `plugins/<plugin-name>/` 创建插件，实现 `<功能>`。
> 要求：不改主程序；使用 `plugin.py` / `_manifest.json` 结构；实现四个生命周期方法；配置用 `PluginConfigBase` + `Field`；用户文本用简体中文；附带 `README`、`config.toml`、`.gitignore`；说明启用与测试方式。

### 修改插件

> 仅修改 `plugins/<plugin-name>/` 内文件，为现有插件增加 `<功能>`。
> 先阅读 `_manifest.json`、`plugin.py`、`config.toml`、`README`，沿用现有风格。不重构无关代码。如需主程序改动，先说明原因并征得许可。

### 排查问题

> 排查 `plugins/<plugin-name>/` 问题，按优先级检查：Manifest 校验 → 依赖声明 → 生命周期方法 → `create_plugin` → 配置模型 → 异常日志。只做最小修复，不重构。

## 外部参考

- **NapCat API**：`https://napneko.github.io/api/4.18.9`（QQ 机器人 HTTP API）

## 自检清单

- [ ] `_manifest.json` 字段完整，版本号与 URL 合法
- [ ] `plugin.py` 仅从合法来源导入
- [ ] 类继承 `MaiBotPlugin`，声明 `config_model`
- [ ] 实现 `on_load` / `on_unload` / `on_config_update` / `create_plugin`
- [ ] 新功能使用 `@Tool` / `@Command` 等，未使用 `@Action`
- [ ] 未修改主程序及根目录 `.gitignore`
- [ ] 无硬编码敏感信息
- [ ] 网络请求有超时和异常处理
- [ ] 资源在卸载时可清理
- [ ] 用户可见文本为简体中文
- [ ] `README` 含安装、配置、命令及常见问题
