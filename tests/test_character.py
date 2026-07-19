"""角色系统模块单元测试。"""

import json
import os
import tempfile
import unittest

from plugins.visual_novel.core.exceptions import CharacterNotFoundError
from plugins.visual_novel.modules.character import CharacterManager, CharacterPrompt


class TestCharacterPrompt(unittest.TestCase):
    """CharacterPrompt 测试。"""

    def test_from_dict(self) -> None:
        """从字典创建角色数据。"""
        data = {
            "name": "测试角色",
            "nickname": "小测",
            "gender": "女",
            "age": 18,
            "personality": ["温柔", "善良"],
            "background": "测试背景",
            "dialogue_style": "温和",
            "likes": ["花"],
            "dislikes": ["噪音"],
            "hobbies": ["阅读"],
            "affection_thresholds": {"event_1": 30},
        }
        char = CharacterPrompt.from_dict(data)
        self.assertEqual(char.name, "测试角色")
        self.assertEqual(char.nickname, "小测")
        self.assertEqual(char.age, 18)
        self.assertEqual(char.personality, ["温柔", "善良"])

    def test_to_dict_roundtrip(self) -> None:
        """to_dict -> from_dict 应保持数据一致。"""
        original = CharacterPrompt(
            name="玲",
            nickname="小玲",
            gender="女",
            age=18,
            personality=["温柔"],
            background="花店店主",
            dialogue_style="温和",
            likes=["鲜花"],
            dislikes=["噪音"],
            hobbies=["园艺"],
            affection_thresholds={"event_1": 30},
        )
        data = original.to_dict()
        restored = CharacterPrompt.from_dict(data)
        self.assertEqual(restored.name, "玲")
        self.assertEqual(restored.age, 18)
        self.assertEqual(restored.likes, ["鲜花"])

    def test_get_full_prompt_includes_name(self) -> None:
        """get_full_prompt 应包含角色名称。"""
        char = CharacterPrompt(
            name="雪姬",
            nickname="小雪",
            gender="女",
            age=17,
            personality=["活泼"],
            background="学生",
            dialogue_style="活泼",
            likes=["运动"],
            dislikes=["无聊"],
            hobbies=["跑步"],
            affection_thresholds={},
        )
        prompt = char.get_full_prompt()
        self.assertIn("雪姬", prompt)
        self.assertIn("小雪", prompt)
        self.assertIn("活泼", prompt)
        self.assertIn("学生", prompt)


class TestCharacterManager(unittest.TestCase):
    """CharacterManager 测试。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._char_dir = os.path.join(self._tmpdir, "characters")
        os.makedirs(self._char_dir)
        self.manager = CharacterManager(self._char_dir)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _create_character_file(self, filename: str, data: dict) -> str:
        filepath = os.path.join(self._char_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return filepath

    def test_load_all_empty_dir(self) -> None:
        """空目录加载不应报错。"""
        self.manager.load_all()
        self.assertEqual(self.manager.list_characters(), [])

    def test_load_single_character(self) -> None:
        """加载单个角色文件。"""
        self._create_character_file("ling.json", {
            "name": "玲",
            "nickname": "小玲",
            "gender": "女",
            "age": 18,
            "personality": ["温柔"],
            "background": "花店",
            "dialogue_style": "温和",
            "likes": ["花"],
            "dislikes": ["噪音"],
            "hobbies": ["园艺"],
            "affection_thresholds": {},
        })
        self.manager.load_all()
        char = self.manager.get_character("玲")
        self.assertEqual(char.name, "玲")
        self.assertEqual(char.nickname, "小玲")

    def test_get_character_not_found(self) -> None:
        """获取不存在角色应抛出异常。"""
        with self.assertRaises(CharacterNotFoundError):
            self.manager.get_character("不存在")

    def test_list_characters(self) -> None:
        """list_characters 应返回所有角色名。"""
        self._create_character_file("ling.json", {
            "name": "玲", "nickname": "小玲", "gender": "女", "age": 18,
            "personality": [], "background": "", "dialogue_style": "",
            "likes": [], "dislikes": [], "hobbies": [],
            "affection_thresholds": {},
        })
        self._create_character_file("yuki.json", {
            "name": "雪姬", "nickname": "小雪", "gender": "女", "age": 17,
            "personality": [], "background": "", "dialogue_style": "",
            "likes": [], "dislikes": [], "hobbies": [],
            "affection_thresholds": {},
        })
        self.manager.load_all()
        chars = self.manager.list_characters()
        self.assertIn("玲", chars)
        self.assertIn("雪姬", chars)

    def test_reload_updates_data(self) -> None:
        """reload 应重新加载数据。"""
        self._create_character_file("ling.json", {
            "name": "玲", "nickname": "小玲", "gender": "女", "age": 18,
            "personality": [], "background": "", "dialogue_style": "温和",
            "likes": [], "dislikes": [], "hobbies": [],
            "affection_thresholds": {},
        })
        self.manager.load_all()
        char = self.manager.get_character("玲")
        self.assertEqual(char.dialogue_style, "温和")

        # 修改文件
        self._create_character_file("ling.json", {
            "name": "玲", "nickname": "小玲", "gender": "女", "age": 18,
            "personality": [], "background": "", "dialogue_style": "活泼",
            "likes": [], "dislikes": [], "hobbies": [],
            "affection_thresholds": {},
        })
        self.manager.reload()
        char = self.manager.get_character("玲")
        self.assertEqual(char.dialogue_style, "活泼")

    def test_get_all_characters(self) -> None:
        """get_all_characters 应返回完整字典。"""
        self._create_character_file("ling.json", {
            "name": "玲", "nickname": "小玲", "gender": "女", "age": 18,
            "personality": [], "background": "", "dialogue_style": "",
            "likes": [], "dislikes": [], "hobbies": [],
            "affection_thresholds": {},
        })
        all_chars = self.manager.get_all_characters()
        self.assertIn("玲", all_chars)

    def test_corrupted_file_skipped(self) -> None:
        """损坏的 JSON 文件应跳过不报错。"""
        filepath = os.path.join(self._char_dir, "bad.json")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        self.manager.load_all()  # Should not raise
        self.assertEqual(self.manager.list_characters(), [])


if __name__ == "__main__":
    unittest.main()
