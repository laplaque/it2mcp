"""Command confirmation gate for it2mcp.

Provides allow/deny/ask classification for commands and an osascript-based
confirmation dialog for commands that require user approval.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
from enum import Enum
from typing import Any

from .security import audit_log, get_config, redact_output

logger = logging.getLogger(__name__)


class GateResult(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


# In-memory session allow list — commands approved via "Allow for Session"
# Resets when the MCP server restarts.
_session_allowed: set[str] = set()


def _normalize_command(command: str) -> str:
    """Strip leading/trailing whitespace from a command."""
    return command.strip()


def match_pattern(command: str, patterns: list[str]) -> bool:
    """Check if a command matches any pattern in the list.

    Supports:
    - Exact match: "pwd" matches "pwd"
    - Wildcard: "git *" matches "git status", "git diff --cached", etc.
    - Pattern without wildcard matches as prefix: "sudo" matches "sudo rm -rf /"
    """
    command = _normalize_command(command)
    for pattern in patterns:
        pattern = pattern.strip()
        if "*" in pattern or "?" in pattern:
            # fnmatch-style wildcard matching
            if fnmatch.fnmatch(command, pattern):
                return True
        else:
            # Exact match or prefix match
            if command == pattern or command.startswith(pattern + " "):
                return True
    return False


def check_command(command: str) -> GateResult:
    """Classify a command as allow, deny, or ask.

    Evaluation order:
    1. Deny list → DENY
    2. Session allow list (in-memory) → ALLOW
    3. Config allow list → ALLOW
    4. Everything else → ASK
    """
    config = get_config()
    commands_config = config.commands

    if not commands_config.get("enabled", True):
        return GateResult.ALLOW

    command = _normalize_command(command)

    # 1. Check deny list
    deny_patterns = commands_config.get("deny", [])
    if match_pattern(command, deny_patterns):
        audit_log("gate", {"command": command, "result": "deny"})
        return GateResult.DENY

    # 2. Check session allow list (in-memory, from "Allow for Session" clicks)
    if match_pattern(command, list(_session_allowed)):
        return GateResult.ALLOW

    # 3. Check config allow list
    allow_patterns = commands_config.get("allow", [])
    if match_pattern(command, allow_patterns):
        return GateResult.ALLOW

    # 4. Not in any list → ask
    return GateResult.ASK


def _extract_command_prefix(command: str) -> str:
    """Extract a reasonable prefix from a command for session allow list.

    Takes the first two tokens (e.g. "go test" from "go test -v ./..."),
    or the first token if the command is a single word.
    """
    parts = _normalize_command(command).split()
    if len(parts) <= 1:
        return parts[0] if parts else command
    return f"{parts[0]} {parts[1]}"


async def confirm_command(command: str) -> tuple[bool, bool]:
    """Show an osascript confirmation dialog for a command.

    Args:
        command: The command to confirm.

    Returns:
        Tuple of (approved: bool, remember_for_session: bool).
        - (True, False): user clicked "Allow"
        - (True, True): user clicked "Allow for Session"
        - (False, False): user clicked "Deny", dismissed, or timeout
    """
    config = get_config()
    timeout = config.commands.get("timeout", 30)

    # Redact secrets from the command before showing in dialog
    display_command = redact_output(command)

    # Escape double quotes and backslashes for osascript
    escaped = display_command.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
    tell application "System Events"
        set dialogResult to display dialog "it2mcp wants to run:\\n\\n{escaped}" ¬
            with title "Command Confirmation" ¬
            buttons {{"Deny", "Allow for Session", "Allow"}} ¬
            default button "Deny" ¬
            cancel button "Deny" ¬
            giving up after {timeout}
        return button returned of dialogResult & "|" & gave up of dialogResult
    end tell
    '''

    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            # User clicked Deny or dismissed the dialog
            audit_log("gate_confirm", {"command": command, "result": "denied"})
            return False, False

        result = stdout.decode().strip()
        parts = result.split("|")
        button = parts[0] if parts else ""
        gave_up = parts[1].strip().lower() == "true" if len(parts) > 1 else False

        if gave_up:
            audit_log("gate_confirm", {"command": command, "result": "timeout"})
            return False, False

        if button == "Allow":
            audit_log("gate_confirm", {"command": command, "result": "allowed"})
            return True, False

        if button == "Allow for Session":
            prefix = _extract_command_prefix(command)
            _session_allowed.add(f"{prefix} *")
            audit_log("gate_confirm", {
                "command": command,
                "result": "allowed_for_session",
                "prefix": f"{prefix} *",
            })
            return True, True

        # Deny or anything else
        audit_log("gate_confirm", {"command": command, "result": "denied"})
        return False, False

    except Exception as e:
        logger.error("osascript confirmation failed: %s", e)
        audit_log("gate_confirm", {"command": command}, error=str(e))
        return False, False


async def gate_command(command: str) -> bool:
    """Full gate check: classify and optionally confirm a command.

    Returns True if the command is allowed to execute, False otherwise.
    Raises PermissionError for denied commands.
    """
    result = check_command(command)

    if result == GateResult.ALLOW:
        return True

    if result == GateResult.DENY:
        raise PermissionError(
            f"Command denied by security policy: {redact_output(command)}"
        )

    # ASK — show confirmation dialog
    approved, _ = await confirm_command(command)
    if not approved:
        raise PermissionError(
            f"Command not approved by user: {redact_output(command)}"
        )

    return True
