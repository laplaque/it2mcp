# it2mcp

MCP server for controlling [iTerm2](https://iterm2.com) from AI assistants, editors, and other MCP clients.

Built on iTerm2's official [Python API](https://iterm2.com/python-api/), it2mcp exposes 40 tools for managing sessions, windows, tabs, profiles, and more — with a security model that keeps you in control.

## Prerequisites

- **macOS** with [iTerm2](https://iterm2.com) installed
- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- iTerm2's Python API enabled: **Preferences → General → Magic → Enable Python API**

## Installation

```bash
git clone https://github.com/youruser/it2mcp.git
cd it2mcp
uv sync
```

## Usage

### Add to Claude Code

```bash
claude mcp add -s user it2mcp -- uv --directory /path/to/it2mcp run it2mcp
```

### Add to other MCP clients

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "it2mcp": {
      "command": "uv",
      "args": ["--directory", "/path/to/it2mcp", "run", "it2mcp"]
    }
  }
}
```

### Run standalone

```bash
uv run it2mcp
```

## Security

it2mcp ships **secure by default**. Two mechanisms protect your terminal sessions:

### Session tagging

Sessions must be explicitly tagged before MCP can interact with them. Untagged sessions are invisible to all tools except `session_list` (which shows their `mcp_enabled` status so you know what to tag).

**Tag a session** (run this in the session's terminal):

```bash
# Using the it2 CLI
it2 session set-var user.mcp_enabled true

# Or using iTerm2's escape sequence (no dependencies)
printf '\033]1337;SetUserVar=%s=%s\007' mcp_enabled $(echo -n true | base64)
```

**Untag a session:**

```bash
it2 session set-var user.mcp_enabled false
```

Tags are **not persistent** — they reset when the session ends. This is intentional: you opt in per-session, per-lifetime.

### Permission tiers

Tools are grouped into three tiers:

| Tier | Tools | Description |
|------|-------|-------------|
| **read** | `session_list`, `session_read`, `session_get_variable`, `tab_list`, `window_list`, `app_get_focus`, `profile_list`, `profile_show`, `app_version`, `app_theme`, `window_arrange_list` | Observation only |
| **interact** | `session_send`, `session_run`, `session_split`, `session_clear`, `session_focus`, `session_set_name`, `session_set_variable`, `tab_new`, `tab_select`, `tab_next`, `tab_prev`, `tab_move`, `window_new`, `window_focus`, `window_move`, `window_resize`, `window_fullscreen`, `window_arrange_save`, `window_arrange_restore`, `app_activate`, `broadcast_on`, `broadcast_off`, `broadcast_add`, `profile_apply`, `batch`, `send_keystrokes` | Can send input and modify layout |
| **destructive** | `session_close`, `session_restart`, `tab_close`, `window_close` | Can terminate sessions and close windows |

By default, only `read` is enabled.

### Audit log

Every tool invocation is logged to `~/.local/share/it2mcp/audit.jsonl` with timestamp, tool name, parameters, and result.

## Configuration

Create `~/.config/it2mcp/config.yaml`:

```yaml
# Which permission tiers to enable
permissions:
  - read
  - interact
  # - destructive

# Require sessions to have user.mcp_enabled set (default: true)
require_tag: true

# Audit log path (set to null to disable)
audit_log: ~/.local/share/it2mcp/audit.jsonl
```

Override the config path with the `IT2MCP_CONFIG` environment variable.

## Tools

### Session

| Tool | Tier | Description |
|------|------|-------------|
| `session_list` | read | List all sessions with IDs, names, sizes, and `mcp_enabled` status |
| `session_read` | read | Read visible screen contents |
| `session_get_variable` | read | Get a session variable (e.g. `path`, `name`, `tty`) |
| `session_send` | interact | Send text without pressing Enter |
| `session_run` | interact | Execute a command (text + Enter) |
| `session_split` | interact | Split into a new pane |
| `session_clear` | interact | Clear screen (Ctrl+L) |
| `session_focus` | interact | Activate a specific session |
| `session_set_name` | interact | Set session name |
| `session_set_variable` | interact | Set a session variable |
| `session_close` | destructive | Close a session |
| `session_restart` | destructive | Restart a session |

### Window

| Tool | Tier | Description |
|------|------|-------------|
| `window_list` | read | List all windows with positions and sizes |
| `window_arrange_list` | read | List saved window arrangements |
| `window_new` | interact | Create a new window |
| `window_focus` | interact | Activate a specific window |
| `window_move` | interact | Move window to screen position |
| `window_resize` | interact | Resize a window |
| `window_fullscreen` | interact | Set fullscreen on/off/toggle |
| `window_arrange_save` | interact | Save current arrangement |
| `window_arrange_restore` | interact | Restore a saved arrangement |
| `window_close` | destructive | Close a window |

### Tab

| Tool | Tier | Description |
|------|------|-------------|
| `tab_list` | read | List all tabs with IDs and active state |
| `tab_new` | interact | Create a new tab |
| `tab_select` | interact | Select tab by ID or index |
| `tab_next` | interact | Switch to next tab |
| `tab_prev` | interact | Switch to previous tab |
| `tab_move` | interact | Move tab to its own window |
| `tab_close` | destructive | Close a tab |

### App

| Tool | Tier | Description |
|------|------|-------------|
| `app_get_focus` | read | Get focused window/tab/session info |
| `app_version` | read | Get iTerm2 version |
| `app_theme` | read | Get or set theme |
| `app_activate` | interact | Bring iTerm2 to front |

### Broadcast

| Tool | Tier | Description |
|------|------|-------------|
| `broadcast_on` | interact | Enable broadcasting to all sessions in current tab |
| `broadcast_off` | interact | Disable broadcasting |
| `broadcast_add` | interact | Create broadcast group with specific sessions |

### Profile

| Tool | Tier | Description |
|------|------|-------------|
| `profile_list` | read | List all profiles |
| `profile_show` | read | Show profile details |
| `profile_apply` | interact | Apply a profile to a session |

### Batch

| Tool | Tier | Description |
|------|------|-------------|
| `batch` | interact | Execute multiple operations in a single iTerm2 connection |

The `batch` tool accepts a list of operations and runs them sequentially over one connection. Supports a `sleep` operation for timing between steps. Each operation's tier is checked individually.

```json
[
  {"op": "session_run", "command": "echo hello"},
  {"op": "sleep", "seconds": 1.0},
  {"op": "session_read"}
]
```

## License

MIT
