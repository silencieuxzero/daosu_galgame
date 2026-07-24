"""有限状态机（FSM）—— 管理游戏流程状态转换。

定义游戏中所有可能的状态以及状态之间的合法转换规则。
状态机确保游戏流程不会出现非法跳转，维护状态的连贯性与可预测性。

设计原则：
- 单向依赖：fsm 模块不依赖任何业务模块，只导出 GameState 枚举和 StateMachine 类
- 显式规则：所有允许的状态转换在 _ALLOWED_TRANSITIONS 中集中声明
- 回调机制：支持注册进入状态时的回调函数，便于触发副作用
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable


class GameState(Enum):
    """游戏状态枚举。

    定义了游戏中所有可能的运行状态。使用 auto() 自动分配不重复的整数值。
    每个状态对应一个特定的游戏界面或操作阶段。
    """

    IDLE = auto()          # 空闲/未开始：插件刚加载，尚未进入游戏
    MAIN_MENU = auto()     # 主菜单：选择角色、读取存档等
    TUTORIAL = auto()      # 新手引导：首次进入游戏时的交互式教程
    EXPLORATION = auto()   # 自由探索（向后兼容保留，新流程使用 PLOT_SCRIPT）
    DIALOGUE = auto()      # 剧情对话：正在进行固定脚本的对话流程
    EVENT = auto()         # 特殊事件：触发特殊的剧情事件
    SAVE_MENU = auto()     # 存档/读档：管理保存进度
    PLOT_SCRIPT = auto()     # 游戏模式（统一剧情+探索）：沉浸式叙事
    CHAT = auto()            # 自由聊天模式（/dsv chat 命令触发，通过 LLM 实时对话）


# 合法的状态转换映射表
# 每个状态映射到其允许跳转的目标状态集合。
# 此映射是静态只读的，运行时不会被修改。
_ALLOWED_TRANSITIONS: dict[GameState, set[GameState]] = {
    GameState.IDLE: {GameState.MAIN_MENU, GameState.TUTORIAL},
    GameState.MAIN_MENU: {
        GameState.EXPLORATION,
        GameState.SAVE_MENU,
        GameState.IDLE,
        GameState.TUTORIAL,
        GameState.PLOT_SCRIPT,
    },
    GameState.TUTORIAL: {
        GameState.DIALOGUE,
        GameState.MAIN_MENU,
        GameState.PLOT_SCRIPT,
    },
    GameState.EXPLORATION: {
        GameState.DIALOGUE,
        GameState.EVENT,
        GameState.SAVE_MENU,
        GameState.MAIN_MENU,
        GameState.CHAT,
        GameState.PLOT_SCRIPT,
    },
    GameState.DIALOGUE: {
        GameState.EXPLORATION,
        GameState.EVENT,
        GameState.SAVE_MENU,
        GameState.PLOT_SCRIPT,
    },
    GameState.EVENT: {
        GameState.DIALOGUE,
        GameState.EXPLORATION,
        GameState.PLOT_SCRIPT,
    },
    GameState.SAVE_MENU: {
        GameState.EXPLORATION,
        GameState.MAIN_MENU,
        GameState.DIALOGUE,
        GameState.PLOT_SCRIPT,
    },
    GameState.PLOT_SCRIPT: {
        GameState.EXPLORATION,
        GameState.MAIN_MENU,
        GameState.SAVE_MENU,
        GameState.CHAT,
        GameState.DIALOGUE,
        GameState.EVENT,
    },
    GameState.CHAT: {
        GameState.EXPLORATION,
        GameState.MAIN_MENU,
        GameState.PLOT_SCRIPT,
    },
}


class StateMachine:
    """有限状态机。

    管理游戏运行流程中的状态转换，确保所有转换符合预定义的规则。
    提供状态查询、转换校验、监听回调等基本能力。

    Attributes:
        _current_state: 当前状态。
        _previous_state: 上一个状态，用于回溯。
        _listeners: 状态进入监听器，key 为状态，value 为回调函数列表。

    Usage:
        fsm = StateMachine(GameState.IDLE)
        fsm.transition_to(GameState.MAIN_MENU)  # 合法转换
        print(fsm.current_state)  # GameState.MAIN_MENU
    """

    def __init__(self, initial_state: GameState = GameState.IDLE) -> None:
        """初始化状态机。

        Args:
            initial_state: 初始状态，默认为 IDLE。
        """
        self._current_state = initial_state
        self._previous_state: GameState | None = None
        self._listeners: dict[GameState, list[Callable[[], None]]] = {}

    @property
    def current_state(self) -> GameState:
        """获取当前状态。"""
        return self._current_state

    @property
    def previous_state(self) -> GameState | None:
        """获取上一个状态。

        在首次转换前返回 None。
        """
        return self._previous_state

    def can_transition_to(self, target: GameState) -> bool:
        """检查当前状态下是否允许转换到目标状态。

        用于调用方在正式转换前做预检，避免抛出异常。

        Args:
            target: 要检查的目标状态。

        Returns:
            如果允许转换返回 True，否则 False。
        """
        return target in _ALLOWED_TRANSITIONS.get(self._current_state, set())

    def get_allowed_transitions(self) -> list[GameState]:
        """获取当前状态下所有允许转换的目标状态列表。

        Returns:
            当前状态可转换到的目标状态列表。
        """
        return list(_ALLOWED_TRANSITIONS.get(self._current_state, set()))

    def transition_to(self, target: GameState) -> None:
        """执行状态转换。

        将当前状态更新为目标状态，记录旧状态为 previous_state，
        并在转换完成后通知所有注册到该状态的监听器。

        Args:
            target: 目标状态。

        Raises:
            InvalidStateTransitionError: 如果当前状态不允许转换到目标状态。
        """
        from .exceptions import InvalidStateTransitionError

        if not self.can_transition_to(target):
            raise InvalidStateTransitionError(
                f"不允许从 {self._current_state.name} 转换到 {target.name}。"
                f"允许的目标: {[s.name for s in self.get_allowed_transitions()]}"
            )

        self._previous_state = self._current_state
        self._current_state = target
        self._notify_listeners(target)

    def reset(self) -> None:
        """重置状态机到初始状态。

        通常在插件卸载或游戏重启时调用。
        """
        self._current_state = GameState.IDLE
        self._previous_state = None

    def on_state(self, state: GameState, callback: Callable[[], None]) -> None:
        """注册进入指定状态时的回调函数。

        回调会在每次进入对应状态时被调用。如果需要在状态转换时
        执行副作用（如播放音效、自动保存等），可通过此机制实现。

        Args:
            state: 要监听的状态。
            callback: 无参回调函数，进入 state 时被调用。
        """
        if state not in self._listeners:
            self._listeners[state] = []
        self._listeners[state].append(callback)

    def _notify_listeners(self, state: GameState) -> None:
        """通知指定状态的所有监听器。

        遍历并调用所有注册到该状态的回调函数。
        单个回调的异常被吞掉，不影响其他回调的执行。"""
        for callback in self._listeners.get(state, []):
            try:
                callback()
            except Exception:
                pass  # 避免回调异常影响状态机运行
