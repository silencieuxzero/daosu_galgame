"""记事本与线索系统模块单元测试。"""

import tempfile
import unittest

from plugins.visual_novel.modules.notebook import CATEGORY_LABELS, CLUE_KEYWORDS, Clue, NotebookManager


class TestClue(unittest.TestCase):
    """Clue 数据类测试。"""

    def test_default_timestamp(self) -> None:
        """创建时自动生成时间戳。"""
        clue = Clue(category="likes", content="喜欢花", source="对话", character_name="玲")
        self.assertTrue(len(clue.discovered_at) > 0)
        self.assertFalse(clue.confirmed)

    def test_to_dict(self) -> None:
        """序列化应包含所有字段。"""
        clue = Clue(category="likes", content="喜欢花", source="对话", character_name="玲", confirmed=True)
        data = clue.to_dict()
        self.assertEqual(data["category"], "likes")
        self.assertEqual(data["content"], "喜欢花")
        self.assertEqual(data["confirmed"], True)

    def test_from_dict(self) -> None:
        """反序列化应正确恢复。"""
        data = {
            "category": "hobbies",
            "content": "喜欢跑步",
            "source": "对话",
            "character_name": "雪姬",
            "discovered_at": "2024-01-01T00:00:00",
            "confirmed": False,
        }
        clue = Clue.from_dict(data)
        self.assertEqual(clue.category, "hobbies")
        self.assertEqual(clue.content, "喜欢跑步")
        self.assertEqual(clue.character_name, "雪姬")

    def test_category_labels_completeness(self) -> None:
        """所有线索分类都应有中文标签。"""
        for cat in CLUE_KEYWORDS:
            self.assertIn(cat, CATEGORY_LABELS, f"分类 '{cat}' 缺少中文标签")


class TestNotebookManager(unittest.TestCase):
    """NotebookManager 测试。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.manager = NotebookManager(self._tmpdir)
        self.manager.auto_save = False  # 测试中关闭自动保存

    def test_initial_empty(self) -> None:
        """初始无线索。"""
        self.assertEqual(self.manager.get_clues_for_character("玲"), [])

    def test_add_clue(self) -> None:
        """添加单条线索。"""
        clue = Clue(category="likes", content="喜欢花", source="对话", character_name="玲")
        result = self.manager.add_clue(clue)
        self.assertTrue(result)
        self.assertEqual(len(self.manager.get_clues_for_character("玲")), 1)

    def test_add_duplicate_clue(self) -> None:
        """重复线索不应添加。"""
        clue = Clue(category="likes", content="喜欢花", source="对话", character_name="玲")
        self.manager.add_clue(clue)
        result = self.manager.add_clue(clue)
        self.assertFalse(result)
        self.assertEqual(len(self.manager.get_clues_for_character("玲")), 1)

    def test_scan_text_for_clues_finds_likes(self) -> None:
        """扫描文本应发现喜欢类线索。"""
        discovered = self.manager.scan_text_for_clues("我最喜欢花了", "玲")
        self.assertGreater(len(discovered), 0)
        # 至少有一条是 likes 类别
        likes_found = [c for c in discovered if c.category == "likes"]
        self.assertGreater(len(likes_found), 0)

    def test_scan_text_for_clues_finds_dislikes(self) -> None:
        """扫描文本应发现厌恶类线索。"""
        discovered = self.manager.scan_text_for_clues("我讨厌吵闹的地方", "玲")
        dislikes_found = [c for c in discovered if c.category == "dislikes"]
        self.assertGreater(len(dislikes_found), 0)

    def test_scan_text_does_not_add_duplicates(self) -> None:
        """多次扫描相同文本不应添加重复线索。"""
        self.manager.scan_text_for_clues("我喜欢花", "玲")
        count_after_first = len(self.manager.get_clues_for_character("玲"))
        self.manager.scan_text_for_clues("我喜欢花", "玲")
        count_after_second = len(self.manager.get_clues_for_character("玲"))
        self.assertEqual(count_after_first, count_after_second)

    def test_get_clues_by_category(self) -> None:
        """按分类筛选线索。"""
        self.manager.scan_text_for_clues("我最喜欢花了", "玲")
        self.manager.scan_text_for_clues("我讨厌下雨天", "玲")
        likes = self.manager.get_clues_by_category("玲", "likes")
        dislikes = self.manager.get_clues_by_category("玲", "dislikes")
        self.assertGreater(len(likes), 0)
        self.assertGreater(len(dislikes), 0)

    def test_get_gift_hints(self) -> None:
        """获取礼物线索提示。"""
        self.manager.scan_text_for_clues("我喜欢漂亮的鲜花", "玲")
        hints = self.manager.get_gift_hints("玲")
        self.assertGreater(len(hints), 0)
        self.assertTrue(any("玲" in h for h in hints))

    def test_get_gift_hints_empty(self) -> None:
        """无线索时应返回空列表。"""
        hints = self.manager.get_gift_hints("未知角色")
        self.assertEqual(hints, [])

    def test_check_gift_match_no_clues(self) -> None:
        """无线索时匹配检查应返回 None。"""
        result = self.manager.check_gift_match("玲", "花束")
        self.assertIsNone(result)

    def test_check_gift_match_with_clues(self) -> None:
        """有线索时应返回匹配提示。"""
        self.manager.scan_text_for_clues("我喜欢花", "玲")
        result = self.manager.check_gift_match("玲", "花束")
        # 礼物名称"花束"应匹配喜欢类线索
        self.assertIsNotNone(result)

    def test_summarize_with_character(self) -> None:
        """按角色生成摘要。"""
        self.manager.scan_text_for_clues("我喜欢花", "玲")
        summary = self.manager.summarize("玲")
        self.assertIn("玲", summary)
        self.assertIn("喜爱之物", summary)

    def test_summarize_empty(self) -> None:
        """空记事本摘要。"""
        summary = self.manager.summarize()
        self.assertIn("暂无线索记录", summary)

    def test_dump_and_load_state(self) -> None:
        """dump_state -> load_state 应保持数据一致。"""
        self.manager.scan_text_for_clues("我喜欢花", "玲")
        self.manager.scan_text_for_clues("我讨厌下雨", "玲")
        dumped = self.manager.dump_state()

        new_manager = NotebookManager(self._tmpdir)
        new_manager.load_state(dumped)
        self.assertEqual(
            len(new_manager.get_clues_for_character("玲")),
            len(self.manager.get_clues_for_character("玲")),
        )

    def test_clear(self) -> None:
        """清空所有线索。"""
        self.manager.scan_text_for_clues("我喜欢花", "玲")
        self.manager.clear()
        self.assertEqual(self.manager.get_clues_for_character("玲"), [])

    def test_save_and_load(self) -> None:
        """持久化保存与加载。"""
        self.manager.auto_save = True
        self.manager.scan_text_for_clues("我喜欢花", "玲")

        new_manager = NotebookManager(self._tmpdir)
        new_manager.load()
        self.assertEqual(len(new_manager.get_clues_for_character("玲")), 1)


if __name__ == "__main__":
    unittest.main()
