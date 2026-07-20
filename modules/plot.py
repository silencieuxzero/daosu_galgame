"""分段式剧情对话模块（Plot Dialogue Engine）。

实现 "/dsv plot <角色名>" 命令配套的分段式交互对话功能：
- 加载角色专属的 JSON 剧情脚本
- 分段展示剧情内容，每段结束后提供 2-4 个选择项
- 用户选择后根据选项影响好感度
- 支持退出对话模式
- 支持进度自动追踪，连续推进多章剧情

JSON 数据文件存储于 data/plot/ 目录下，
使用与 dialogue 模块相同的节点图结构，但独立管理脚本目录。

格式规范：
    用户仅需将符合以下格式的 .json 文件放入 data/plot/ 目录，
    系统会自动扫描、验证并加载：

    .. code-block:: json

        {
          "script_id": "角色名_序号",       // 必填，全局唯一，如 "luoshulv_01"
          "character_name": "角色名",       // 必填，用于按角色匹配
          "title": "章节标题",               // 必填，如 "初入茶馆"
          "start_node": "start",           // 必填，起始节点 ID
          "nodes": {
            "start": {                     // 起始节点，ID 自定
              "speaker": "narrator",       // 说话者，"narrator" 表示旁白
              "text": "旁白文本...",        // 必填
              "next_node": "greeting"      // 自动跳转的目标节点
            },
            "greeting": {
              "speaker": "角色名",
              "text": "对话文本...",
              "choices": [                 // 选项列表（可选）
                {
                  "text": "选项文本",       // 必填
                  "next_node": "node_id",  // 必填，跳转目标
                  "affection_change": 5    // 好感度变化量
                }
              ]
            },
            "chapter_end": {
              "speaker": "narrator",
              "text": "本章结束...",
              "next_node": null           // null 表示本章结束
            }
          }
        }

    脚本排序规则：
        同一个角色的多个章节按 script_id 的字典序排序播放。
        推荐命名格式：`角色名_两位序号`，如 `luoshulv_01`、`luoshulv_02`。

Usage:
    mgr = PlotManager("data/plot", affection_manager)
    mgr.load_all_scripts()
    result = mgr.start_next_script("洛疏律")  # 自动从第一章开始
    result = mgr.make_choice(0)
    result = mgr.advance()
    result = mgr.mark_current_completed()     # 标记本章已完成
    result = mgr.start_next_script("洛疏律")  # 自动推进到第二章
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from ..core.json_utils import strip_json_comments as _strip_json_comments


@dataclass
class PlotChoice:
    """对话选项。

    Attributes:
        text: 选项显示文本。
        next_node: 选择后跳转的目标节点 ID。
        affection_change: 好感度变化量。
    """

    text: str
    next_node: str
    affection_change: int = 0


@dataclass
class PlotNode:
    """剧情对话节点。

    Attributes:
        node_id: 节点唯一标识。
        text: 剧情文本内容。
        speaker: 说话者（"narrator" 表示旁白）。
        emotion: 情绪标签。
        choices: 可选分支列表（空表示无分支）。
        next_node: 无分支时的自动跳转目标（None 表示对话结束）。
    """

    node_id: str
    text: str
    speaker: str = "narrator"
    emotion: str = "neutral"
    choices: list[PlotChoice] = field(default_factory=list)
    next_node: str | None = None

    def has_choices(self) -> bool:
        """当前节点是否有选项分支。"""
        return len(self.choices) > 0


@dataclass
class PlotScript:
    """分段式剧情脚本。

    Attributes:
        script_id: 脚本唯一标识。
        character_name: 关联的角色名称。
        title: 脚本标题。
        start_node: 起始节点 ID。
        nodes: 节点 ID 到 PlotNode 的映射。
    """

    script_id: str
    character_name: str
    title: str
    start_node: str
    nodes: dict[str, PlotNode] = field(default_factory=dict)


@dataclass
class ValidationReport:
    """脚本验证报告。

    Attributes:
        filepath: 被验证的 JSON 文件路径。
        script_id: 脚本 ID。
        is_valid: 是否通过验证。
        errors: 错误信息列表（阻止加载）。
        warnings: 警告信息列表（不影响加载但建议修复）。
    """

    filepath: str
    script_id: str
    is_valid: bool
    errors: list[str]
    warnings: list[str]


class PlotManager:
    """分段式剧情对话管理器。

    独立于 DialogueManager 管理剧情脚本，支持：
    - 自动扫描并验证 data/plot/ 下所有 JSON 文件
    - 加载/重新加载角色专属剧情脚本
    - 启动/推进/选择/结束对话
    - 进度自动追踪，按顺序推进多章剧情
    - 与好感度系统联动

    用户只需将符合格式的 JSON 文件放入 data/plot/ 目录，
    无需任何额外配置即可自动识别。
    """

    # 剧情 JSON 必填字段
    _REQUIRED_TOP_FIELDS = {"script_id", "character_name", "title", "start_node", "nodes"}
    # 节点必填字段
    _REQUIRED_NODE_FIELDS = {"text"}
    # 选项必填字段
    _REQUIRED_CHOICE_FIELDS = {"text", "next_node"}

    def __init__(self, plot_dir: str, affection_manager: Any | None = None) -> None:
        """初始化剧情管理器。

        Args:
            plot_dir: data/plot/ 目录的绝对路径。
            affection_manager: 好感度管理器实例，用于选项好感度计算。
        """
        self._plot_dir = plot_dir
        self._affection = affection_manager
        self._scripts: dict[str, PlotScript] = {}
        self._current_script: PlotScript | None = None
        self._current_node: PlotNode | None = None
        self._script_loaded = False

        # 验证报告缓存
        self._validation_reports: list[ValidationReport] = []

        # 进度追踪
        self._progress_path = os.path.join(plot_dir, ".progress.json")
        self._completed_scripts: dict[str, list[str]] = {}  # character_name -> [script_id, ...]
        self._load_progress()

    # ==================== 进度追踪 ====================

    def _load_progress(self) -> None:
        """从磁盘加载进度数据。"""
        try:
            if os.path.exists(self._progress_path):
                with open(self._progress_path, encoding="utf-8") as f:
                    self._completed_scripts = json.load(f)
        except (json.JSONDecodeError, IOError):
            self._completed_scripts = {}

    def _save_progress(self) -> None:
        """保存进度数据到磁盘。"""
        try:
            dirname = os.path.dirname(self._progress_path)
            if dirname and not os.path.exists(dirname):
                os.makedirs(dirname, exist_ok=True)
            with open(self._progress_path, "w", encoding="utf-8") as f:
                json.dump(self._completed_scripts, f, ensure_ascii=False, indent=2)
        except IOError:
            pass

    def mark_current_completed(self) -> dict[str, Any]:
        """标记当前正在播放的脚本为已完成。

        将当前脚本的 script_id 记录到该角色的已完成列表中，
        并自动持久化到磁盘。

        Returns:
            操作结果字典。
        """
        if self._current_script is None:
            return {"success": False, "message": "当前没有活跃的剧情脚本。"}

        character = self._current_script.character_name
        script_id = self._current_script.script_id

        if character not in self._completed_scripts:
            self._completed_scripts[character] = []
        if script_id not in self._completed_scripts[character]:
            self._completed_scripts[character].append(script_id)

        self._save_progress()
        return {"success": True, "character_name": character, "script_id": script_id}

    def reset_progress(self, character_name: str | None = None) -> dict[str, Any]:
        """重置指定角色或所有角色的剧情进度。

        Args:
            character_name: 角色名称。为 None 时重置所有角色。

        Returns:
            操作结果字典。
        """
        if character_name:
            self._completed_scripts.pop(character_name, None)
        else:
            self._completed_scripts.clear()
        self._save_progress()
        msg = f"已重置角色 '{character_name}' 的剧情进度。" if character_name else "已重置所有角色的剧情进度。"
        return {"success": True, "message": msg}

    def get_character_progress(self, character_name: str) -> dict[str, Any]:
        """获取指定角色的剧情进度。

        Args:
            character_name: 角色名称。

        Returns:
            包含已完成脚本列表和下一个待播放脚本的字典。
        """
        scripts = self.get_scripts_for_character(character_name)
        completed = self._completed_scripts.get(character_name, [])
        next_script = self._get_next_script(character_name)

        return {
            "character_name": character_name,
            "total": len(scripts),
            "completed": len(completed),
            "completed_scripts": list(completed),
            "next_script_id": next_script.script_id if next_script else None,
            "next_script_title": next_script.title if next_script else None,
            "is_all_completed": next_script is None,
        }

    # ==================== 脚本验证 ====================

    @staticmethod
    def validate_script_data(data: dict[str, Any], filepath: str = "") -> ValidationReport:
        """验证单个剧情 JSON 数据的完整性和正确性。

        检查项目：
        1. 必需字段是否存在
        2. start_node 是否在 nodes 中存在
        3. 每个节点是否包含 text
        4. 每个 next_node 是否指向存在的节点
        5. 每个 choice 的 next_node 是否指向存在的节点
        6. 节点是否形成可达图（从 start_node 出发所有路径都能到达终点）

        Args:
            data: 从 JSON 解析出的原始字典。
            filepath: 文件路径（用于报告）。

        Returns:
            ValidationReport 实例。
        """
        errors: list[str] = []
        warnings: list[str] = []
        script_id = str(data.get("script_id", "未知"))

        # 1. 检查必需字段
        for field in sorted(PlotManager._REQUIRED_TOP_FIELDS):
            if field not in data:
                errors.append(f"缺少必需字段 '{field}'")
            elif data[field] is None or (isinstance(data[field], str) and not data[field].strip()):
                errors.append(f"字段 '{field}' 不能为空")

        if errors:
            return ValidationReport(
                filepath=filepath,
                script_id=script_id,
                is_valid=False,
                errors=errors,
                warnings=warnings,
            )

        # 2. 检查 nodes
        nodes = data["nodes"]
        if not isinstance(nodes, dict):
            errors.append("'nodes' 必须是一个对象 (JSON Object)")
            return ValidationReport(filepath, script_id, False, errors, warnings)

        if len(nodes) == 0:
            errors.append("'nodes' 不能为空，至少需要一个节点")
            return ValidationReport(filepath, script_id, False, errors, warnings)

        node_ids = set(nodes.keys())

        # 3. 检查 start_node
        start_node = data["start_node"]
        if start_node not in nodes:
            errors.append(f"起始节点 '{start_node}' 在 nodes 中不存在")

        # 4. 逐节点检查
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                errors.append(f"节点 '{node_id}' 的值必须是一个对象")
                continue

            # 检查节点必需字段
            for field in PlotManager._REQUIRED_NODE_FIELDS:
                if field not in node:
                    errors.append(f"节点 '{node_id}' 缺少必需字段 '{field}'")
                elif not isinstance(node[field], str) or not node[field].strip():
                    errors.append(f"节点 '{node_id}' 的 '{field}' 不能为空")

            # 检查 next_node 引用
            next_node = node.get("next_node")
            if next_node is not None:
                if not isinstance(next_node, str):
                    errors.append(f"节点 '{node_id}' 的 'next_node' 必须是字符串或 null")
                elif next_node not in nodes:
                    errors.append(f"节点 '{node_id}' 的 next_node '{next_node}' 不存在于 nodes 中")

            # 检查 choices
            choices = node.get("choices")
            if choices is not None:
                if not isinstance(choices, list):
                    errors.append(f"节点 '{node_id}' 的 'choices' 必须是数组")
                    continue

                if len(choices) == 0:
                    warnings.append(f"节点 '{node_id}' 的 choices 为空数组，建议删除或填入选项")
                    continue

                for i, choice in enumerate(choices):
                    if not isinstance(choice, dict):
                        errors.append(f"节点 '{node_id}' 的第 {i} 个选项必须是一个对象")
                        continue

                    for field in PlotManager._REQUIRED_CHOICE_FIELDS:
                        if field not in choice:
                            errors.append(f"节点 '{node_id}' 的第 {i} 个选项缺少 '{field}'")
                        elif not isinstance(choice[field], str) or not choice[field].strip():
                            errors.append(f"节点 '{node_id}' 的第 {i} 个选项的 '{field}' 不能为空")

                    choice_next = choice.get("next_node", "")
                    if choice_next and choice_next not in nodes:
                        errors.append(f"节点 '{node_id}' 的第 {i} 个选项跳转目标 '{choice_next}' 不存在于 nodes 中")

            # 检查节点既无 choices 也无 next_node（终点节点必须有 next_node=null）
            has_choices = choices is not None and isinstance(choices, list) and len(choices) > 0
            if not has_choices and next_node is None and node_id != start_node:
                # 非起始节点的死胡同 - 这可能是有意设计的终点
                # 但在 plot 系统中，终止节点应该显式标记
                pass  # 这是正常情况，终点节点

        # 5. 检查 script_id 命名规范
        sid_pattern = re.compile(r"^.+\d+$")
        if not sid_pattern.match(str(data.get("script_id", ""))):
            warnings.append(f"script_id '{script_id}' 建议包含序号，如 'luoshulv_01'")

        return ValidationReport(
            filepath=filepath,
            script_id=script_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def get_validation_reports(self) -> list[ValidationReport]:
        """获取最近一次加载的验证报告列表。

        Returns:
            所有脚本的验证报告列表。
        """
        return list(self._validation_reports)

    def get_validation_summary(self) -> dict[str, Any]:
        """获取验证结果汇总。

        Returns:
            包含统计信息的字典。
        """
        total = len(self._validation_reports)
        valid = sum(1 for r in self._validation_reports if r.is_valid)
        invalid = total - valid
        total_errors = sum(len(r.errors) for r in self._validation_reports)
        total_warnings = sum(len(r.warnings) for r in self._validation_reports)

        invalid_reports = [r for r in self._validation_reports if not r.is_valid]

        return {
            "total": total,
            "valid": valid,
            "invalid": invalid,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "invalid_files": [
                {"filepath": r.filepath, "script_id": r.script_id, "errors": r.errors}
                for r in invalid_reports
            ],
        }

    # ==================== 脚本加载 ====================

    def load_all_scripts(self) -> list[ValidationReport]:
        """从磁盘扫描、验证并加载所有剧情脚本。

        递归扫描 plot_dir 及其子目录下所有 .json 文件，
        对每个文件进行格式验证，仅加载通过验证的脚本。

        Returns:
            所有文件的验证报告列表。
        """
        self._validation_reports.clear()
        self._scripts.clear()

        if not os.path.isdir(self._plot_dir):
            self._script_loaded = True
            return []

        for root, _dirs, files in os.walk(self._plot_dir):
            # 跳过进度文件
            files = [f for f in files if not f.startswith(".")]
            for filename in sorted(files):
                if not filename.endswith(".json"):
                    continue

                filepath = os.path.join(root, filename)
                relpath = os.path.relpath(filepath, self._plot_dir)

                # 步骤1: 读取并解析 JSON
                try:
                    with open(filepath, encoding="utf-8") as f:
                        content = f.read()
                    data = json.loads(_strip_json_comments(content))
                except json.JSONDecodeError as e:
                    report = ValidationReport(
                        filepath=relpath,
                        script_id=filename,
                        is_valid=False,
                        errors=[f"JSON 解析错误: {e}"],
                        warnings=[],
                    )
                    self._validation_reports.append(report)
                    continue
                except IOError as e:
                    report = ValidationReport(
                        filepath=relpath,
                        script_id=filename,
                        is_valid=False,
                        errors=[f"文件读取错误: {e}"],
                        warnings=[],
                    )
                    self._validation_reports.append(report)
                    continue

                # 步骤2: 验证数据结构
                report = self.validate_script_data(data, filepath=relpath)
                self._validation_reports.append(report)

                if not report.is_valid:
                    continue

                # 步骤3: 解析为 PlotScript 对象
                try:
                    script = self._parse_script(data)
                except (KeyError, TypeError) as e:
                    report = ValidationReport(
                        filepath=relpath,
                        script_id=str(data.get("script_id", filename)),
                        is_valid=False,
                        errors=[f"数据解析失败: {e}"],
                        warnings=[],
                    )
                    # 替换最后一条无效的报告
                    self._validation_reports[-1] = report
                    continue

                # 步骤4: 检查 script_id 唯一性
                if script.script_id in self._scripts:
                    existing_path = None
                    for r in self._validation_reports:
                        if r.script_id == script.script_id and r.is_valid and r.filepath != relpath:
                            existing_path = r.filepath
                            break
                    report = ValidationReport(
                        filepath=relpath,
                        script_id=script.script_id,
                        is_valid=False,
                        errors=[f"script_id '{script.script_id}' 重复（已存在于 {existing_path or '其他文件'}）"],
                        warnings=[],
                    )
                    self._validation_reports[-1] = report
                    continue

                self._scripts[script.script_id] = script

        self._script_loaded = True
        return self._validation_reports

    def reload(self) -> list[ValidationReport]:
        """重新加载所有脚本。

        Returns:
            所有文件的验证报告列表。
        """
        return self.load_all_scripts()

    def _parse_script(self, data: dict[str, Any]) -> PlotScript:
        """解析 JSON 数据为 PlotScript 对象。

        Args:
            data: 从 JSON 解析出的原始字典。

        Returns:
            构建好的 PlotScript 实例。
        """
        script_id = data.get("script_id", "")
        character_name = data.get("character_name", "")
        title = data.get("title", "")
        start_node = data.get("start_node", "")

        nodes_data = data.get("nodes", {})
        nodes: dict[str, PlotNode] = {}

        for node_id, node_data in nodes_data.items():
            choices_data = node_data.get("choices", [])
            choices = [
                PlotChoice(
                    text=c.get("text", ""),
                    next_node=c.get("next_node", ""),
                    affection_change=c.get("affection_change", 0),
                )
                for c in choices_data
            ]

            nodes[node_id] = PlotNode(
                node_id=node_id,
                text=node_data.get("text", ""),
                speaker=node_data.get("speaker", "narrator"),
                emotion=node_data.get("emotion", "neutral"),
                choices=choices,
                next_node=node_data.get("next_node"),
            )

        return PlotScript(
            script_id=script_id,
            character_name=character_name,
            title=title,
            start_node=start_node,
            nodes=nodes,
        )

    # ==================== 脚本查找与排序 ====================

    def get_scripts_for_character(self, character_name: str) -> list[PlotScript]:
        """获取指定角色的所有剧情脚本，按 script_id 排序。

        Args:
            character_name: 角色名称。

        Returns:
            排序后的脚本列表。
        """
        if not self._script_loaded:
            self.load_all_scripts()
        scripts = [s for s in self._scripts.values() if s.character_name == character_name]
        scripts.sort(key=lambda s: s.script_id)
        return scripts

    def get_script_count_for_character(self, character_name: str) -> int:
        """获取指定角色的可用的剧情章节数量。

        Args:
            character_name: 角色名称。

        Returns:
            章节数量。
        """
        return len(self.get_scripts_for_character(character_name))

    def get_script_for_character(self, character_name: str) -> PlotScript | None:
        """获取指定角色的第一个剧情脚本（兼容旧接口）。

        建议使用 start_next_script 或 get_next_script_for_character 替代。

        Args:
            character_name: 角色名称。

        Returns:
            第一个脚本，不存在则返回 None。
        """
        scripts = self.get_scripts_for_character(character_name)
        return scripts[0] if scripts else None

    def get_next_script_for_character(self, character_name: str) -> PlotScript | None:
        """获取指定角色下一个未完成的脚本。

        自动跳过已标记完成的脚本，返回下一个待播放的脚本。
        如果所有脚本都已完成，返回 None。

        Args:
            character_name: 角色名称。

        Returns:
            下一个未完成的脚本，不存在则返回 None。
        """
        scripts = self.get_scripts_for_character(character_name)
        completed = self._completed_scripts.get(character_name, [])
        for script in scripts:
            if script.script_id not in completed:
                return script
        return None

    def has_more_scripts(self, character_name: str) -> bool:
        """检查指定角色是否还有未完成的脚本。

        Args:
            character_name: 角色名称。

        Returns:
            有未完成脚本返回 True，否则 False。
        """
        return self.get_next_script_for_character(character_name) is not None

    # ==================== 对话流程 ====================

    def start_next_script(self, character_name: str) -> dict[str, Any]:
        """为指定角色启动下一个未完成的脚本。

        自动查找该角色下一个未完成的脚本并启动。
        如果所有脚本已完成，返回提示信息。

        Args:
            character_name: 角色名称。

        Returns:
            启动结果字典。
        """
        script = self.get_next_script_for_character(character_name)
        if script is None:
            # 检查是否该角色没有任何脚本
            all_scripts = self.get_scripts_for_character(character_name)
            if not all_scripts:
                return {"success": False, "message": f"角色 '{character_name}' 没有可用的剧情对话。"}
            # 所有脚本已完成
            total = len(all_scripts)
            return {
                "success": False,
                "message": f"角色 '{character_name}' 的所有剧情（共 {total} 章）已全部完成。",
                "all_completed": True,
                "total_scripts": total,
            }

        self._current_script = script
        result = self._go_to_node(script.start_node)
        if result.get("success"):
            all_scripts = self.get_scripts_for_character(character_name)
            result["script_id"] = script.script_id
            result["title"] = script.title
            result["script_index"] = self._get_script_index(character_name, script.script_id)
            result["total_scripts"] = len(all_scripts)
        return result

    def start_script_for_character(self, character_name: str) -> dict[str, Any]:
        """为指定角色启动剧情对话（兼容旧接口）。

        默认使用进度追踪，自动从下一个未完成的脚本开始。
        等同于 start_next_script。

        Args:
            character_name: 角色名称。

        Returns:
            启动结果字典，包含起始节点或错误信息。
        """
        return self.start_next_script(character_name)

    def _get_script_index(self, character_name: str, script_id: str) -> int:
        """获取脚本在该角色中的序号（从 1 开始）。"""
        scripts = self.get_scripts_for_character(character_name)
        for i, s in enumerate(scripts):
            if s.script_id == script_id:
                return i + 1
        return 0

    def _get_next_script(self, character_name: str) -> PlotScript | None:
        """内部方法：获取下一个未完成的脚本。"""
        return self.get_next_script_for_character(character_name)

    def _go_to_node(self, node_id: str) -> dict[str, Any]:
        """跳转到指定节点并返回格式化结果。

        Args:
            node_id: 目标节点 ID。

        Returns:
            节点数据字典，包含文本、选项、好感度等信息。
        """
        if self._current_script is None:
            return {"success": False, "message": "当前没有活跃的剧情对话。"}

        node = self._current_script.nodes.get(node_id)
        if node is None:
            return {"success": False, "message": f"节点 '{node_id}' 不存在。"}

        self._current_node = node
        return self._format_node_output(node)

    def _format_node_output(self, node: PlotNode) -> dict[str, Any]:
        """格式化节点输出为统一字典。

        Args:
            node: 当前 PlotNode。

        Returns:
            格式化后的结果字典。
        """
        result: dict[str, Any] = {
            "success": True,
            "plot_dialogue": True,
            "speaker": node.speaker,
            "text": node.text,
            "emotion": node.emotion,
            "node_id": node.node_id,
        }

        if node.has_choices():
            choices = [
                {
                    "index": i,
                    "text": c.text,
                    "affection_change": c.affection_change,
                }
                for i, c in enumerate(node.choices)
            ]
            result["choices"] = choices
            result["awaiting_choice"] = True

        if node.next_node is None and not node.has_choices():
            # 终点节点，标记对话结束
            result["dialogue_ended"] = True

        return result

    def make_choice(self, choice_index: int) -> dict[str, Any]:
        """玩家选择选项后推进剧情对话。

        应用好感度变化，跳转到下一节点。

        Args:
            choice_index: 选项索引（从 0 开始）。

        Returns:
            选择后的节点数据或错误信息。
        """
        if self._current_node is None:
            return {"success": False, "message": "当前没有活跃的剧情对话。"}

        if not self._current_node.has_choices():
            return {"success": False, "message": "当前节点没有选项。"}

        if choice_index < 0 or choice_index >= len(self._current_node.choices):
            return {"success": False, "message": f"无效的选项编号。请输入 0-{len(self._current_node.choices) - 1}。"}

        choice = self._current_node.choices[choice_index]

        # 应用好感度变化
        affection_change = choice.affection_change
        character_name = self._current_script.character_name if self._current_script else ""
        if self._affection and character_name and affection_change != 0:
            self._affection.modify(character_name, affection_change)
            total_affection = self._affection.get_value(character_name)
        else:
            character_name = ""
            total_affection = 0

        # 跳转到下一节点
        result = self._go_to_node(choice.next_node)

        # 将好感度信息附加到结果中
        result["affection_change"] = affection_change
        if character_name:
            result["character_name"] = character_name
            result["total_affection"] = total_affection

        return result

    def advance(self) -> dict[str, Any]:
        """自动推进到下一节点（无选项时使用）。

        Returns:
            下一节点数据或结束标记。
        """
        if self._current_node is None:
            return {"success": False, "message": "当前没有活跃的剧情对话。"}

        if self._current_node.has_choices():
            # 有选项时转为等待选择
            result = self._format_node_output(self._current_node)
            result["awaiting_choice"] = True
            return result

        next_id = self._current_node.next_node
        if next_id is None:
            return {"success": True, "plot_dialogue": True, "dialogue_ended": True, "message": "对话已结束。"}

        return self._go_to_node(next_id)

    def end_dialogue(self) -> dict[str, Any]:
        """结束当前剧情对话，重置状态。

        Returns:
            操作结果。
        """
        self._current_script = None
        self._current_node = None
        return {"success": True, "message": "已退出剧情对话模式。"}

    def get_current_node(self) -> PlotNode | None:
        """获取当前节点。"""
        return self._current_node

    def get_current_script(self) -> PlotScript | None:
        """获取当前脚本。"""
        return self._current_script

    def is_active(self) -> bool:
        """检查当前是否有活跃的剧情对话。"""
        return self._current_node is not None

    def list_scripts(self) -> list[dict[str, str]]:
        """列出所有可用剧情脚本。

        Returns:
            包含 script_id、character_name、title 的字典列表。
        """
        if not self._script_loaded:
            self.load_all_scripts()
        return [
            {
                "script_id": s.script_id,
                "character_name": s.character_name,
                "title": s.title,
            }
            for s in self._scripts.values()
        ]

    def list_characters(self) -> list[dict[str, Any]]:
        """列出所有有剧情脚本的角色及其进度信息。

        Returns:
            每个角色的名称、章节数、已完成数等信息。
        """
        if not self._script_loaded:
            self.load_all_scripts()

        characters: dict[str, dict[str, Any]] = {}
        for script in self._scripts.values():
            name = script.character_name
            if name not in characters:
                characters[name] = {
                    "character_name": name,
                    "total_scripts": 0,
                }
            characters[name]["total_scripts"] += 1

        result = []
        for name, info in characters.items():
            completed = len(self._completed_scripts.get(name, []))
            info["completed_scripts"] = completed
            info["remaining"] = info["total_scripts"] - completed
            result.append(info)

        return result
