"""Simple WebSocket IM server with a built-in UI page."""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiohttp import web


@dataclass
class ClientInfo:
    client_id: str
    name: str
    room: str
    role: str


class IMServer:
    def __init__(self) -> None:
        self._clients: dict[web.WebSocketResponse, ClientInfo] = {}
        self._lock = asyncio.Lock()

    async def index(self, request: web.Request) -> web.Response:
        html_path = Path(__file__).parent / "static" / "index.html"
        return web.FileResponse(path=html_path)

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)

        client_id = uuid4().hex
        await self._register(ws, ClientInfo(client_id, "guest", "lobby", "user"))

        await ws.send_json({"type": "welcome", "client_id": client_id})

        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                await self._handle_message(ws, msg.data)
            elif msg.type == web.WSMsgType.ERROR:
                break

        await self._unregister(ws)
        return ws

    async def _register(self, ws: web.WebSocketResponse, info: ClientInfo) -> None:
        async with self._lock:
            self._clients[ws] = info

    async def _unregister(self, ws: web.WebSocketResponse) -> None:
        async with self._lock:
            self._clients.pop(ws, None)

    async def _handle_message(self, ws: web.WebSocketResponse, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send_json({"type": "error", "message": "Invalid JSON"})
            return

        msg_type = data.get("type", "chat")
        if msg_type == "ping":
            await ws.send_json({"type": "pong"})
            return

        media_base64 = data.get("media_base64") or []

        if msg_type == "message":
            name = str(data.get("sender_id", "guest"))
            room = str(data.get("chat_id", "lobby"))
            role = str(data.get("role", "user"))
            content = str(data.get("content", ""))
            msg_type = "chat"
        else:
            name = str(data.get("name", "guest"))
            room = str(data.get("room", "lobby"))
            role = str(data.get("role", "user"))
            content = str(data.get("content", ""))
            media_base64 = media_base64 or data.get("images") or []

        async with self._lock:
            info = self._clients.get(ws)
            if info:
                info.name = name
                info.room = room
                info.role = role

        if msg_type != "chat":
            return

        payload = {
            "type": "chat",
            "id": info.client_id if info else "unknown",
            "name": name,
            "role": role,
            "room": room,
            "content": content,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "media_base64": media_base64,
        }

        await self._broadcast(room, payload)

    async def _broadcast(self, room: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            targets = [ws for ws, info in self._clients.items() if info.room == room]

        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                pass


def create_app() -> web.Application:
    server = IMServer()
    app = web.Application()
    app.add_routes(
        [
            web.get("/", server.index),
            web.get("/health", server.health),
            web.get("/ws", server.websocket_handler),
        ]
    )
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="0.0.0.0", port=19090)
