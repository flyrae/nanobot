import pytest

from nanobot.agent.tools.message import MessageTool
from nanobot.bus.events import OutboundMessage


@pytest.mark.asyncio
async def test_message_tool_supports_media() -> None:
    captured = {}

    async def send_callback(msg: OutboundMessage) -> None:
        captured["msg"] = msg

    tool = MessageTool(send_callback=send_callback, default_channel="ws", default_chat_id="room")
    result = await tool.execute(content="hi", media=["C:/temp/shot.png"])

    assert "Message sent" in result
    assert captured["msg"].media == ["C:/temp/shot.png"]
