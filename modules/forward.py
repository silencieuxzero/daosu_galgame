"""合并转发消息服务模块。

提供 ``ForwardService`` 类，封装消息的合并转发或直接发送逻辑。
供 ``renderer.py`` 调用，实现格式与发送的耦合。

消息格式遵循 Host 侧 forward 消息段标准，由 NapCat 适配器自动转换为 OneBot v11
send_group_forward_msg / send_private_forward_msg 动作。

参考实现：
- backrooms-escape: renderer.py → BackroomsRenderer._forward_node()
- MaiBot-Napcat-Adapter: codecs/outbound/segment_encoder.py → _build_forward_nodes
"""

from __future__ import annotations

from typing import Any, Callable


class ForwardService:
    """合并转发消息服务。

    封装消息的转发/直发决策逻辑，供 renderer 使用。
    插件层（plugin.py）在初始化时传入 ``ctx.send.text`` 和 ``ctx.send.forward``
    的回调函数，renderer 层调用本服务进行消息发送。

    Usage:
        forward = ForwardService(
            send_text=ctx.send.text,
            send_forward=ctx.send.forward,
            enabled=True,
            bot_name="悼溯茶馆",
        )
        await forward.send(stream_id, "你好")
        await forward.send(stream_id, "你好",
                           nodes=[forward.build_node("你好", "系统")])
    """

    def __init__(
        self,
        send_text: Callable[..., Any],
        send_forward: Callable[..., Any],
        enabled: bool = True,
        bot_name: str = "悼溯茶馆",
        bot_user_id: str = "10000",
    ) -> None:
        """初始化 ForwardService。

        Args:
            send_text: ``ctx.send.text`` 回调。
            send_forward: ``ctx.send.forward`` 回调。
            enabled: 是否启用合并转发。关闭时回退为直接文本发送。
            bot_name: 机器人显示名称。
            bot_user_id: 机器人在转发消息节点中的用户标识。
        """
        self._send_text = send_text
        self._send_forward = send_forward
        self._enabled = enabled
        self._bot_name = bot_name
        self._bot_user_id = bot_user_id

    # ==================== 节点构建 ====================

    @staticmethod
    def build_node(
        content: str,
        user_nickname: str = "悼溯茶馆",
        user_id: str = "10000",
    ) -> dict[str, Any]:
        """构建一条 Host ``send.forward`` 兼容的转发消息节点。

        Args:
            content: 消息文本内容。
            user_nickname: 发送者显示名称。
            user_id: 发送者标识（QQ 号或角色 ID 字符串）。

        Returns:
            符合 Host forward 消息段标准的节点字典。
        """
        return {
            "user_id": user_id,
            "user_nickname": user_nickname,
            "content": [{"type": "text", "data": content}],
        }

    # ==================== 统一发送 ====================

    async def send(
        self,
        stream_id: str,
        text: str,
        *,
        nodes: list[dict[str, Any]] | None = None,
    ) -> bool:
        """统一消息发送方法。

        启用合并转发时通过 ``send_forward`` 发送；否则直接发送文本。

        Args:
            stream_id: 消息会话 ID。
            text: 消息文本（nodes 为 None 时发送此文本）。
            nodes: 转发节点列表。提供时用于 forward 模式；text 模式时将所有
                   节点内容拼接为单条消息发送。

        Returns:
            发送是否成功。
        """
        if self._enabled:
            if nodes:
                return await self._send_forward(nodes, stream_id)
            node = self.build_node(text, self._bot_name)
            return await self._send_forward([node], stream_id)
        # text 模式
        if nodes:
            combined = "\n\n══════════════════════════\n\n".join(
                n["content"][0]["data"] for n in nodes
            )
            return await self._send_text(combined, stream_id)
        return await self._send_text(text, stream_id)

    # ==================== 对话展示 ====================

    async def send_dialogue(
        self,
        stream_id: str,
        result: dict[str, Any],
        bot_name: str = "悼溯茶馆",
    ) -> None:
        """格式化对话节点数据并发送。

        根据节点类型（旁白/角色、有选项/无选项）生成不同的展示格式。
        启用合并转发时，每条消息包装为单个转发节点即时发送。

        Args:
            stream_id: 消息流 ID。
            result: renderer 返回的对话节点数据。
            bot_name: 机器人（旁白）在转发消息中的显示名称。
        """
        speaker = result.get("speaker", "")
        text = result.get("text", "")
        is_tutorial = result.get("is_tutorial", False)

        # 格式化说话者标签
        if speaker == "narrator":
            header = "📖" if not is_tutorial else "📖 新手引导"
        else:
            header = f"💬 {speaker}"

        lines = [f"{header}\n{text}"]

        choices = result.get("choices")
        if choices:
            lines.append("\n请选择：")
            for c in choices:
                lines.append(f"  /dsv choose {c['index']} — {c['text']}")
        else:
            lines.append("\n—— 输入 /dsv next 继续 ——")

        content = "\n".join(lines)
        sender = speaker if speaker != "narrator" else bot_name
        await self.send(
            stream_id, content,
            nodes=[self.build_node(content, sender, self._bot_user_id)],
        )
