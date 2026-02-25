---
name: windows-computer-use
description: "Desktop / native-app automation ONLY — launch apps, focus windows, click screen coordinates, type text, send hotkeys, and take full desktop screenshots via PowerShell + pyautogui. Use ONLY for Windows desktop apps and OS-level tasks. For web-page automation (URLs, forms, DOM), use browser-use instead."
metadata: {"nanobot":{"emoji":"🖥️","requires":{"bins":["powershell","pwsh"]}}}
---

# Windows Computer-Use Skill

Use this skill to automate **Windows desktop GUI tasks** with safety checks. It combines:
- **PowerShell** for app launching and window focus
- **pyautogui** for mouse/keyboard/screenshot

> ⚠️ **This skill is for desktop applications and OS-level tasks ONLY.** For web-page
> automation (navigating URLs, filling forms, clicking DOM elements), use the
> **browser-use** skill instead. Do NOT use this skill to interact with web content.

## How to run

Use the bundled script:

```
python nanobot/skills/windows-computer-use/scripts/computer_use.py <command> [options]
```

## Commands

### `open_app`
Launch an application by name or path.

```
python nanobot/skills/windows-computer-use/scripts/computer_use.py open_app --app "notepad"
```

### `focus_window`
Bring a window to the foreground by title substring.

```
python nanobot/skills/windows-computer-use/scripts/computer_use.py focus_window --title "Notepad"
```

### `type_text`
Type text into the active window.

```
python nanobot/skills/windows-computer-use/scripts/computer_use.py type_text --text "hello"
```

### `click`
Click a screen coordinate.

```
python nanobot/skills/windows-computer-use/scripts/computer_use.py click --x 400 --y 300 --hint "send button"
```

### `hotkey`
Send hotkeys (e.g. Ctrl+S).

```
python nanobot/skills/windows-computer-use/scripts/computer_use.py hotkey --keys ctrl+s
```

### `point_confirm`
Only capture screenshot + emit confirmation JSON for a coordinate.

```
python nanobot/skills/windows-computer-use/scripts/computer_use.py point_confirm --x 400 --y 300 --hint "send button"
```

### `screenshot`
Save a screenshot and send it to the user. The file path is printed to stdout, and the
agent loop will **automatically** attach the image to the outbound message so the user
sees it in the chat as an inline image.

```
python nanobot/skills/windows-computer-use/scripts/computer_use.py screenshot --path "C:\\temp\\shot.png"
```

> **Tip:** You do NOT need any extra flags. Just run the command above and the image
> will be delivered to the user automatically.

## Confirmation flow (LLM-friendly)

If `confirm_before_click` is enabled in config, `click` will:
1. Capture a screenshot
2. Print a JSON confirmation request (includes screen size, mouse position, and window title)
3. Exit with non-zero code unless `--confirm allow` is provided

The agent should:
- Read the screenshot
- Decide if the coordinates are correct
- Re-run with `--confirm allow`

## Config

Default config path:
- `%USERPROFILE%\\.nanobot\\computer_use.json`

Supported fields:
- `allow_apps`: list of allowed app names/paths
- `confirm_before_click`: true/false
- `confirm_mode`: `manual` or `llm`
- `screenshot_dir`: directory for screenshots
- `screenshot_mode`: `all` or `primary`
- `screenshot_backend`: `mss` (recommended) or `pyautogui`
- `screenshot_auto_send`: `true` to send screenshots via ws_client automatically
- `shell`: `pwsh` or `powershell`

Example config:

```json
{
  "allow_apps": ["notepad", "calc"],
  "confirm_before_click": true,
  "confirm_mode": "llm",
  "screenshot_dir": "C:\\temp",
  "screenshot_mode": "all",
  "screenshot_backend": "mss",
  "screenshot_auto_send": true,
  "shell": "pwsh"
}
```

If you send screenshots via the `ws_client` channel, enable base64:

```json
{
  "channels": {
    "wsClient": {
      "sendMediaBase64": true,
      "mediaMaxBytes": 2097152
    }
  }
}
```
