"""自由聊天模式模块（Say Chat Engine）。

实现 "/dsv chat <角色名>" 命令配套的 LLM 自由对话功能：
- 加载角色 prompt 作为 LLM system prompt
- 维护对话历史，实现上下文连续的对话体验
- 支持用户指定替代模型（默认使用 replyer）
- 完整的进入/退出反馈

Usage:
    mgr = SayChatManager(character_manager, affection_manager)
    mgr.start_chat("洛疏律", model="replyer")
    mgr.add_user_message("你好呀")
    reply = mgr.generate_reply(llm_callback)
    mgr.end_chat()
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable


# 对话历史条目的类型别名
MessageDict = dict[str, str]


class SayChatManager:
    """自由聊天模式管理器。

    管理当前聊天的角色、对话历史和模型选择。
    不直接持有 LLM，通过回调函数实现生成，避免对 ctx 的强依赖。

    Attributes:
        _character_name: 当前聊天的角色名称。
        _character_prompt: 角色 prompt 文本。
        _model_name: 当前使用的 LLM 模型名称。
        _history: 对话历史列表，每项为 {"role": ..., "content": ...}。
        _active: 是否处于活跃聊天状态。
    """

    # 对话历史最大条目数（超过时裁剪最早的非 system 条目）
    MAX_HISTORY_LENGTH = 20
    # LLM 生成超时时间（秒），超时后返回超时错误
    LLM_TIMEOUT = 30

    def __init__(
        self,
        character_mgr: Any,
        affection_mgr: Any | None = None,
    ) -> None:
        """初始化聊天管理器。

        Args:
            character_mgr: CharacterManager 实例，用于加载角色 prompt。
            affection_mgr: 可选，AffectionManager 实例，用于在聊天中获取好感度信息。
        """
        self._character_mgr = character_mgr
        self._affection_mgr = affection_mgr
        self._character_name: str = ""
        self._character_prompt: str = ""
        self._model_name: str = "replyer"
        self._history: list[MessageDict] = []
        self._active = False

    @property
    def is_active(self) -> bool:
        """当前是否处于活跃聊天状态。"""
        return self._active

    @property
    def character_name(self) -> str:
        """当前聊天的角色名称。"""
        return self._character_name

    @property
    def model_name(self) -> str:
        """当前使用的 LLM 模型名称。"""
        return self._model_name

    @property
    def history(self) -> list[MessageDict]:
        """获取对话历史（只读副本）。"""
        return list(self._history)

    def start_chat(self, character_name: str, model: str = "replyer") -> dict[str, Any]:
        """开始与指定角色的自由聊天。

        加载角色 prompt，构建 system 消息，
        如果存在好感度管理器，在 prompt 中附加好感度信息。

        Args:
            character_name: 角色名称。
            model: LLM 模型名称，默认 "replyer"。

        Returns:
            启动结果字典，包含成功标记、角色名、prompt 摘要等信息。

        Raises:
            ValueError: 角色不存在时抛出。
        """
        try:
            char_data = self._character_mgr.get_character(character_name)
        except Exception as e:
            return {"success": False, "message": str(e)}

        self._character_name = character_name
        self._character_prompt = char_data.get_full_prompt()
        self._model_name = model or "replyer"
        self._history = []
        self._active = True

        # 构建 system prompt：角色设定 + 好感度信息
        system_prompt = self._character_prompt

        if self._affection_mgr:
            try:
                value = self._affection_mgr.get_value(character_name)
                level = self._affection_mgr.get_level(character_name)
                system_prompt += (
                    f"\n\n当前玩家与你的好感度：{value}（{level}）\n"
                    f"请根据这个好感度水平自然地回应玩家。"
                )
            except Exception:
                pass

        self._history.append({"role": "system", "content": system_prompt})

        return {
            "success": True,
            "character_name": character_name,
            "model": self._model_name,
            "message": f"已进入与 {character_name} 的自由聊天模式。",
        }

    def add_user_message(self, content: str) -> None:
        """添加用户消息到对话历史。

        Args:
            content: 用户消息文本。
        """
        self._history.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        """添加助手（角色）回复到对话历史。

        添加后自动裁剪历史，确保不超过 MAX_HISTORY_LENGTH（保留 system 消息）。

        Args:
            content: 角色回复文本。
        """
        self._history.append({"role": "assistant", "content": content})
        self._trim_history()

    def _trim_history(self) -> None:
        """裁剪对话历史。

        保留 system 消息，然后按时间顺序保留最近的 N-1 条消息
        （使得总条数不超过 MAX_HISTORY_LENGTH）。
        """
        if len(self._history) <= self.MAX_HISTORY_LENGTH:
            return

        # 保留第一条（system）和最近的 MAX_HISTORY_LENGTH - 1 条
        system = self._history[:1]
        recent = self._history[1:]
        self._history = system + recent[-(self.MAX_HISTORY_LENGTH - 1):]

    async def generate_reply(
        self,
        llm_generate: Callable[..., Any],
        user_input: str = "",
    ) -> dict[str, Any]:
        """调用 LLM 生成角色回复。

        使用已设置好的对话历史 + 用户最新输入调用 LLM，
        自动将用户输入和助手回复存入历史。

        Args:
            llm_generate: 异步函数，签名同 self.ctx.llm.generate()。
                         接受 prompt 和 model 参数。
            user_input: 用户最新输入。如果为空则仅使用历史（用于开场白生成）。

        Returns:
            包含生成结果和角色回复的字典。
        """
        if not self._active:
            return {"success": False, "message": "当前没有活跃的聊天会话。"}

        # 构建 messages
        messages = list(self._history)

        # 添加用户输入
        prompt_text = user_input.strip()
        if prompt_text:
            # 先在历史中添加用户消息（内部分历史不重复添加）
            self.add_user_message(prompt_text)

        try:
            result = await asyncio.wait_for(
                llm_generate(prompt=messages, model=self._model_name),
                timeout=self.LLM_TIMEOUT,
            )
            if result.get("success"):
                reply = result.get("response", "").strip()
                if reply:
                    self.add_assistant_message(reply)
                    return {
                        "success": True,
                        "reply": reply,
                        "character_name": self._character_name,
                    }
                return {"success": False, "message": "LLM 返回了空回复。"}
            return {"success": False, "message": f"LLM 生成失败：{result}"}
        except Exception as e:
            return {"success": False, "message": f"LLM 调用异常：{e}"}

    def end_chat(self) -> dict[str, Any]:
        """结束当前聊天会话。

        Returns:
            结束结果字典。
        """
        self._character_name = ""
        self._character_prompt = ""
        self._model_name = "replyer"
        self._history = []
        self._active = False
        return {"success": True, "message": "已退出自由聊天模式。"}

    def get_status_text(self) -> str:
        """获取当前聊天状态的格式化文本。

        Returns:
            状态描述文本，如 "💬 正在与 洛疏律 聊天（模型：replyer）"。
        """
        if not self._active:
            return "当前未处于聊天模式。"
        return f"💬 正在与 {self._character_name} 聊天（模型：{self._model_name}）"
