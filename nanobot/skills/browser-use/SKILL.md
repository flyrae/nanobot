---
name: browser-use
description: "Web-page automation ONLY — navigate URLs, fill forms, click DOM elements, extract web content, and take in-browser screenshots using a headless Chromium session. Use ONLY for tasks involving websites/URLs. For desktop apps or OS-level automation, use windows-computer-use instead."
metadata: {"nanobot":{"emoji":"🌐","requires":{"bins":["browser-use"]}}}
---

# Browser-Use Skill

Automate **web pages** using the `browser-use` CLI. The CLI maintains persistent browser sessions across commands, enabling fast multi-step web workflows.

> ⚠️ **This skill is for web-page interactions ONLY.** For desktop apps, native Windows
> programs, or full-screen screenshots, use the **windows-computer-use** skill instead.
> Do NOT use this skill for anything outside a browser.

## Core Workflow

1. **Navigate**: `browser-use open <url>`
2. **Inspect**: `browser-use state` — returns clickable elements with indices
3. **Interact**: Use indices to click/type (`browser-use click 5`, `browser-use input 3 "text"`)
4. **Verify**: `browser-use state` or `browser-use screenshot` to confirm
5. **Repeat**: Browser stays open between commands
6. **Close**: `browser-use close` when done

## Browser Modes

```bash
browser-use open <url>                         # Default: headless Chromium
browser-use --headed open <url>                # Visible Chromium window
browser-use --browser real open <url>          # User's Chrome with login sessions
browser-use --browser remote open <url>        # Cloud browser (requires API key)
```

- **chromium** (default): Fast, isolated, headless
- **real**: Uses the user's Chrome with cookies, extensions, and logged-in sessions
- **remote**: Cloud-hosted browser with proxy support (requires BROWSER_USE_API_KEY)

## Commands

### Navigation

```bash
browser-use open <url>          # Navigate to URL
browser-use back                # Go back
browser-use scroll down         # Scroll down
browser-use scroll up           # Scroll up
```

### Page State

```bash
browser-use state               # Get URL, title, and clickable elements with indices
browser-use screenshot          # Take screenshot (outputs base64)
browser-use screenshot path.png # Save screenshot to file
browser-use screenshot --full path.png  # Full page screenshot
```

### Interactions (use indices from `browser-use state`)

```bash
browser-use click <index>              # Click element
browser-use type "text"                # Type into focused element
browser-use input <index> "text"       # Click element then type text
browser-use keys "Enter"               # Send keyboard key
browser-use keys "Control+a"           # Send key combination
browser-use select <index> "option"    # Select dropdown option
browser-use hover <index>              # Hover over element
browser-use dblclick <index>           # Double-click element
```

### Tab Management

```bash
browser-use switch <tab>        # Switch to tab by index
browser-use close-tab           # Close current tab
browser-use close-tab <tab>     # Close specific tab
```

### JavaScript & Data

```bash
browser-use eval "document.title"              # Execute JavaScript
browser-use extract "all product prices"       # Extract data using LLM (requires API key)
```

### Wait Conditions

```bash
browser-use wait selector "h1"                          # Wait for element visible
browser-use wait selector ".loading" --state hidden      # Wait for element to disappear
browser-use wait text "Success"                          # Wait for text to appear
browser-use wait selector "h1" --timeout 5000            # Custom timeout (ms)
```

### Information Retrieval

```bash
browser-use get title               # Page title
browser-use get html                # Full page HTML
browser-use get html --selector "h1"  # HTML of specific element
browser-use get text <index>        # Text content of element
browser-use get value <index>       # Value of input/textarea
browser-use get attributes <index>  # All attributes of element
```

### Session Management

```bash
browser-use sessions              # List active sessions
browser-use close                 # Close current session
browser-use close --all           # Close all sessions
browser-use --session NAME open <url>  # Named session for parallel browsing
```

### Agent Mode (autonomous task completion)

For complex multi-step tasks, use the bundled script to run a browser-use AI agent:

```bash
python nanobot/skills/browser-use/scripts/browser_agent.py run --task "Find the top 3 posts on Hacker News and summarize them"
python nanobot/skills/browser-use/scripts/browser_agent.py run --task "Fill in the contact form at example.com with name John, email john@test.com" --headed
python nanobot/skills/browser-use/scripts/browser_agent.py run --task "Search for Python tutorials" --max-steps 30
```

## Examples

### Search and Extract

```bash
browser-use open https://www.google.com
browser-use state
browser-use input 0 "nanobot AI assistant"
browser-use keys "Enter"
browser-use state
browser-use screenshot search_results.png
browser-use close
```

### Form Submission

```bash
browser-use open https://example.com/contact
browser-use state
# Shows: [0] input "Name", [1] input "Email", [2] textarea "Message", [3] button "Submit"
browser-use input 0 "John Doe"
browser-use input 1 "john@example.com"
browser-use input 2 "Hello, this is a test."
browser-use click 3
browser-use state  # Verify success
browser-use close
```

### Multi-Session Workflow

```bash
browser-use --session work open https://work.example.com
browser-use --session personal open https://personal.example.com
browser-use --session work state
browser-use --session personal state
browser-use close --all
```

### Using Real Browser (Pre-authenticated)

```bash
browser-use --browser real open https://gmail.com
# Already logged in with your Chrome sessions
browser-use state
browser-use close
```

## Tips

1. **Always run `browser-use state` first** to see elements and their indices
2. **Use `--headed` for debugging** to see what the browser is doing
3. **Sessions persist** — browser stays open between commands
4. **Use `--json`** for parsing output programmatically
5. **Real browser mode** preserves your login sessions and extensions
6. **Always close the browser when done** with `browser-use close`

## Troubleshooting

- **Browser won't start?** — Run `browser-use install` to install/reinstall Chromium
- **Element not found?** — Run `browser-use state`, try `browser-use scroll down`, then `browser-use state` again
- **Session issues?** — Run `browser-use close --all` for a clean slate

## Configuration

Browser-use agent settings can be configured in `~/.nanobot/config.json` under `tools.browserUse`:

```json
{
  "tools": {
    "browserUse": {
      "model": "deepseek/deepseek-chat",
      "apiKey": "sk-xxx",
      "apiBase": "https://api.deepseek.com/v1",
      "headless": true,
      "browserMode": "chromium",
      "maxSteps": 20,
      "chromeProfile": "",
      "screenshotDir": ""
    }
  }
}
```

| Field | Description | Default |
|-------|-------------|---------|
| `model` | LLM model for agent mode. Empty = use `agents.defaults.model` | `""` |
| `apiKey` | API key override. Empty = auto-detect from `providers` config | `""` |
| `apiBase` | API base URL override. Empty = use provider default | `""` |
| `headless` | Run browser without visible window | `true` |
| `browserMode` | `chromium` (isolated), `real` (user's Chrome), `remote` (cloud) | `"chromium"` |
| `maxSteps` | Max agent steps for autonomous tasks | `20` |
| `chromeProfile` | Chrome profile name (for `real` mode) | `""` |
| `screenshotDir` | Directory for screenshots. Empty = `~/.nanobot/screenshots` | `""` |

Priority: CLI arguments > `tools.browserUse` config > `agents.defaults` > environment variables.
