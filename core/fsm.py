"""有限状态机（FSM）—— 管理游戏流程状态转换。"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable


class GameState(Enum):
    """游戏状态枚举。"""

    IDLE = auto()  # 空闲/未开始
    MAIN_MENU = auto()  # 主菜单
    EXPLORATION = auto()  # 自由探索/日常对话
    DIALOGUE = auto()  # 剧情对话
    EVENT = auto()  # 特殊事件
    GIFT_MENU = auto()  # 礼物赠送界面
    INVITE_MENU = auto()  # 邀约界面
    NOTEBOOK = auto()  # 记事本
    SAVE_MENU = auto()  # 存档/读档
    AWAITING_CHOICE = auto()  # 等待玩家选择


# 合法的状态转换映射表
_ALLOWED_TRANSITIONS: dict[GameState, set[GameState]] = {
    GameState.IDLE: {GameState.MAIN_MENU},
    GameState.MAIN_MENU: {
        GameState.EXPLORATION,
        GameState.SAVE_MENU,
        GameState.NOTEBOOK,
        GameState.IDLE,
    },
    GameState.EXPLORATION: {
        GameState.DIALOGUE,
        GameState.EVENT,
        GameState.GIFT_MENU,
        GameState.INVITE_MENU,
        GameState.NOTEBOOK,
        GameState.SAVE_MENU,
        GameState.MAIN_MENU,
    },
    GameState.DIALOGUE: {
        GameState.EXPLORATION,
        GameState.EVENT,
        GameState.AWAITING_CHOICE,
        GameState.SAVE_MENU,
    },
    GameState.EVENT: {
        GameState.DIALOGUE,
        GameState.EXPLORATION,
        GameState.AWAITING_CHOICE,
    },
    GameState.GIFT_MENU: {GameState.EXPLORATION, GameState.DIALOGUE},
    GameState.INVITE_MENU: {GameState.EXPLORATION, GameState.DIALOGUE},
    GameState.NOTEBOOK: {GameState.EXPLORATION, GameState.MAIN_MENU},
    GameState.SAVE_MENU: {
        GameState.EXPLORATION,
        GameState.MAIN_MENU,
        GameState.DIALOGUE,
    },
    GameState.AWAITING_CHOICE: {GameState.DIALOGUE, GameState.EVENT, GameState.EXPLORATION},
}


class StateMachine:
    """有限状态机。

    管理游戏运行流程中的状态转换，确保所有转换符合预定义的规则。
    """

    def __init__(self, initial_state: GameState = GameState.IDLE) -> None:
        self._current_state = initial_state
        self._previous_state: GameState | None = None
        self._listeners: dict[GameState, list[Callable[[], None]]] = {}

    @property
    def current_state(self) -> GameState:
        """获取当前状态。"""
        return self._current_state

    @property
    def previous_state(self) -> GameState | None:
        """获取上一个状态。"""
        return self._previous_state

    def can_transition_to(self, target: GameState) -> bool:
        """检查是否可以转换到目标状态。"""
        return target in _ALLOWED_TRANSITIONS.get(self._current_state, set())

    def get_allowed_transitions(self) -> list[GameState]:
        """获取当前状态下所有允许转换的目标状态列表。"""
        return list(_ALLOWED_TRANSITIONS.get(self._current_state, set()))

    def transition_to(self, target: GameState) -> None:
        """执行状态转换。

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
        """重置状态机到初始状态。"""
        self._current_state = GameState.IDLE
        self._previous_state = None

    def on_state(self, state: GameState, callback: Callable[[], None]) -> None:
        """注册进入指定状态时的回调。

        Args:
            state: 要监听的状态。
            callback: 无参回调函数。
        """
        if state not in self._listeners:
            self._listeners[state] = []
        self._listeners[state].append(callback)

    def _notify_listeners(self, state: GameState) -> None:
        """通知指定状态的所有监听器。"""
        for callback in self._listeners.get(state, []):
            try:
                callback()
            except Exception:
                pass  # 避免回调异常影响状态机运行
