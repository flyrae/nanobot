import pytest

from nanobot.agent.tools.screenshot import ScreenshotTool, ScreenshotConfig
from nanobot.bus.events import OutboundMessage


@pytest.mark.asyncio
async def test_screenshot_tool_sends_media(tmp_path):
    captured = {}

    async def send_callback(msg: OutboundMessage) -> None:
        captured["msg"] = msg

    tool = ScreenshotTool(
        send_callback=send_callback,
        default_channel="ws",
        default_chat_id="room",
        config=ScreenshotConfig(default_dir=tmp_path),
    )

    tool._capture = lambda path, mode, backend: path.write_text("ok")  # type: ignore

    result = await tool.execute(send=True, content="screen")

    assert "Screenshot captured and sent" in result
    assert captured["msg"].media