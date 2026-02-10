"""Deprecated websocket server channel (no longer used)."""

from nanobot.channels.base import BaseChannel


class WebSocketChannel(BaseChannel):
    """Deprecated: Nanobot no longer runs as a WebSocket server."""

    name = "websocket"

    async def start(self) -> None:
        raise RuntimeError("WebSocket server channel is deprecated; use ws_client")

    async def stop(self) -> None:
        return

    async def send(self, msg):  # type: ignore[override]
        return
