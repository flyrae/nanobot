# Windows Computer-Use Skill Demo

This demo shows how to use the bundled script in dry runs.

## Examples

```pwsh
python nanobot/skills/windows-computer-use/scripts/computer_use.py open_app --app "notepad"
```

```pwsh
python nanobot/skills/windows-computer-use/scripts/computer_use.py screenshot --path "C:\\temp\\shot.png" --emit
```

Auto-send the screenshot via ws_client:

```pwsh
python nanobot/skills/windows-computer-use/scripts/computer_use.py screenshot --path "C:\\temp\\shot.png" --send --content "current screen"
```

The `--emit` flag prints a JSON payload with `media` that can be sent via the `message` tool.

## One-step send (ws_client)

```pwsh
python nanobot/skills/windows-computer-use/scripts/computer_use.py screenshot_send --path "C:\\temp\\shot.png" --content "current screen"
```

```pwsh
python nanobot/skills/windows-computer-use/scripts/computer_use.py click --x 400 --y 300 --hint "send button"
```

```pwsh
python nanobot/skills/windows-computer-use/scripts/computer_use.py point_confirm --x 400 --y 300 --hint "send button"
```

## End-to-end demo

Dry-run (no UI actions):

```pwsh
python case/windows_computer_use/e2e_demo.py
```

Execute real actions (opens Notepad):

```pwsh
python case/windows_computer_use/e2e_demo.py --execute
```

If `confirm_before_click` is enabled, the command prints a confirmation JSON (includes screen size, mouse position, and window title) and exits with code 2.
Re-run with `--confirm allow` after verifying the screenshot.

## Screenshot mode

You can force primary-screen capture by setting `screenshot_mode` to `primary` in config. Default is `all` (full desktop).

To avoid any interactive screenshot tool popups, set `screenshot_backend` to `mss` (default).
