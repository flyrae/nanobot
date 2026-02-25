"""Browser-Use agent script — run autonomous browser tasks via browser-use library.

This script provides a CLI wrapper around browser-use's Agent for complex,
multi-step browser automation tasks. It can automatically pick up LLM
configuration from nanobot's config or environment variables.

Usage:
    python nanobot/skills/browser-use/scripts/browser_agent.py run --task "your task"
    python nanobot/skills/browser-use/scripts/browser_agent.py run --task "your task" --headed
    python nanobot/skills/browser-use/scripts/browser_agent.py run --task "your task" --model "openai/gpt-4o"
    python nanobot/skills/browser-use/scripts/browser_agent.py run --task "your task" --max-steps 30
    python nanobot/skills/browser-use/scripts/browser_agent.py run --task "your task" --browser real
    python nanobot/skills/browser-use/scripts/browser_agent.py install
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _try_load_nanobot_config() -> dict[str, Any] | None:
    """Attempt to load nanobot config including browser_use settings."""
    try:
        from nanobot.config.loader import load_config

        config = load_config(None)
        bu = config.tools.browser_use
        return {
            "model": config.agents.defaults.model,
            "providers": config.providers,
            "browser_use": {
                "model": bu.model,
                "api_key": bu.api_key,
                "api_base": bu.api_base,
                "headless": bu.headless,
                "browser_mode": bu.browser_mode,
                "max_steps": bu.max_steps,
                "chrome_profile": bu.chrome_profile,
                "screenshot_dir": bu.screenshot_dir,
            },
        }
    except Exception:
        return None


def _setup_env_from_nanobot(nanobot_cfg: dict[str, Any] | None) -> None:
    """Set environment variables from nanobot config if not already set."""
    if not nanobot_cfg:
        return

    providers = nanobot_cfg.get("providers")
    if not providers:
        return

    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "groq": "GROQ_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }

    for provider_name, env_var in env_map.items():
        if os.environ.get(env_var):
            continue
        provider = getattr(providers, provider_name, None)
        if provider and provider.api_key:
            os.environ[env_var] = provider.api_key


def _resolve_model(model_override: str | None, nanobot_cfg: dict[str, Any] | None) -> str:
    """Resolve LLM model: CLI arg > config.tools.browser_use.model > config.agents.defaults.model > fallback."""
    if model_override:
        return model_override
    if nanobot_cfg:
        bu_model = nanobot_cfg.get("browser_use", {}).get("model", "")
        if bu_model:
            return bu_model
        if nanobot_cfg.get("model"):
            return nanobot_cfg["model"]
    return "openai/gpt-4o"


def _create_llm(model: str, api_key: str = "", api_base: str = ""):
    """Create an LLM instance for browser-use using its built-in Chat classes.

    browser-use ships ChatOpenAI, ChatAnthropic, ChatGoogle, ChatGroq, ChatOllama
    etc. — no extra langchain packages needed.

    Args:
        model: Model identifier (e.g. "deepseek/deepseek-chat").
        api_key: Explicit API key override from config. Empty = use env var.
        api_base: Explicit API base override from config. Empty = use default.
    """
    model_lower = model.lower()

    # Try ChatBrowserUse first (official browser-use LLM, optimized for browser tasks)
    if os.environ.get("BROWSER_USE_API_KEY"):
        try:
            from browser_use import ChatBrowserUse
            return ChatBrowserUse()
        except Exception:
            pass

    # Anthropic (Claude)
    if "anthropic/" in model_lower or "claude" in model_lower:
        from browser_use import ChatAnthropic

        clean_model = model.replace("anthropic/", "")
        kwargs: dict[str, Any] = {"model": clean_model}
        if api_key:
            kwargs["api_key"] = api_key
        return ChatAnthropic(**kwargs)

    # Google Gemini
    if "gemini" in model_lower or "google/" in model_lower:
        from browser_use import ChatGoogle

        clean_model = model.replace("gemini/", "").replace("google/", "")
        kwargs = {"model": clean_model}
        if api_key:
            kwargs["api_key"] = api_key
        return ChatGoogle(**kwargs)

    # Groq
    if "groq/" in model_lower:
        from browser_use import ChatGroq

        clean_model = model.replace("groq/", "")
        kwargs = {"model": clean_model}
        if api_key:
            kwargs["api_key"] = api_key
        return ChatGroq(**kwargs)

    # Ollama (local)
    if "ollama/" in model_lower:
        from browser_use import ChatOllama

        clean_model = model.replace("ollama/", "")
        return ChatOllama(model=clean_model)

    # All OpenAI-compatible providers: OpenAI, DeepSeek, OpenRouter, Moonshot, etc.
    # browser_use.ChatOpenAI wraps the OpenAI SDK directly
    from browser_use import ChatOpenAI

    # Determine model name and default base_url for known providers
    provider_defaults: dict[str, str] = {
        "deepseek": "https://api.deepseek.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "moonshot": "https://api.moonshot.cn/v1",
        "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }

    clean_model = model
    resolved_base = api_base
    for prefix, default_base in provider_defaults.items():
        if prefix in model_lower:
            clean_model = model.replace(f"{prefix}/", "")
            if not resolved_base:
                resolved_base = default_base
            break
    else:
        # Plain openai/ prefix
        clean_model = model.replace("openai/", "")

    kwargs = {"model": clean_model}
    if api_key:
        kwargs["api_key"] = api_key
    if resolved_base:
        kwargs["base_url"] = resolved_base
    return ChatOpenAI(**kwargs)


async def _run_agent(
    task: str,
    model: str,
    api_key: str = "",
    api_base: str = "",
    headed: bool = False,
    browser_mode: str = "chromium",
    max_steps: int = 20,
    save_screenshot: str | None = None,
) -> dict[str, Any]:
    """Run a browser-use agent with the given task."""
    from browser_use import Agent, Browser, BrowserConfig

    # Configure browser
    browser_config_kwargs: dict[str, Any] = {}

    if browser_mode == "real":
        browser_config_kwargs["chrome_instance_path"] = _find_chrome_path()
    elif browser_mode == "remote":
        pass  # handled by browser-use with BROWSER_USE_API_KEY

    browser_config_kwargs["headless"] = not headed

    browser_config = BrowserConfig(**browser_config_kwargs)
    browser = Browser(config=browser_config)

    # Create LLM
    llm = _create_llm(model, api_key=api_key, api_base=api_base)

    # Create and run agent
    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        max_actions_per_step=5,
    )

    print(f"🌐 Starting browser-use agent...")
    print(f"   Task: {task}")
    print(f"   Model: {model}")
    print(f"   Browser: {browser_mode} ({'headed' if headed else 'headless'})")
    print(f"   Max steps: {max_steps}")
    print()

    try:
        history = await agent.run(max_steps=max_steps)

        result = {
            "success": not history.has_errors(),
            "task": task,
            "steps": len(history.action_results()),
            "final_url": history.final_url() if hasattr(history, "final_url") else None,
        }

        # Extract result if available
        if history.final_result():
            result["result"] = history.final_result()
            print(f"\n✅ Task completed!")
            print(f"   Result: {history.final_result()}")
        else:
            print(f"\n✅ Task completed in {result['steps']} steps.")

        # Take final screenshot if requested
        if save_screenshot:
            try:
                page = await browser.get_current_page()
                screenshot_path = Path(save_screenshot)
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(screenshot_path))
                result["screenshot"] = str(screenshot_path)
                print(f"   Screenshot: {screenshot_path}")
            except Exception as e:
                print(f"   ⚠️ Screenshot failed: {e}")

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    except Exception as e:
        error_result = {"success": False, "task": task, "error": str(e)}
        print(f"\n❌ Task failed: {e}")
        print(json.dumps(error_result, ensure_ascii=False, indent=2))
        return error_result

    finally:
        await browser.close()


def _find_chrome_path() -> str | None:
    """Find Chrome/Chromium executable path on Windows."""
    common_paths = [
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for p in common_paths:
        if p.exists():
            return str(p)
    return None


def cmd_run(args: argparse.Namespace) -> None:
    """Run a browser-use agent task."""
    nanobot_cfg = _try_load_nanobot_config()
    _setup_env_from_nanobot(nanobot_cfg)

    # Merge: CLI args override config file values
    bu_cfg = (nanobot_cfg or {}).get("browser_use", {})

    model = _resolve_model(args.model, nanobot_cfg)
    api_key = bu_cfg.get("api_key", "")
    api_base = bu_cfg.get("api_base", "")
    headless = bu_cfg.get("headless", True)
    browser_mode = bu_cfg.get("browser_mode", "chromium")
    max_steps = bu_cfg.get("max_steps", 20)
    screenshot_dir = bu_cfg.get("screenshot_dir", "")

    # CLI args take priority over config
    if args.headed:
        headless = False
    if args.browser != "chromium":  # only override if user explicitly changed it
        browser_mode = args.browser
    if args.max_steps != 20:  # only override if user explicitly changed it
        max_steps = args.max_steps

    # Resolve screenshot path
    save_screenshot = args.screenshot
    if not save_screenshot and screenshot_dir:
        save_screenshot = None  # agent-mode screenshots go to screenshot_dir when requested

    result = asyncio.run(
        _run_agent(
            task=args.task,
            model=model,
            api_key=api_key,
            api_base=api_base,
            headed=not headless,
            browser_mode=browser_mode,
            max_steps=max_steps,
            save_screenshot=save_screenshot,
        )
    )

    if not result.get("success"):
        sys.exit(1)


def _find_bundled_browsers() -> str | None:
    """Return the path to bundled ms-playwright browsers if they exist."""
    frozen = getattr(sys, 'frozen', False)
    if not frozen:
        return None
    base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    browsers = os.path.join(base, 'ms-playwright')
    # Check that at least one chromium-* directory exists
    if os.path.isdir(browsers):
        for entry in os.listdir(browsers):
            if entry.startswith('chromium-'):
                return browsers
    return None


def cmd_install(args: argparse.Namespace) -> None:
    """Install browser-use dependencies (Chromium browser)."""
    frozen = getattr(sys, 'frozen', False)

    # Check if Chromium is already bundled inside the exe
    bundled = _find_bundled_browsers()
    if bundled:
        print("✅ Chromium browser is already bundled in this executable.")
        print(f"   Browsers path: {bundled}")
        for entry in sorted(os.listdir(bundled)):
            full = os.path.join(bundled, entry)
            if os.path.isdir(full):
                print(f"   📂 {entry}")
        print("\n   No additional installation needed.")
        return

    if not frozen:
        # Normal Python environment: install packages via pip
        print("📦 Installing browser-use and dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "browser-use"],
            check=True,
        )

    # Install Chromium via playwright
    print("\n🌐 Installing Chromium browser...")
    if frozen:
        # PyInstaller bundle without bundled browsers: use playwright's node + cli.js
        try:
            from playwright._impl._driver import compute_driver_executable
            node_exe, cli_js = compute_driver_executable()
            subprocess.run([node_exe, cli_js, "install", "chromium"], check=True)
        except ImportError:
            subprocess.run(["playwright", "install", "chromium"], check=True)
    else:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )

    print("\n✅ Installation complete!")
    print("   You can now use: browser-use open https://example.com")
    print("   Or run agent: python nanobot/skills/browser-use/scripts/browser_agent.py run --task 'your task'")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Browser-Use agent for nanobot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run an autonomous browser agent task")
    run_parser.add_argument("--task", required=True, help="Natural language task description")
    run_parser.add_argument("--model", default=None, help="LLM model to use (e.g. anthropic/claude-sonnet-4-20250514)")
    run_parser.add_argument("--headed", action="store_true", help="Show browser window")
    run_parser.add_argument("--browser", default="chromium", choices=["chromium", "real", "remote"],
                            help="Browser mode: chromium (default), real (your Chrome), remote (cloud)")
    run_parser.add_argument("--max-steps", type=int, default=20, help="Maximum agent steps (default: 20)")
    run_parser.add_argument("--screenshot", default=None, help="Save final screenshot to path")
    run_parser.set_defaults(func=cmd_run)

    # install command
    install_parser = subparsers.add_parser("install", help="Install browser-use dependencies")
    install_parser.set_defaults(func=cmd_install)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
