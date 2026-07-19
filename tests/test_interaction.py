"""互动行为系统模块单元测试。"""

import unittest

from plugins.visual_novel.modules.affection import AffectionManager
from plugins.visual_novel.modules.interaction import (
    Activity,
    DEFAULT_ACTIVITIES,
    DEFAULT_GIFTS,
    GiftItem,
    InteractionManager,
)
from plugins.visual_novel.modules.notebook import NotebookManager


class TestGiftItem(unittest.TestCase):
    """GiftItem 测试。"""

    def test_to_dict(self) -> None:
        """序列化。"""
        gift = GiftItem(name="花束", description="鲜花", category="decoration", base_affection=5, tags=["romantic"])
        data = gift.to_dict()
        self.assertEqual(data["name"], "花束")
        self.assertEqual(data["base_affection"], 5)

    def test_from_dict(self) -> None:
        """反序列化。"""
        data = {"name": "巧克力", "description": "香浓巧克力", "category": "food", "base_affection": 7, "tags": ["sweet"]}
        gift = GiftItem.from_dict(data)
        self.assertEqual(gift.name, "巧克力")
        self.assertEqual(gift.base_affection, 7)


class TestActivity(unittest.TestCase):
    """Activity 测试。"""

    def test_to_dict(self) -> None:
        """序列化。"""
        act = Activity(name="散步", description="公园散步", category="relax", base_affection=3)
        data = act.to_dict()
        self.assertEqual(data["name"], "散步")
        self.assertEqual(data["category"], "relax")

    def test_from_dict(self) -> None:
        """反序列化。"""
        data = {"name": "看电影", "description": "看电影", "category": "date", "base_affection": 5, "duration": "medium", "tags": []}
        act = Activity.from_dict(data)
        self.assertEqual(act.name, "看电影")


class TestInteractionManager(unittest.TestCase):
    """InteractionManager 测试。"""

    def setUp(self) -> None:
        self._affection = AffectionManager()
        self._notebook = NotebookManager("")
        self._notebook.auto_save = False
        self.manager = InteractionManager(self._affection, self._notebook)

    def test_default_gifts_exist(self) -> None:
        """默认礼物应正确初始化。"""
        gifts = self.manager.list_available_gifts()
        # 初始背包为空
        self.assertEqual(gifts, [])

    def test_add_gift_to_inventory(self) -> None:
        """添加礼物到背包。"""
        result = self.manager.add_gift_to_inventory("花束")
        self.assertTrue(result)
        self.assertEqual(len(self.manager.list_available_gifts()), 1)

    def test_add_nonexistent_gift(self) -> None:
        """添加不存在的礼物应返回 False。"""
        result = self.manager.add_gift_to_inventory("不存在")
        self.assertFalse(result)

    def test_add_all_default_gifts(self) -> None:
        """批量添加默认礼物。"""
        self.manager.add_all_default_gifts()
        self.assertEqual(len(self.manager.list_available_gifts()), len(DEFAULT_GIFTS))

    def test_give_gift_success(self) -> None:
        """赠送礼物成功。"""
        self.manager.add_all_default_gifts()
        result = self.manager.give_gift("玲", "花束")
        self.assertTrue(result["success"])
        self.assertGreater(result["affection_change"], 0)

    def test_give_gift_not_in_inventory(self) -> None:
        """背包中无此礼物应失败。"""
        result = self.manager.give_gift("玲", "花束")
        self.assertFalse(result["success"])

    def test_give_gift_nonexistent(self) -> None:
        """不存在的礼物应失败。"""
        result = self.manager.give_gift("玲", "不存在")
        self.assertFalse(result["success"])

    def test_give_gift_updates_affection(self) -> None:
        """赠送礼物后好感度应更新。"""
        self.manager.add_all_default_gifts()
        self.manager.give_gift("玲", "花束")
        self.assertGreater(self._affection.get_value("玲"), 0)

    def test_give_gift_removes_from_inventory(self) -> None:
        """赠送后礼物应从背包移除。"""
        self.manager.add_gift_to_inventory("花束")
        self.manager.give_gift("玲", "花束")
        self.assertEqual(len(self.manager.list_available_gifts()), 0)

    def test_give_gift_with_notebook_hint(self) -> None:
        """有关联线索时应返回提示。"""
        self.manager.add_all_default_gifts()
        self._notebook.scan_text_for_clues("我喜欢漂亮的花", "玲")
        result = self.manager.give_gift("玲", "花束")
        self.assertIsNotNone(result.get("hint"))

    def test_list_activities(self) -> None:
        """列出活动。"""
        activities = self.manager.list_activities()
        self.assertEqual(len(activities), len(DEFAULT_ACTIVITIES))

    def test_invite_success(self) -> None:
        """邀请活动成功。"""
        result = self.manager.invite("玲", "散步")
        self.assertTrue(result["success"])
        self.assertGreater(result["affection_change"], 0)

    def test_invite_nonexistent_activity(self) -> None:
        """不存在的活动应失败。"""
        result = self.manager.invite("玲", "不存在")
        self.assertFalse(result["success"])

    def test_invite_updates_affection(self) -> None:
        """邀请后好感度应更新。"""
        self.manager.invite("玲", "散步")
        self.assertGreater(self._affection.get_value("玲"), 0)

    def test_process_daily_talk(self) -> None:
        """日常对话处理。"""
        result = self.manager.process_daily_talk("玲", "你好，今天天气真不错")
        self.assertIn("你好", result["keywords"])
        self.assertIn("天气", result["keywords"])

    def test_daily_talk_discovers_clues(self) -> None:
        """日常对话应发现线索。"""
        result = self.manager.process_daily_talk("玲", "我喜欢和喜欢的花在一起")
        self.assertGreater(result["clues_discovered"], 0)

    def test_dump_and_load_state(self) -> None:
        """状态持久化。"""
        self.manager.add_gift_to_inventory("花束")
        self.manager.add_gift_to_inventory("巧克力")

        dumped = self.manager.dump_state()
        new_manager = InteractionManager(self._affection)
        new_manager.load_state(dumped)

        self.assertEqual(len(new_manager.list_available_gifts()), 2)


if __name__ == "__main__":
    unittest.main()
