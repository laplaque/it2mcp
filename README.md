# it2mcp

MCP server for controlling [iTerm2](https://iterm2.com) from AI assistants, editors, and other MCP clients.

Built on iTerm2's official [Python API](https://iterm2.com/python-api/), it2mcp exposes terminal management tools with a layered security model: session tagging, command gate, secret redaction, and macOS sandboxing.

## Prerequisites

- **macOS** with [iTerm2](https://iterm2.com) installed
- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- iTerm2's Python API enabled: **Preferences → General → Magic → Enable Python API**

## Installation

```bash
git clone https://github.com/laplaque/it2mcp.git
cd it2mcp
uv sync
./install.sh
```

The installer sets up the macOS sandbox profile, iTerm2 "MCP Sandboxed" dynamic profile, and default configuration. See the installer output for next steps.

### Add to Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "it2mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/it2mcp", "it2mcp"]
    }
  }
}
```

### Add to Claude Code

```bash
claude mcp add -s user it2mcp -- uv --directory /path/to/it2mcp run it2mcp
```

## Security

it2mcp uses four layers of security, each addressing a different attack vector:

### 1. Session tagging

Sessions must be tagged before MCP can interact with them. `tab_new` and `window_new` always use the "MCP Sandboxed" profile, which auto-tags sessions on startup. Untagged sessions are invisible to all tools except `session_list`.

Tags are **not persistent** — they reset when the session ends.

### 2. Command gate

Before executing commands via `session_run`, `session_send`, `tab_new` (with command), or `window_new` (with command), the gate classifies the command:

1. **Deny list** → rejected immediately, logged to audit
2. **Allow list** → executed without confirmation
3. **Not in either** → macOS dialog asks the user (Allow / Allow for Session / Deny)

The dialog times out after a configurable period (default 30s) and auto-denies. Commands are piped through the secfilter before display to strip secrets.

Configure in `~/.config/it2mcp/config.yaml`:

```yaml
commands:
  enabled: true
  timeout: 30
  allow:
    - "git *"
    - "ls *"
    - "go test *"
  deny:
    - "sudo *"
    - "ssh *"
    - "gh auth *"
```

### 3. Secret redaction (secfilter)

A pluggable redaction engine scrubs secrets from `session_read` output before the MCP client sees them. Built-in plugins cover:

| Plugin | What it catches |
|--------|----------------|
| `github` | PATs, OAuth tokens, app tokens |
| `gitlab` | PATs, deploy tokens, runner tokens, CI tokens |
| `aws` | Access key IDs, secret access keys, session tokens |
| `cloud_cli` | GCP access tokens (`ya29.`), Azure accessToken (JSON + TSV) |
| `generic` | OpenAI/Anthropic keys, JWTs, bearer tokens, Slack/Stripe/SendGrid/Twilio tokens, PEM private key blocks |
| `env_vars` | Sensitive values in `env`/`printenv`/`export` output |

Custom plugins auto-discover from `~/.config/it2mcp/redact-plugins/`.

### 4. macOS sandbox

The "MCP Sandboxed" profile runs shells inside `sandbox-exec` with kernel-level file access restrictions. Blocks: SSH keys, GPG keys, AWS credentials, shell profiles, `.env` files, Claude config, shell history, cloud provider configs, password manager databases, and more.

The sandboxed shell also uses `env -i` to strip inherited environment variables, preventing leakage of tokens and secrets from the parent shell.

### Permission tiers

Tools are grouped into three tiers:

| Tier | Description |
|------|-------------|
| **read** | Observation only (session_list, session_read, etc.) |
| **interact** | Can send input and modify layout (session_run, tab_new, etc.) |
| **destructive** | Can terminate sessions and close windows |

By default, only `read` is enabled. Enable tiers in `~/.config/it2mcp/config.yaml`.

### Audit log

Every tool invocation is logged to `~/.local/share/it2mcp/audit.jsonl` with timestamp, tool name, parameters, and result. Gate decisions (allow/deny/timeout) are also logged.

## Configuration

Configuration lives at `~/.config/it2mcp/config.yaml`. See `config/example-config.yaml` for a fully documented template.

Override the config path with the `IT2MCP_CONFIG` environment variable.

## Tools

### Session

| Tool | Tier | Description |
|------|------|-------------|
| `session_list` | read | List all sessions with IDs, names, sizes, and `mcp_enabled` status |
| `session_read` | read | Read visible screen contents |
| `session_status` | read | Get busy/idle status (foreground job info) |
| `session_get_variable` | read | Get a session variable |
| `session_send` | interact | Send text without pressing Enter |
| `session_run` | interact | Execute a command (text + Enter) |
| `session_interrupt` | interact | Send SIGINT (Ctrl+C) to foreground process |
| `session_split` | interact | Split into a new pane |
| `session_clear` | interact | Clear screen (Ctrl+L) |
| `session_focus` | interact | Activate a specific session |
| `session_set_name` | interact | Set session name |
| `session_close` | destructive | Close a session |
| `session_restart` | destructive | Restart a session |

### Window

| Tool | Tier | Description |
|------|------|-------------|
| `window_list` | read | List all windows with positions and sizes |
| `window_arrange_list` | read | List saved window arrangements |
| `window_new` | interact | Create a new window (MCP Sandboxed profile) |
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
| `tab_new` | interact | Create a new tab (MCP Sandboxed profile) |
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
| `batch` | interact | Execute multiple operations in a single connection |

```json
[
  {"op": "session_run", "command": "echo hello"},
  {"op": "sleep", "seconds": 1.0},
  {"op": "session_read"}
]
```

## Acknowledgments

Built on top of [it2](https://github.com/mkusaka/it2) by [@mkusaka](https://github.com/mkusaka) — a powerful CLI for controlling iTerm2 via its Python API.

## License

MIT
