from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "nanobot" / "skills" / "windows-computer-use" / "scripts" / "computer_use.py"
    spec = importlib.util.spec_from_file_location("computer_use", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_load_config_merges_overrides(tmp_path: Path) -> None:
    module = _load_module()
    config_path = tmp_path / "computer_use.json"
    config_path.write_text(json.dumps({"confirm_before_click": True, "shell": "powershell"}))

    config = module._load_config(str(config_path))

    assert config["confirm_before_click"] is True
    assert config["shell"] == "powershell"
    assert "screenshot_dir" in config


def test_ensure_allowed_blocks_unknown() -> None:
    module = _load_module()
    with pytest.raises(PermissionError):
        module._ensure_allowed("calc.exe", ["notepad"])


def test_ensure_allowed_allows_match() -> None:
    module = _load_module()
    module._ensure_allowed("C:/Windows/System32/notepad.exe", ["notepad"])


def test_request_confirmation_payload(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    module = _load_module()

    class DummyPyAutoGUI:
        def size(self):
            return type("Size", (), {"width": 1920, "height": 1080})()

        def position(self):
            return type("Point", (), {"x": 100, "y": 200})()

    monkeypatch.setattr(module, "_lazy_pyautogui", lambda: DummyPyAutoGUI())
    monkeypatch.setattr(module, "_screenshot", lambda path, mode=None, backend=None: None)
    monkeypatch.setattr(module, "_get_foreground_window_title", lambda: "Notepad")

    config = {"screenshot_dir": str(Path.cwd())}

    with pytest.raises(SystemExit) as exc_info:
        module._request_confirmation(10, 20, "ok", config)

    assert exc_info.value.code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["x"] == 10
    assert payload["y"] == 20
    assert payload["hint"] == "ok"
    assert payload["screen"]["width"] == 1920
    assert payload["mouse"]["x"] == 100
    assert payload["window_title"] == "Notepad"


def test_cmd_click_requires_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    called = {"confirm": False}

    def fake_confirm(x, y, hint, config):
        called["confirm"] = True
        raise SystemExit(2)

    monkeypatch.setattr(module, "_request_confirmation", fake_confirm)
    args = type("Args", (), {"x": 1, "y": 2, "hint": None, "confirm": None, "clicks": 1, "interval": 0.0, "button": "left"})()
    with pytest.raises(SystemExit):
        module.cmd_click(args, {"confirm_before_click": True})
    assert called["confirm"] is True


def test_cmd_click_allow_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls = {}

    class DummyPyAutoGUI:
        def click(self, x, y, clicks, interval, button):
            calls["args"] = (x, y, clicks, interval, button)

    monkeypatch.setattr(module, "_lazy_pyautogui", lambda: DummyPyAutoGUI())
    args = type("Args", (), {"x": 9, "y": 8, "hint": None, "confirm": "allow", "clicks": 2, "interval": 0.1, "button": "left"})()
    module.cmd_click(args, {"confirm_before_click": True})
    assert calls["args"] == (9, 8, 2, 0.1, "left")


def test_cmd_point_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    called = {"confirm": False}

    def fake_confirm(x, y, hint, config):
        called["confirm"] = True
        raise SystemExit(2)

    monkeypatch.setattr(module, "_request_confirmation", fake_confirm)
    args = type("Args", (), {"x": 1, "y": 2, "hint": "here"})()

    with pytest.raises(SystemExit):
        module.cmd_point_confirm(args, {"confirm_before_click": True})

    assert called["confirm"] is True
