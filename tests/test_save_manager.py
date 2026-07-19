"""存档管理模块单元测试。"""

import os
import tempfile
import unittest

from plugins.visual_novel.core.exceptions import SaveDataError
from plugins.visual_novel.modules.save_manager import SaveManager, SaveSlot


class TestSaveSlot(unittest.TestCase):
    """SaveSlot 测试。"""

    def test_to_dict(self) -> None:
        """序列化应包含所有字段。"""
        slot = SaveSlot(slot_id=1, timestamp="2024-01-01T00:00:00", label="测试存档")
        data = slot.to_dict()
        self.assertEqual(data["slot_id"], 1)
        self.assertEqual(data["label"], "测试存档")
        self.assertEqual(data["game_state"], "IDLE")

    def test_from_dict(self) -> None:
        """反序列化应正确恢复。"""
        data = {
            "slot_id": 3,
            "timestamp": "2024-06-15T12:30:00",
            "label": "重要存档",
            "game_state": "EXPLORATION",
            "current_script": "flower_shop",
            "current_node": "start",
            "affection_data": {"玲": {"character_name": "玲", "value": 50, "level": "友好"}},
            "notebook_data": [],
            "interaction_data": {},
            "choice_history": [],
            "metadata": {},
        }
        slot = SaveSlot.from_dict(data)
        self.assertEqual(slot.slot_id, 3)
        self.assertEqual(slot.game_state, "EXPLORATION")
        self.assertEqual(slot.current_script, "flower_shop")
        self.assertIn("玲", slot.affection_data)


class TestSaveManager(unittest.TestCase):
    """SaveManager 测试。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._save_dir = os.path.join(self._tmpdir, "saves")
        self.manager = SaveManager(self._save_dir, slot_count=5)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_scan_empty_slots(self) -> None:
        """初始所有槽位应为空。"""
        slots = self.manager.scan_slots()
        self.assertEqual(len(slots), 5)
        for slot_id in range(1, 6):
            self.assertIsNone(slots[slot_id])

    def test_save_and_scan(self) -> None:
        """保存后扫描应显示非空。"""
        self.manager.save(slot_id=1, label="测试存档", game_state="EXPLORATION")
        slots = self.manager.scan_slots()
        self.assertIsNotNone(slots[1])
        self.assertEqual(slots[1].label, "测试存档")
        self.assertEqual(slots[1].game_state, "EXPLORATION")

    def test_save_with_data(self) -> None:
        """保存时应包含完整数据。"""
        self.manager.save(
            slot_id=1,
            label="完整存档",
            game_state="DIALOGUE",
            current_script="flower_shop",
            current_node="start",
            affection_data={"玲": {"character_name": "玲", "value": 30, "level": "友好"}},
            notebook_data=[{"category": "likes", "content": "喜欢花", "source": "对话", "character_name": "玲"}],
        )
        slot = self.manager.get_slot_info(1)
        self.assertEqual(slot.current_script, "flower_shop")
        self.assertIn("玲", slot.affection_data)
        self.assertEqual(len(slot.notebook_data), 1)

    def test_load_returns_slot(self) -> None:
        """读档应返回正确的存档数据。"""
        self.manager.save(slot_id=1, label="测试")
        slot = self.manager.load(1)
        self.assertEqual(slot.slot_id, 1)
        self.assertEqual(slot.label, "测试")

    def test_load_nonexistent_raises(self) -> None:
        """加载不存在槽位应抛出异常。"""
        with self.assertRaises(SaveDataError):
            self.manager.load(1)

    def test_load_invalid_slot_id_raises(self) -> None:
        """无效槽位编号应抛出异常。"""
        with self.assertRaises(SaveDataError):
            self.manager.load(0)

        with self.assertRaises(SaveDataError):
            self.manager.load(99)

    def test_delete_slot(self) -> None:
        """删除存档后扫描应为空。"""
        self.manager.save(slot_id=1, label="待删除")
        self.manager.delete_slot(1)
        slots = self.manager.scan_slots()
        self.assertIsNone(slots[1])

    def test_get_slot_info_nonexistent(self) -> None:
        """不存在槽位的 info 应为 None。"""
        info = self.manager.get_slot_info(1)
        self.assertIsNone(info)

    def test_choice_history(self) -> None:
        """选择记录应正确追踪。"""
        self.manager.add_choice_record({"node": "start", "choice": 0})
        self.manager.add_choice_record({"node": "middle", "choice": 1})
        self.assertEqual(len(self.manager.get_choice_history()), 2)

        # 存档包含选择记录
        self.manager.save(slot_id=1, label="含选择记录")
        slot = self.manager.load(1)
        self.assertEqual(len(slot.choice_history), 2)

    def test_clear_choice_history(self) -> None:
        """清空选择记录。"""
        self.manager.add_choice_record({"node": "start", "choice": 0})
        self.manager.clear_choice_history()
        self.assertEqual(self.manager.get_choice_history(), [])

    def test_get_latest_save(self) -> None:
        """获取最近存档。"""
        self.manager.save(slot_id=1, label="存档1")
        import time
        time.sleep(0.01)
        self.manager.save(slot_id=2, label="存档2")
        latest = self.manager.get_latest_save()
        self.assertEqual(latest.label, "存档2")

    def test_get_latest_save_all_empty(self) -> None:
        """无存档时返回 None。"""
        latest = self.manager.get_latest_save()
        self.assertIsNone(latest)

    def test_save_invalid_slot_id(self) -> None:
        """超出范围的槽位应抛出异常。"""
        with self.assertRaises(SaveDataError):
            self.manager.save(slot_id=0)

        with self.assertRaises(SaveDataError):
            self.manager.save(slot_id=6)

    def test_save_creates_directory(self) -> None:
        """保存应自动创建目录。"""
        self.manager.save(slot_id=1, label="自动创建目录")
        self.assertTrue(os.path.isdir(self._save_dir))

    def test_save_with_metadata(self) -> None:
        """保存应包含额外元数据。"""
        self.manager.save(slot_id=1, label="带元数据", extra_metadata={"play_time": 3600, "version": "1.0"})
        slot = self.manager.get_slot_info(1)
        self.assertEqual(slot.metadata.get("play_time"), 3600)


if __name__ == "__main__":
    unittest.main()
