"""合并转发消息模块。

消息收集器（ForwardMessageCollector）作为插件消息发送的中间层，
将多条独立消息缓冲后通过 NapCat 的 send_forward_msg API 
以合并转发消息格式统一发送。

支持的合并转发场景：
- 对话流程中的多段文本（旁白 + 角色对话）
- 引导教程中的步骤式消息
- 状态查询中的多条结果汇总

消息格式遵循 OneBot v11 node 标准，
兼容 NapCat 的 send_group_forward_msg / send_private_forward_msg API。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib import request
from urllib.error import URLError


@dataclass
class ForwardNodeItem:
    """合并转发中的单条消息节点。

    每个节点对应一条原始消息，包含发送者身份和消息内容。
    多个节点按添加顺序组合为最终的合并转发消息。

    Attributes:
        name: 发送者显示名称（如"旁白"、"洛疏律"）。
        uin: 发送者标识（QQ 号或角色 ID 字符串）。
        content: 消息文本内容。
        timestamp: Unix 时间戳（秒），自动记录添加时间。
    """

    name: str
    uin: str
    content: str
    timestamp: int = field(default_factory=lambda: int(time.time()))

    def to_node_dict(self) -> dict[str, Any]:
        """转换为 OneBot v11 node 格式字典。

        Returns:
            符合 NapCat send_forward_msg 的 node 结构。
        """
        return {
            "type": "node",
            "data": {
                "name": self.name,
                "uin": self.uin,
                "content": self.content,
                "time": self.timestamp,
            },
        }


class ForwardMessageCollector:
    """合并转发消息收集器。

    缓冲插件的多条消息，在触发条件下通过 NapCat HTTP API
    以合并转发消息格式一次性发送。

    设计原则：
    - 按 stream_id 隔离会话缓冲，不同会话/群聊互不干扰
    - 支持手动 flush 和自动触发两种发送模式
    - 发送失败时保留缓冲区，便于重试或降级为逐条发送
    - HTTP 调用带超时和异常保护，不阻塞主流程

    Usage:
        collector = ForwardMessageCollector(
            bot_uin="10000",
            bot_name="悼溯茶馆",
            napcat_url="http://127.0.0.1:3000",
        )
        collector.add("旁白", "narrator", "窗外下起了雨...")
        collector.add("洛疏律", "luoshulv", "欢迎光临。")
        result = await collector.flush("group_123456")
    """

    # NapCat HTTP API 端点
    _SEND_GROUP_FORWARD = "/send_group_forward_msg"
    _SEND_PRIVATE_FORWARD = "/send_private_forward_msg"

    def __init__(
        self,
        bot_uin: str = "10000",
        bot_name: str = "悼溯茶馆",
        napcat_url: str = "http://127.0.0.1:3000",
        auto_flush: bool = True,
        display_title: str = "悼溯茶馆 · 消息记录",
        request_timeout: int = 10,
    ) -> None:
        """初始化合并转发消息收集器。

        Args:
            bot_uin: 机器人 QQ 号，作为默认发送者。
            bot_name: 机器人显示名称。
            napcat_url: NapCat HTTP API 地址。
            auto_flush: 是否自动合并发送（关闭则逐条发送）。
            display_title: 合并转发消息的显示标题（摘要文字）。
            request_timeout: HTTP 请求超时秒数。
        """
        self._bot_uin = bot_uin
        self._bot_name = bot_name
        self._napcat_url = napcat_url.rstrip("/")
        self._auto_flush = auto_flush
        self._display_title = display_title
        self._request_timeout = request_timeout
        self._buffers: dict[str, list[ForwardNodeItem]] = {}

    # ==================== 消息缓冲 ====================

    def add(
        self,
        stream_id: str,
        name: str,
        content: str,
        uin: str | None = None,
    ) -> None:
        """添加一条消息到指定会话的缓冲区。

        Args:
            stream_id: 消息流 ID（用于区分不同会话）。
            name: 发送者显示名称。
            content: 消息文本内容。
            uin: 发送者标识，默认使用 bot_uin。
        """
        if stream_id not in self._buffers:
            self._buffers[stream_id] = []

        self._buffers[stream_id].append(
            ForwardNodeItem(
                name=name,
                uin=uin or self._bot_uin,
                content=content,
            )
        )

    def add_bot_msg(self, stream_id: str, content: str) -> None:
        """快捷方法：添加一条机器人消息。

        Args:
            stream_id: 消息流 ID。
            content: 消息文本内容。
        """
        self.add(stream_id, self._bot_name, content, self._bot_uin)

    def clear(self, stream_id: str) -> None:
        """清空指定会话的消息缓冲区。

        Args:
            stream_id: 消息流 ID。
        """
        self._buffers.pop(stream_id, None)

    def buffer_size(self, stream_id: str) -> int:
        """获取指定会话缓冲区中的消息数量。

        Args:
            stream_id: 消息流 ID。

        Returns:
            缓冲消息数。
        """
        return len(self._buffers.get(stream_id, []))

    @property
    def total_buffered(self) -> int:
        """获取所有会话缓冲区中的消息总数。"""
        return sum(len(buf) for buf in self._buffers.values())

    # ==================== 发送逻辑 ====================

    def build_payload(self, stream_id: str) -> list[dict[str, Any]] | None:
        """构建 NapCat send_forward_msg 的 messages 数组。

        将缓冲区中的所有节点转换为 OneBot v11 node 格式列表。

        Args:
            stream_id: 消息流 ID。

        Returns:
            node 字典列表，缓冲区为空时返回 None。
        """
        buf = self._buffers.get(stream_id, [])
        if not buf:
            return None
        return [item.to_node_dict() for item in buf]

    async def flush(self, stream_id: str) -> dict[str, Any]:
        """将指定会话缓冲区的消息通过 NapCat 以合并转发格式发送。

        发送流程：
        1. 构建 OneBot node 列表
        2. 解析 stream_id 确定发送目标（群聊/私聊）
        3. 通过 NapCat HTTP API 发送
        4. 成功则清空该会话缓冲区

        Args:
            stream_id: 消息流 ID。

        Returns:
            操作结果字典，包含 success / message / nodes_count 等字段。
        """
        nodes = self.build_payload(stream_id)
        if nodes is None:
            return {"success": False, "message": "缓冲区为空，无需发送。"}

        target_type, target_id = self._parse_stream_id(stream_id)

        try:
            response = await self._call_napcat_api(
                target_type, target_id, nodes
            )
            if response.get("success"):
                self.clear(stream_id)
            return response
        except Exception as e:
            return {
                "success": False,
                "message": f"发送合并转发失败：{e}",
                "nodes_count": len(nodes),
            }

    async def send_direct(self, stream_id: str, content: str) -> None:
        """逐条发送模式：直接通过 NapCat API 发送单条消息。

        当 auto_flush 关闭时使用，每条消息立即发送而不缓冲。

        Args:
            stream_id: 消息流 ID。
            content: 消息文本内容。
        """
        target_type, target_id = self._parse_stream_id(stream_id)

        if target_type == "group":
            endpoint = f"{self._napcat_url}/send_group_msg"
            body = {"group_id": target_id, "message": content}
        else:
            endpoint = f"{self._napcat_url}/send_private_msg"
            body = {"user_id": target_id, "message": content}

        await self._http_post(endpoint, body)

    # ==================== 内部方法 ====================

    async def _call_napcat_api(
        self,
        target_type: str,
        target_id: str,
        nodes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """调用 NapCat 合并转发 API。

        Args:
            target_type: 消息类型（"group" 或 "private"）。
            target_id: 目标 ID（群号或 QQ 号）。
            nodes: OneBot v11 node 格式的消息列表。

        Returns:
            API 响应解析后的字典。
        """
        if target_type == "group":
            endpoint = f"{self._napcat_url}{self._SEND_GROUP_FORWARD}"
            body = {"group_id": target_id, "messages": nodes}
        else:
            endpoint = f"{self._napcat_url}{self._SEND_PRIVATE_FORWARD}"
            body = {"user_id": target_id, "messages": nodes}

        response = await self._http_post(endpoint, body)
        data = json.loads(response)

        if data.get("status") == "ok":
            return {
                "success": True,
                "message_id": data.get("data", {}).get("message_id"),
                "nodes_count": len(nodes),
                "message": f"已发送 {len(nodes)} 条合并转发消息。",
            }
        return {
            "success": False,
            "message": data.get("wording", "NapCat API 返回失败。"),
            "nodes_count": len(nodes),
        }

    async def _http_post(self, url: str, body: dict[str, Any]) -> str:
        """异步 HTTP POST 请求。

        使用 asyncio 在独立线程中执行同步 urllib 调用，
        避免阻塞事件循环。

        Args:
            url: 请求 URL。
            body: JSON 请求体。

        Returns:
            响应体字符串。

        Raises:
            URLError: 网络请求失败。
        """
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        def _do_request() -> str:
            with request.urlopen(req, timeout=self._request_timeout) as resp:
                return resp.read().decode("utf-8")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do_request)

    @staticmethod
    def _parse_stream_id(stream_id: str) -> tuple[str, str]:
        """从 stream_id 解析消息类型和目标 ID。

        支持格式：
        - "group_123456" → ("group", "123456")
        - "private_654321" → ("private", "654321")
        - 纯数字 → ("group", stream_id)

        Args:
            stream_id: 消息流 ID。

        Returns:
            (message_type, target_id) 元组。
        """
        if stream_id.startswith("group_"):
            return ("group", stream_id[len("group_"):])
        elif stream_id.startswith("private_"):
            return ("private", stream_id[len("private_"):])
        # 回退：假设为群聊
        return ("group", stream_id)
