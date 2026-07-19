"""好感度系统模块单元测试。"""

import unittest

from plugins.visual_novel.modules.affection import (
    AFFECTION_LEVELS,
    AffectionManager,
    AffectionRule,
    AffectionState,
    get_affection_level,
)
from plugins.visual_novel.modules.character import CharacterManager, CharacterPrompt


class TestAffectionLevel(unittest.TestCase):
    """好感度等级函数测试。"""

    def test_get_affection_level_values(self) -> None:
        """各级好感度应正确返回。"""
        self.assertEqual(get_affection_level(-100), "冷漠")
        self.assertEqual(get_affection_level(-60), "冷漠")
        self.assertEqual(get_affection_level(-50), "陌生")
        self.assertEqual(get_affection_level(-1), "陌生")
        self.assertEqual(get_affection_level(0), "普通")
        self.assertEqual(get_affection_level(15), "普通")
        self.assertEqual(get_affection_level(30), "普通")
        self.assertEqual(get_affection_level(31), "友好")
        self.assertEqual(get_affection_level(60), "友好")
        self.assertEqual(get_affection_level(61), "亲近")
        self.assertEqual(get_affection_level(80), "亲近")
        self.assertEqual(get_affection_level(81), "亲密")
        self.assertEqual(get_affection_level(95), "亲密")
        self.assertEqual(get_affection_level(96), "爱慕")
        self.assertEqual(get_affection_level(100), "爱慕")


class TestAffectionState(unittest.TestCase):
    """AffectionState 测试。"""

    def test_initial_value(self) -> None:
        """初始好感度应为 0。"""
        state = AffectionState(character_name="玲")
        self.assertEqual(state.value, 0)
        self.assertEqual(state.level, "普通")

    def test_level_changes(self) -> None:
        """好感度变化后等级应更新。"""
        state = AffectionState(character_name="玲", value=80)
        self.assertEqual(state.level, "亲近")

        state.value = 100
        self.assertEqual(state.level, "爱慕")

    def test_to_dict(self) -> None:
        """序列化应包含必要字段。"""
        state = AffectionState(character_name="玲", value=50)
        data = state.to_dict()
        self.assertEqual(data["character_name"], "玲")
        self.assertEqual(data["value"], 50)
        self.assertEqual(data["level"], "友好")

    def test_from_dict(self) -> None:
        """反序列化应正确恢复。"""
        data = {"character_name": "雪姬", "value": 75, "level": "亲近"}
        state = AffectionState.from_dict(data)
        self.assertEqual(state.character_name, "雪姬")
        self.assertEqual(state.value, 75)


class TestAffectionRule(unittest.TestCase):
    """AffectionRule 测试。"""

    def test_base_change(self) -> None:
        """无特殊条件下应使用 base_change。"""
        rule = AffectionRule(
            option_id="praise",
            description="赞美",
            base_change=5,
            personality_tags=["温和"],
        )
        change = rule.calculate_change(["温和"])
        self.assertEqual(change, 5)

    def test_reverse_for_tags(self) -> None:
        """匹配 reverse_for_tags 时应取反。"""
        rule = AffectionRule(
            option_id="praise",
            description="赞美",
            base_change=5,
            personality_tags=["温和"],
            reverse_for_tags=["傲娇"],
        )
        change = rule.calculate_change(["傲娇"])
        self.assertEqual(change, -5)

    def test_special_multiplier(self) -> None:
        """匹配 special_multiplier 时应应用倍率。"""
        rule = AffectionRule(
            option_id="praise",
            description="赞美",
            base_change=5,
            personality_tags=["温和"],
            special_multiplier={"内向": 2.0},
        )
        change = rule.calculate_change(["内向"])
        self.assertEqual(change, 10)  # 5 * 2.0

    def test_no_personality_match(self) -> None:
        """不匹配任何标签时使用 base_change。"""
        rule = AffectionRule(
            option_id="praise",
            description="赞美",
            base_change=5,
            personality_tags=["温和"],
        )
        change = rule.calculate_change(["活泼"])
        self.assertEqual(change, 5)


class TestAffectionManager(unittest.TestCase):
    """AffectionManager 测试。"""

    def setUp(self) -> None:
        self.manager = AffectionManager()

    def test_initial_state(self) -> None:
        """首次 get 应返回普通等级。"""
        state = self.manager.get_or_create_state("玲")
        self.assertEqual(state.value, 0)

    def test_modify_increases(self) -> None:
        """增加好感度。"""
        self.manager.modify("玲", 10)
        self.assertEqual(self.manager.get_value("玲"), 10)

    def test_modify_decreases(self) -> None:
        """降低好感度。"""
        self.manager.modify("玲", 10)
        self.manager.modify("玲", -5)
        self.assertEqual(self.manager.get_value("玲"), 5)

    def test_modify_clamps_to_100(self) -> None:
        """好感度不应超过 100。"""
        self.manager.modify("玲", 200)
        self.assertEqual(self.manager.get_value("玲"), 100)

    def test_modify_clamps_to_neg100(self) -> None:
        """好感度不应低于 -100。"""
        self.manager.modify("玲", -200)
        self.assertEqual(self.manager.get_value("玲"), -100)

    def test_get_level(self) -> None:
        """get_level 应返回正确等级。"""
        self.assertEqual(self.manager.get_level("玲"), "普通")
        self.manager.modify("玲", -60)
        self.assertEqual(self.manager.get_level("玲"), "冷漠")

    def test_register_and_apply_rule(self) -> None:
        """注册规则并应用。"""
        rule = AffectionRule(
            option_id="praise",
            description="赞美",
            base_change=5,
            personality_tags=["温和"],
        )
        self.manager.register_rule("玲", rule)

        # 没有角色管理器时，使用 base_change
        change = self.manager.apply_option("玲", "praise")
        self.assertEqual(change, 5)

    def test_apply_option_no_rule(self) -> None:
        """不存在的选项应返回 0。"""
        change = self.manager.apply_option("玲", "nonexistent")
        self.assertEqual(change, 0)

    def test_get_all_states(self) -> None:
        """get_all_states 应返回所有角色状态。"""
        self.manager.modify("玲", 10)
        self.manager.modify("雪姬", 20)
        states = self.manager.get_all_states()
        self.assertIn("玲", states)
        self.assertIn("雪姬", states)
        self.assertEqual(states["玲"].value, 10)
        self.assertEqual(states["雪姬"].value, 20)

    def test_dump_and_load_state(self) -> None:
        """dump_state -> load_state 应保持数据一致。"""
        self.manager.modify("玲", 50)
        self.manager.modify("雪姬", -20)
        dumped = self.manager.dump_state()

        new_manager = AffectionManager()
        new_manager.load_state(dumped)
        self.assertEqual(new_manager.get_value("玲"), 50)
        self.assertEqual(new_manager.get_value("雪姬"), -20)

    def test_register_rules_from_config(self) -> None:
        """批量注册规则。"""
        config = [
            {"option_id": "praise", "description": "赞美", "base_change": 5, "personality_tags": ["温和"]},
            {"option_id": "criticize", "description": "批评", "base_change": -5, "personality_tags": ["温和"]},
        ]
        self.manager.register_rules_from_config("玲", config)
        change1 = self.manager.apply_option("玲", "praise")
        change2 = self.manager.apply_option("玲", "criticize")
        self.assertEqual(change1, 5)
        self.assertEqual(change2, -5)

    def test_threshold_event(self) -> None:
        """好感度阈值检测。"""
        from unittest.mock import Mock, MagicMock

        character = CharacterPrompt(
            name="玲", nickname="小玲", gender="女", age=18,
            personality=["温柔"], background="", dialogue_style="",
            likes=[], dislikes=[], hobbies=[],
            affection_thresholds={"event_friendship": 30, "event_love": 60},
        )

        self.manager.modify("玲", 20)
        event = self.manager.get_threshold_event("玲", character)
        # 20 < 30，不应触发
        self.assertIsNone(event)

        self.manager.modify("玲", 15)  # now 35
        event = self.manager.get_threshold_event("玲", character)
        self.assertEqual(event, "event_friendship")


if __name__ == "__main__":
    unittest.main()
