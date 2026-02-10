"""WebSocket client channel for connecting to an external IM server."""

import asyncio
import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import WsClientConfig


class WsClientChannel(BaseChannel):
    """Connect to a remote WebSocket IM server and bridge messages."""

    name = "ws_client"

    def __init__(self, config: WsClientConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: WsClientConfig = config
        self._ws = None
        self._connected = False

    async def start(self) -> None:
        """Start the WebSocket client connection."""
        import websockets

        self._running = True
        while self._running:
            try:
                logger.info(f"Connecting to IM server at {self.config.url}...")
                async with websockets.connect(self.config.url) as ws:
                    self._ws = ws
                    self._connected = True
                    logger.info("Connected to IM server")

                    async for message in ws:
                        await self._handle_server_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                self._ws = None
                logger.warning(f"IM server connection error: {e}")

                if self._running:
                    await asyncio.sleep(self.config.reconnect_interval)

    async def stop(self) -> None:
        """Stop the WebSocket client."""
        self._running = False
        self._connected = False

        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message to the IM server."""
        if not self._ws or not self._connected:
            logger.warning("IM server not connected, cannot send message")
            return

        logger.debug(f"ws_client.send: content={msg.content!r}, media={msg.media}")
        media_base64 = self._encode_media(msg.media)
        logger.info(f"ws_client.send: media_base64 count={len(media_base64)}, media input count={len(msg.media) if msg.media else 0}")
        payload = {
            "type": "message",
            "sender_id": self.config.bot_name,
            "chat_id": msg.chat_id,
            "content": msg.content,
            "role": "bot",
            "metadata": msg.metadata,
            "media_base64": media_base64,
        }

        try:
            await self._ws.send(json.dumps(payload))
        except Exception as e:
            logger.error(f"Error sending IM message: {e}")

    def _encode_media(self, media: list[str]) -> list[str]:
        if not media:
            logger.debug("_encode_media: no media items")
            return []
        if not self.config.send_media_base64:
            logger.debug("_encode_media: send_media_base64 is disabled")
            return []

        logger.info(f"_encode_media: processing {len(media)} items: {media}")
        encoded: list[str] = []
        for item in media:
            if item.startswith("data:"):
                encoded.append(item)
                logger.debug(f"_encode_media: item is already data-url, length={len(item)}")
                continue

            path = Path(item)
            if not path.exists():
                logger.warning(f"_encode_media: file does not exist: {path}")
                continue
            if not path.is_file():
                logger.warning(f"_encode_media: not a file: {path}")
                continue

            file_size = path.stat().st_size
            if file_size > self.config.media_max_bytes:
                logger.warning(
                    f"_encode_media: file too large: {path} "
                    f"({file_size} bytes > {self.config.media_max_bytes} limit)"
                )
                continue

            mime, _ = mimetypes.guess_type(path.name)
            if not mime:
                mime = "application/octet-stream"

            data = base64.b64encode(path.read_bytes()).decode("utf-8")
            encoded.append(f"data:{mime};base64,{data}")
            logger.info(f"_encode_media: encoded {path} ({file_size} bytes, {mime})")

        return encoded

    async def _handle_server_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from IM server: {raw[:100]}")
            return

        msg_type = data.get("type")
        if msg_type in ("welcome", "pong"):
            return

        if msg_type != "chat":
            return

        name = str(data.get("name", ""))
        role = str(data.get("role", ""))
        room = str(data.get("room", ""))
        content = str(data.get("content", ""))

        if self.config.ignore_self and role == "bot" and name == self.config.bot_name:
            return

        await self._handle_message(
            sender_id=name or "unknown",
            chat_id=room or self.config.default_room,
            content=content,
            metadata={
                "role": role,
                "server_id": data.get("id"),
                "timestamp": data.get("timestamp"),
            },
        )
