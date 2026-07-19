"""状态机模块单元测试。"""

import unittest

from plugins.visual_novel.core.exceptions import InvalidStateTransitionError
from plugins.visual_novel.core.fsm import GameState, StateMachine


class TestStateMachine(unittest.TestCase):
    """StateMachine 测试。"""

    def setUp(self) -> None:
        self.fsm = StateMachine()

    def test_initial_state_is_idle(self) -> None:
        """初始状态应为 IDLE。"""
        self.assertEqual(self.fsm.current_state, GameState.IDLE)

    def test_transition_to_main_menu(self) -> None:
        """IDLE -> MAIN_MENU 应成功。"""
        self.fsm.transition_to(GameState.MAIN_MENU)
        self.assertEqual(self.fsm.current_state, GameState.MAIN_MENU)

    def test_invalid_transition_raises(self) -> None:
        """IDLE -> DIALOGUE 应抛出异常。"""
        with self.assertRaises(InvalidStateTransitionError):
            self.fsm.transition_to(GameState.DIALOGUE)

    def test_can_transition_to(self) -> None:
        """can_transition_to 应正确判断。"""
        self.assertTrue(self.fsm.can_transition_to(GameState.MAIN_MENU))
        self.assertFalse(self.fsm.can_transition_to(GameState.DIALOGUE))

    def test_get_allowed_transitions(self) -> None:
        """get_allowed_transitions 应返回合法目标列表。"""
        allowed = self.fsm.get_allowed_transitions()
        self.assertEqual(allowed, [GameState.MAIN_MENU])

    def test_previous_state(self) -> None:
        """previous_state 应记录上一个状态。"""
        self.fsm.transition_to(GameState.MAIN_MENU)
        self.assertEqual(self.fsm.previous_state, GameState.IDLE)

        self.fsm.transition_to(GameState.EXPLORATION)
        self.assertEqual(self.fsm.previous_state, GameState.MAIN_MENU)

    def test_reset(self) -> None:
        """reset 应恢复到 IDLE。"""
        self.fsm.transition_to(GameState.MAIN_MENU)
        self.fsm.reset()
        self.assertEqual(self.fsm.current_state, GameState.IDLE)
        self.assertIsNone(self.fsm.previous_state)

    def test_full_path_exploration(self) -> None:
        """测试完整的探索路径。"""
        # IDLE -> MAIN_MENU
        self.fsm.transition_to(GameState.MAIN_MENU)
        self.assertEqual(self.fsm.current_state, GameState.MAIN_MENU)

        # MAIN_MENU -> EXPLORATION
        self.fsm.transition_to(GameState.EXPLORATION)
        self.assertEqual(self.fsm.current_state, GameState.EXPLORATION)

        # EXPLORATION -> GIFT_MENU
        self.fsm.transition_to(GameState.GIFT_MENU)
        self.assertEqual(self.fsm.current_state, GameState.GIFT_MENU)

    def test_dialogue_with_choice(self) -> None:
        """对话带选择的路径。"""
        self.fsm.transition_to(GameState.MAIN_MENU)
        self.fsm.transition_to(GameState.EXPLORATION)
        self.fsm.transition_to(GameState.DIALOGUE)
        self.fsm.transition_to(GameState.AWAITING_CHOICE)
        self.fsm.transition_to(GameState.DIALOGUE)

    def test_state_listener(self) -> None:
        """状态进入监听器应被调用。"""
        calls = []

        def on_main_menu() -> None:
            calls.append("entered_main_menu")

        self.fsm.on_state(GameState.MAIN_MENU, on_main_menu)
        self.fsm.transition_to(GameState.MAIN_MENU)
        self.assertEqual(calls, ["entered_main_menu"])

    def test_state_listener_not_called_for_other_states(self) -> None:
        """监听器不应在其他状态进入时触发。"""
        calls = []

        def on_exploration() -> None:
            calls.append("entered_exploration")

        self.fsm.on_state(GameState.EXPLORATION, on_exploration)
        self.fsm.transition_to(GameState.MAIN_MENU)
        self.assertEqual(calls, [])

    def test_state_listener_exception_does_not_block(self) -> None:
        """监听器异常不应影响状态机。"""

        def failing_listener() -> None:
            raise RuntimeError("listener failed")

        self.fsm.on_state(GameState.MAIN_MENU, failing_listener)
        # Should not raise
        self.fsm.transition_to(GameState.MAIN_MENU)
        self.assertEqual(self.fsm.current_state, GameState.MAIN_MENU)


if __name__ == "__main__":
    unittest.main()
