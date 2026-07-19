"""自定义异常定义。

为视觉小说插件建立统一的异常类型体系，按错误类别分层：
- VisualNovelError：所有插件异常的基类
- CharacterNotFoundError：角色数据访问相关
- InvalidStateTransitionError：状态机流程控制相关
- SaveDataError：存档读写与数据完整性相关
- ConfigurationError：插件配置相关
- DialogueScriptError：对话脚本解析相关

所有业务层模块应抛出这些自定义异常，而非原始 Python 异常，
以便调用层统一捕获与处理。
"""


class VisualNovelError(Exception):
    """视觉小说插件基础异常。

    所有插件自定义异常的基类。捕获此异常即可捕获所有插件层错误。
    """


class CharacterNotFoundError(VisualNovelError):
    """指定角色不存在。

    在通过角色名称查询数据但未找到时抛出。
    """


class InvalidStateTransitionError(VisualNovelError):
    """非法状态转换。

    当状态机尝试从不允许的状态转换到目标状态时抛出。
    例如在 IDLE 状态下尝试直接进入 DIALOGUE 状态。
    """


class SaveDataError(VisualNovelError):
    """存档数据异常。

    存档文件不存在、格式损坏、写入失败时抛出。
    """


class ConfigurationError(VisualNovelError):
    """配置错误。

    插件配置项缺失、类型不匹配或值不合法时抛出。
    """


class DialogueScriptError(VisualNovelError):
    """对话脚本解析错误。

    加载 JSON 对话脚本时，字段缺失或格式不符合预期时抛出。
    """
