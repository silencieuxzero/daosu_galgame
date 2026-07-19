"""自定义异常定义。"""


class VisualNovelError(Exception):
    """视觉小说插件基础异常。"""


class CharacterNotFoundError(VisualNovelError):
    """指定角色不存在。"""


class InvalidStateTransitionError(VisualNovelError):
    """非法状态转换。"""


class SaveDataError(VisualNovelError):
    """存档数据异常。"""


class ConfigurationError(VisualNovelError):
    """配置错误。"""


class DialogueScriptError(VisualNovelError):
    """对话脚本解析错误。"""
