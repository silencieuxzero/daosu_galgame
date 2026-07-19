"""对话系统模块单元测试。"""

import json
import os
import tempfile
import unittest

from plugins.visual_novel.modules.dialogue import DialogueChoice, DialogueManager, DialogueNode, DialogueScript


class TestDialogueNode(unittest.TestCase):
    """DialogueNode 测试。"""

    def test_has_choices_true(self) -> None:
        """有选项时返回 True。"""
        node = DialogueNode(
            node_id="test",
            speaker="玲",
            text="你好",
            choices=[DialogueChoice(text="选项1", next_node="node2")],
        )
        self.assertTrue(node.has_choices())

    def test_has_choices_false(self) -> None:
        """无选项时返回 False。"""
        node = DialogueNode(node_id="test", speaker="玲", text="你好")
        self.assertFalse(node.has_choices())

    def test_is_venting_true(self) -> None:
        """倾诉烦恼情绪应检测正确。"""
        for emotion in ("sad", "anxious", "frustrated", "venting"):
            node = DialogueNode(node_id="test", speaker="玲", text="...", emotion=emotion)
            self.assertTrue(node.is_venting(), f"{emotion} 应被检测为倾诉状态")

    def test_is_venting_false(self) -> None:
        """非倾诉情绪不应误判。"""
        for emotion in ("neutral", "happy", "warm", "angry"):
            node = DialogueNode(node_id="test", speaker="玲", text="...", emotion=emotion)
            self.assertFalse(node.is_venting())


class TestDialogueManager(unittest.TestCase):
    """DialogueManager 测试。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._events_dir = os.path.join(self._tmpdir, "events")
        os.makedirs(self._events_dir)
        self.manager = DialogueManager(self._events_dir)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _create_script(self, filename: str, data: dict) -> str:
        filepath = os.path.join(self._events_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return filepath

    def _make_test_script(self) -> dict:
        return {
            "script_id": "test_script",
            "title": "测试脚本",
            "start_node": "start",
            "characters": ["玲"],
            "nodes": {
                "start": {
                    "speaker": "narrator",
                    "text": "开始",
                    "emotion": "neutral",
                    "next_node": "choice_node",
                },
                "choice_node": {
                    "speaker": "玲",
                    "text": "选哪个？",
                    "emotion": "neutral",
                    "choices": [
                        {"text": "选项A", "next_node": "end_a", "option_id": "a", "affection_change": 5},
                        {"text": "选项B", "next_node": "end_b", "option_id": "b", "affection_change": -3},
                    ],
                },
                "end_a": {"speaker": "玲", "text": "选了A", "emotion": "happy", "next_node": None},
                "end_b": {"speaker": "玲", "text": "选了B", "emotion": "sad", "next_node": None},
            },
        }

    def test_load_all_scripts_empty(self) -> None:
        """空目录加载不应报错。"""
        self.manager.load_all_scripts()
        self.assertEqual(self.manager.list_scripts(), [])

    def test_start_script(self) -> None:
        """启动脚本应返回起始节点。"""
        data = self._make_test_script()
        self._create_script("test.json", data)
        node = self.manager.start_script("test_script")
        self.assertIsNotNone(node)
        self.assertEqual(node.node_id, "start")
        self.assertEqual(node.text, "开始")

    def test_start_script_not_found(self) -> None:
        """不存在的脚本应返回 None。"""
        node = self.manager.start_script("nonexistent")
        self.assertIsNone(node)

    def test_advance_to_next_node(self) -> None:
        """自动推进到下一个节点。"""
        data = self._make_test_script()
        self._create_script("test.json", data)
        self.manager.start_script("test_script")
        node = self.manager.advance()
        self.assertIsNotNone(node)
        self.assertEqual(node.node_id, "choice_node")
        self.assertTrue(node.has_choices())

    def test_advance_at_end_returns_none(self) -> None:
        """对话结尾推进应返回 None。"""
        data = self._make_test_script()
        self._create_script("test.json", data)
        self.manager.start_script("test_script")
        self.manager.advance()  # -> choice_node
        self.manager.choose(0)  # -> end_a
        node = self.manager.advance()  # end_a has no next
        self.assertIsNone(node)

    def test_choose_valid_option(self) -> None:
        """选择有效选项应跳转到正确节点。"""
        data = self._make_test_script()
        self._create_script("test.json", data)
        self.manager.start_script("test_script")
        self.manager.advance()  # -> choice_node
        node = self.manager.choose(0)  # -> end_a
        self.assertIsNotNone(node)
        self.assertEqual(node.node_id, "end_a")
        self.assertEqual(node.text, "选了A")

    def test_choose_invalid_index(self) -> None:
        """无效选项索引应返回 None。"""
        data = self._make_test_script()
        self._create_script("test.json", data)
        self.manager.start_script("test_script")
        self.manager.advance()
        node = self.manager.choose(99)
        self.assertIsNone(node)

    def test_choose_when_no_choices(self) -> None:
        """无选项时选择应返回 None。"""
        data = self._make_test_script()
        self._create_script("test.json", data)
        self.manager.start_script("test_script")
        node = self.manager.choose(0)
        self.assertIsNone(node)  # start node has no choices

    def test_current_node_tracking(self) -> None:
        """当前节点应正确追踪。"""
        data = self._make_test_script()
        self._create_script("test.json", data)
        self.manager.start_script("test_script")
        self.assertEqual(self.manager.get_current_node().node_id, "start")
        self.manager.advance()
        self.assertEqual(self.manager.get_current_node().node_id, "choice_node")

    def test_get_current_script(self) -> None:
        """当前脚本应正确返回。"""
        data = self._make_test_script()
        self._create_script("test.json", data)
        self.manager.start_script("test_script")
        script = self.manager.get_current_script()
        self.assertIsNotNone(script)
        self.assertEqual(script.script_id, "test_script")

    def test_is_current_node_venting(self) -> None:
        """检测当前节点是否倾诉状态。"""
        data = self._make_test_script()
        # 修改 end_a 为倾诉状态
        data["nodes"]["end_a"]["emotion"] = "sad"
        self._create_script("test.json", data)
        self.manager.start_script("test_script")
        self.manager.advance()
        self.manager.choose(0)
        self.assertTrue(self.manager.is_current_node_venting())

    def test_end_current(self) -> None:
        """结束当前对话应清空状态。"""
        data = self._make_test_script()
        self._create_script("test.json", data)
        self.manager.start_script("test_script")
        self.manager.end_current()
        self.assertIsNone(self.manager.get_current_node())
        self.assertIsNone(self.manager.get_current_script())

    def test_get_script_by_id(self) -> None:
        """get_script 应返回脚本对象但不启动。"""
        data = self._make_test_script()
        self._create_script("test.json", data)
        script = self.manager.get_script("test_script")
        self.assertIsNotNone(script)
        self.assertEqual(script.title, "测试脚本")
        self.assertIsNone(self.manager.get_current_script())

    def test_list_scripts(self) -> None:
        """list_scripts 应返回所有脚本 ID。"""
        data1 = self._make_test_script()
        self._create_script("s1.json", data1)
        data2 = dict(self._make_test_script())
        data2["script_id"] = "script2"
        self._create_script("s2.json", data2)
        self.manager.load_all_scripts()
        scripts = self.manager.list_scripts()
        self.assertIn("test_script", scripts)
        self.assertIn("script2", scripts)


if __name__ == "__main__":
    unittest.main()
