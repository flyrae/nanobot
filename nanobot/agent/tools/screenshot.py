"""Screenshot tool for capturing and sending images via channels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Awaitable

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage

from loguru import logger


@dataclass
class ScreenshotConfig:
    default_dir: Path
    mode: str = "all"  # all | primary
    backend: str = "mss"  # mss | pyautogui


class ScreenshotTool(Tool):
    """Capture a screenshot and send it via the message bus."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
        config: ScreenshotConfig | None = None,
    ):
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id
        self._config = config or ScreenshotConfig(default_dir=Path.cwd() / "screenshots")

    def set_context(self, channel: str, chat_id: str) -> None:
        self._default_channel = channel
        self._default_chat_id = chat_id

    @property
    def name(self) -> str:
        return "screenshot"

    @property
    def description(self) -> str:
        return "Capture a screenshot and send it to the current channel."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Optional: file path to save screenshot"
                },
                "content": {
                    "type": "string",
                    "description": "Optional: message text to send with screenshot"
                },
                "send": {
                    "type": "boolean",
                    "description": "Whether to send via channel (default true)"
                },
                "mode": {
                    "type": "string",
                    "description": "Screenshot mode: all or primary"
                },
                "backend": {
                    "type": "string",
                    "description": "Screenshot backend: mss or pyautogui"
                },
            },
            "required": []
        }

    async def execute(
        self,
        path: str | None = None,
        content: str | None = None,
        send: bool | None = True,
        mode: str | None = None,
        backend: str | None = None,
        **kwargs: Any,
    ) -> str:
        channel = self._default_channel
        chat_id = self._default_chat_id

        if send and (not channel or not chat_id):
            return "Error: No target channel/chat specified"

        if send and not self._send_callback:
            return "Error: Message sending not configured"

        target_path = self._resolve_path(path)
        self._capture(target_path, mode or self._config.mode, backend or self._config.backend)

        if send:
            msg = OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=content or "screenshot",
                media=[str(target_path)],
            )
            logger.info(f"ScreenshotTool: sending media={msg.media} to {channel}:{chat_id}")
            await self._send_callback(msg)
            return f"Screenshot captured and sent: {target_path}"

        return f"Screenshot captured: {target_path}"

    def _resolve_path(self, path: str | None) -> Path:
        if path:
            target = Path(path)
            if not target.is_absolute():
                target = Path.cwd() / target
            target.parent.mkdir(parents=True, exist_ok=True)
            return target

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        target = self._config.default_dir / f"screen_{timestamp}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _capture(self, path: Path, mode: str, backend: str) -> None:
        if backend not in ("mss", "pyautogui"):
            raise RuntimeError("Invalid backend; use mss or pyautogui")

        if backend == "mss":
            try:
                from mss import mss
                from mss.tools import to_png

                with mss() as sct:
                    monitor = sct.monitors[0] if mode != "primary" else sct.monitors[1]
                    image = sct.grab(monitor)
                    to_png(image.rgb, image.size, output=str(path))
                return
            except Exception as exc:
                raise RuntimeError("mss screenshot failed; install mss or check permissions") from exc

        import pyautogui  # type: ignore

        pyautogui.screenshot(str(path))
