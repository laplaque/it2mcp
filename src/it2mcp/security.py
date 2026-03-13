"""Security layer for it2mcp.

Provides:
- Permission tiers (read, interact, destructive)
- Session tag gating (user.mcp_enabled)
- Audit logging
- Config file loading
"""

from __future__ import annotations

import datetime
import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

import iterm2

# ---------------------------------------------------------------------------
# Permission tiers
# ---------------------------------------------------------------------------

class Tier(str, Enum):
    READ = "read"
    INTERACT = "interact"
    DESTRUCTIVE = "destructive"


# Which tier each tool belongs to.
# Tools not listed here are ungated (e.g. app_version, profile_list).
TOOL_TIERS: dict[str, Tier] = {
    # read
    "session_list": Tier.READ,
    "session_read": Tier.READ,
    "session_get_variable": Tier.READ,
    "tab_list": Tier.READ,
    "window_list": Tier.READ,
    "app_get_focus": Tier.READ,
    "profile_list": Tier.READ,
    "profile_show": Tier.READ,
    "app_version": Tier.READ,
    "app_theme": Tier.READ,
    "window_arrange_list": Tier.READ,
    # interact
    "session_send": Tier.INTERACT,
    "session_run": Tier.INTERACT,
    "session_split": Tier.INTERACT,
    "session_set_name": Tier.INTERACT,
    "session_set_variable": Tier.INTERACT,
    "session_clear": Tier.INTERACT,
    "session_focus": Tier.INTERACT,
    "tab_new": Tier.INTERACT,
    "tab_select": Tier.INTERACT,
    "tab_next": Tier.INTERACT,
    "tab_prev": Tier.INTERACT,
    "tab_move": Tier.INTERACT,
    "window_new": Tier.INTERACT,
    "window_focus": Tier.INTERACT,
    "window_move": Tier.INTERACT,
    "window_resize": Tier.INTERACT,
    "window_fullscreen": Tier.INTERACT,
    "window_arrange_save": Tier.INTERACT,
    "window_arrange_restore": Tier.INTERACT,
    "app_activate": Tier.INTERACT,
    "broadcast_on": Tier.INTERACT,
    "broadcast_off": Tier.INTERACT,
    "broadcast_add": Tier.INTERACT,
    "profile_apply": Tier.INTERACT,
    "batch": Tier.INTERACT,
    "send_keystrokes": Tier.INTERACT,
    # destructive
    "session_close": Tier.DESTRUCTIVE,
    "session_restart": Tier.DESTRUCTIVE,
    "tab_close": Tier.DESTRUCTIVE,
    "window_close": Tier.DESTRUCTIVE,
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_DIR = Path.home() / ".config" / "it2mcp"
_DEFAULT_CONFIG_PATH = _DEFAULT_CONFIG_DIR / "config.yaml"
_DEFAULT_AUDIT_PATH = Path.home() / ".local" / "share" / "it2mcp" / "audit.jsonl"


class Config:
    """Server configuration loaded from ~/.config/it2mcp/config.yaml."""

    def __init__(self) -> None:
        self.permissions: set[Tier] = {Tier.READ}
        self.require_tag: bool = True
        self.audit_log: Path | None = _DEFAULT_AUDIT_PATH

    @classmethod
    def load(cls) -> Config:
        config = cls()
        path = Path(os.environ.get("IT2MCP_CONFIG", str(_DEFAULT_CONFIG_PATH)))
        if not path.exists():
            return config

        try:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        except ImportError:
            # Fall back to manual parsing if PyYAML not available
            return config

        # permissions
        if "permissions" in data:
            perms = data["permissions"]
            if isinstance(perms, list):
                config.permissions = set()
                for p in perms:
                    try:
                        config.permissions.add(Tier(p))
                    except ValueError:
                        pass

        # require_tag
        if "require_tag" in data:
            config.require_tag = bool(data["require_tag"])

        # audit_log
        if "audit_log" in data:
            if data["audit_log"] is None or data["audit_log"] is False:
                config.audit_log = None
            else:
                config.audit_log = Path(data["audit_log"]).expanduser()

        return config


# Singleton
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.load()
    return _config


# ---------------------------------------------------------------------------
# Permission checking
# ---------------------------------------------------------------------------

def assert_permission(tool_name: str) -> None:
    """Raise if the tool's tier is not in the configured permissions."""
    tier = TOOL_TIERS.get(tool_name)
    if tier is None:
        # Ungated tool
        return
    config = get_config()
    if tier not in config.permissions:
        raise PermissionError(
            f"Tool '{tool_name}' requires '{tier.value}' permission. "
            f"Current permissions: {', '.join(t.value for t in config.permissions)}. "
            f"Update ~/.config/it2mcp/config.yaml to enable it."
        )


# ---------------------------------------------------------------------------
# Session tag gating
# ---------------------------------------------------------------------------

async def check_session_allowed(session: iterm2.Session) -> None:
    """Raise if the session doesn't have user.mcp_enabled set to a truthy value."""
    config = get_config()
    if not config.require_tag:
        return
    value = await session.async_get_variable("user.mcp_enabled")
    if not value or str(value).lower() in ("false", "0", "no", ""):
        raise PermissionError(
            f"Session '{session.session_id}' is not MCP-enabled. "
            f"Tag it first: it2 session set-var user.mcp_enabled true -s {session.session_id}"
        )


async def check_sessions_allowed(sessions: list[iterm2.Session]) -> None:
    """Check all sessions in a list."""
    for s in sessions:
        await check_session_allowed(s)


async def is_session_enabled(session: iterm2.Session) -> bool:
    """Check if a session has mcp_enabled without raising."""
    config = get_config()
    if not config.require_tag:
        return True
    value = await session.async_get_variable("user.mcp_enabled")
    return bool(value) and str(value).lower() not in ("false", "0", "no", "")


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def audit_log(tool_name: str, params: dict[str, Any] | None = None, result: str | None = None, error: str | None = None) -> None:
    """Append an entry to the audit log."""
    config = get_config()
    if config.audit_log is None:
        return

    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tool": tool_name,
    }
    if params:
        # Redact overly long text values
        sanitized = {}
        for k, v in params.items():
            if isinstance(v, str) and len(v) > 200:
                sanitized[k] = v[:200] + "..."
            else:
                sanitized[k] = v
        entry["params"] = sanitized
    if result is not None:
        entry["result"] = result[:200] if len(result) > 200 else result
    if error is not None:
        entry["error"] = error

    try:
        config.audit_log.parent.mkdir(parents=True, exist_ok=True)
        with open(config.audit_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # Don't let audit failures break tool execution
