"""Windows computer-use automation script (PowerShell + pyautogui)."""

import argparse
import base64
import ctypes
import json
import mimetypes
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "allow_apps": [],
    "confirm_before_click": False,
    "confirm_mode": "manual",
    "screenshot_dir": str(Path.home() / ".nanobot" / "screenshots"),
    "screenshot_mode": "all",
    "screenshot_backend": "mss",
    "screenshot_auto_send": False,
    "shell": "pwsh",
}


def _load_config(path: str | None) -> dict[str, Any]:
    if path:
        config_path = Path(path)
    else:
        config_path = Path.home() / ".nanobot" / "computer_use.json"

    if config_path.exists():
        try:
            return {**DEFAULT_CONFIG, **json.loads(config_path.read_text())}
        except json.JSONDecodeError:
            return DEFAULT_CONFIG.copy()

    return DEFAULT_CONFIG.copy()


def _shell_executable(preferred: str) -> str:
    if shutil.which(preferred):
        return preferred
    fallback = "powershell" if preferred == "pwsh" else "pwsh"
    if shutil.which(fallback):
        return fallback
    return preferred


def _run_powershell(command: str, shell: str) -> None:
    exe = _shell_executable(shell)
    result = subprocess.run([exe, "-NoProfile", "-Command", command])
    if result.returncode != 0:
        raise RuntimeError("PowerShell command failed")


def _ensure_allowed(app: str, allow_list: list[str]) -> None:
    if not allow_list:
        return
    app_lower = app.lower()
    if not any(item.lower() in app_lower for item in allow_list):
        raise PermissionError(f"App not allowed: {app}")


def _lazy_pyautogui():
    try:
        import pyautogui  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("pyautogui is required for this command") from exc
    return pyautogui


def _screenshot(path: Path, mode: str = "all", backend: str = "mss") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from mss import mss
        from mss.tools import to_png

        with mss() as sct:
            monitor = sct.monitors[0] if mode != "primary" else sct.monitors[1]
            image = sct.grab(monitor)
            to_png(image.rgb, image.size, output=str(path))
        return
    except Exception:
        if backend == "mss":
            raise RuntimeError("mss screenshot failed; install mss or check permissions")
        pyautogui = _lazy_pyautogui()
        pyautogui.screenshot(str(path))


def _encode_file_to_data_url(path: Path, max_bytes: int) -> str:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Screenshot not found: {path}")

    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"Screenshot too large ({size} bytes), max {max_bytes} bytes")

    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "application/octet-stream"

    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def _load_nanobot_config(path: str | None):
    try:
        from nanobot.config.loader import load_config
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("nanobot config loader not available") from exc

    config_path = Path(path) if path else None
    return load_config(config_path)


async def _send_ws_payload(url: str, payload: dict[str, Any]) -> None:
    import websockets

    async with websockets.connect(url) as ws:
        await ws.send(json.dumps(payload))


def _send_screenshot_via_ws_client(
    path: Path,
    content: str | None,
    room: str | None,
    nanobot_config: str | None,
) -> None:
    nb_config = _load_nanobot_config(nanobot_config)
    ws_cfg = nb_config.channels.ws_client

    if not ws_cfg.enabled:
        raise RuntimeError("ws_client channel is not enabled in config")

    media_url = _encode_file_to_data_url(path, ws_cfg.media_max_bytes)
    payload = {
        "type": "message",
        "sender_id": ws_cfg.bot_name,
        "chat_id": room or ws_cfg.default_room,
        "content": content or "screenshot",
        "role": "bot",
        "media_base64": [media_url],
    }

    asyncio.run(_send_ws_payload(ws_cfg.url, payload))


def _request_confirmation(x: int, y: int, hint: str | None, config: dict[str, Any]) -> None:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    screenshot_path = Path(config["screenshot_dir"]) / f"confirm_{timestamp}.png"
    _screenshot(
        screenshot_path,
        config.get("screenshot_mode", "all"),
        config.get("screenshot_backend", "mss"),
    )

    pyautogui = _lazy_pyautogui()
    screen = pyautogui.size()
    mouse_pos = pyautogui.position()

    payload = {
        "type": "confirm_click",
        "x": x,
        "y": y,
        "hint": hint,
        "screenshot": str(screenshot_path),
        "screen": {"width": screen.width, "height": screen.height},
        "mouse": {"x": mouse_pos.x, "y": mouse_pos.y},
        "window_title": _get_foreground_window_title(),
    }
    print(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(2)


def _get_foreground_window_title() -> str | None:
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd == 0:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value
    except Exception:
        return None


def cmd_open_app(args: argparse.Namespace, config: dict[str, Any]) -> None:
    _ensure_allowed(args.app, config["allow_apps"])
    _run_powershell(f"Start-Process -FilePath '{args.app}'", config["shell"])


def cmd_focus_window(args: argparse.Namespace, config: dict[str, Any]) -> None:
    title = args.title.replace("'", "''")
    command = r"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
$process = Get-Process | Where-Object { $_.MainWindowTitle -like "*{title}*" } | Select-Object -First 1
if ($null -eq $process) { throw "Window not found" }
[Win32]::SetForegroundWindow($process.MainWindowHandle) | Out-Null
""".format(title=title)
    _run_powershell(command, config["shell"])


def cmd_type_text(args: argparse.Namespace, config: dict[str, Any]) -> None:
    pyautogui = _lazy_pyautogui()
    pyautogui.typewrite(args.text, interval=args.interval)


def cmd_click(args: argparse.Namespace, config: dict[str, Any]) -> None:
    if config["confirm_before_click"] and args.confirm != "allow":
        _request_confirmation(args.x, args.y, args.hint, config)

    pyautogui = _lazy_pyautogui()
    pyautogui.click(args.x, args.y, clicks=args.clicks, interval=args.interval, button=args.button)


def cmd_point_confirm(args: argparse.Namespace, config: dict[str, Any]) -> None:
    _request_confirmation(args.x, args.y, args.hint, config)


def cmd_hotkey(args: argparse.Namespace, config: dict[str, Any]) -> None:
    pyautogui = _lazy_pyautogui()
    keys = args.keys.split("+")
    pyautogui.hotkey(*keys)


def cmd_screenshot(args: argparse.Namespace, config: dict[str, Any]) -> None:
    path = Path(args.path)
    if not path.is_absolute():
        path = Path.cwd() / path
    _screenshot(
        path,
        config.get("screenshot_mode", "all"),
        config.get("screenshot_backend", "mss"),
    )
    # Always print path so the agent loop can extract it as media
    print(str(path))
    if args.emit:
        print(json.dumps({"type": "screenshot", "path": str(path), "media": [str(path)]}, ensure_ascii=False))
    if args.send or config.get("screenshot_auto_send", False):
        _send_screenshot_via_ws_client(path, args.content, args.room, args.nanobot_config)


def cmd_screenshot_send(args: argparse.Namespace, config: dict[str, Any]) -> None:
    path = Path(args.path)
    if not path.is_absolute():
        path = Path.cwd() / path

    _screenshot(
        path,
        config.get("screenshot_mode", "all"),
        config.get("screenshot_backend", "mss"),
    )
    _send_screenshot_via_ws_client(path, args.content, args.room, args.nanobot_config)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Windows computer-use automation")
    parser.add_argument("--config", help="Path to config JSON", default=None)

    subparsers = parser.add_subparsers(dest="command", required=True)

    open_app = subparsers.add_parser("open_app")
    open_app.add_argument("--app", required=True)
    open_app.set_defaults(func=cmd_open_app)

    focus_window = subparsers.add_parser("focus_window")
    focus_window.add_argument("--title", required=True)
    focus_window.set_defaults(func=cmd_focus_window)

    type_text = subparsers.add_parser("type_text")
    type_text.add_argument("--text", required=True)
    type_text.add_argument("--interval", type=float, default=0.02)
    type_text.set_defaults(func=cmd_type_text)

    click = subparsers.add_parser("click")
    click.add_argument("--x", type=int, required=True)
    click.add_argument("--y", type=int, required=True)
    click.add_argument("--button", default="left")
    click.add_argument("--clicks", type=int, default=1)
    click.add_argument("--interval", type=float, default=0.0)
    click.add_argument("--hint", default=None)
    click.add_argument("--confirm", default=None, help="Set to 'allow' to bypass confirmation")
    click.set_defaults(func=cmd_click)

    point_confirm = subparsers.add_parser("point_confirm")
    point_confirm.add_argument("--x", type=int, required=True)
    point_confirm.add_argument("--y", type=int, required=True)
    point_confirm.add_argument("--hint", default=None)
    point_confirm.set_defaults(func=cmd_point_confirm)

    hotkey = subparsers.add_parser("hotkey")
    hotkey.add_argument("--keys", required=True, help="e.g. ctrl+s")
    hotkey.set_defaults(func=cmd_hotkey)

    screenshot = subparsers.add_parser("screenshot")
    screenshot.add_argument("--path", required=True)
    screenshot.add_argument("--emit", action="store_true", help="Print JSON with media path for channel sending")
    screenshot.add_argument("--send", action="store_true", help="Send screenshot via ws_client")
    screenshot.add_argument("--content", default=None)
    screenshot.add_argument("--room", default=None)
    screenshot.add_argument("--nanobot-config", default=None)
    screenshot.set_defaults(func=cmd_screenshot)

    screenshot_send = subparsers.add_parser("screenshot_send")
    screenshot_send.add_argument("--path", required=True)
    screenshot_send.add_argument("--content", default=None)
    screenshot_send.add_argument("--room", default=None)
    screenshot_send.add_argument("--nanobot-config", default=None)
    screenshot_send.set_defaults(func=cmd_screenshot_send)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    config = _load_config(args.config)
    args.func(args, config)


if __name__ == "__main__":
    main()
