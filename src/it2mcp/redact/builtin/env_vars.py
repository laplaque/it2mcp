"""Redaction plugin for environment variable dump commands."""

from __future__ import annotations

import re

from ..base import RedactPlugin


_SENSITIVE_VAR_NAMES = re.compile(
    r"(?i)("
    r"token|secret|password|passwd|api[_-]?key|private[_-]?key|"
    r"access[_-]?key|auth|credential|connection[_-]?string|"
    r"database[_-]?url|redis[_-]?url|mongodb[_-]?uri|"
    r"smtp[_-]?pass|mail[_-]?pass|"
    r"encryption[_-]?key|signing[_-]?key|"
    r"client[_-]?secret|app[_-]?secret|"
    r"webhook[_-]?secret|"
    r"github[_-]?token|gitlab[_-]?token|"
    r"openai[_-]?api[_-]?key|anthropic[_-]?api[_-]?key|"
    r"aws[_-]?secret|"
    r"stripe[_-]?key|sendgrid[_-]?key|twilio[_-]?auth"
    r")"
)


class EnvVarsPlugin(RedactPlugin):
    """Detects and redacts sensitive values in environment variable output.

    Catches output from commands like `env`, `printenv`, `export`, `set`
    where the output format is KEY=VALUE or KEY: VALUE, and the key name
    matches common secret variable names.
    """

    @property
    def name(self) -> str:
        return "env_vars"

    @property
    def description(self) -> str:
        return "Sensitive values in env/printenv/export output"

    def patterns(self) -> list[re.Pattern[str]]:
        # Not used directly — we override redact() for context-aware matching
        return []

    def redact(self, text: str, replacement: str = "[REDACTED]") -> str:
        """Scan each line for KEY=VALUE patterns where KEY looks sensitive."""
        lines = text.split("\n")
        result = []
        for line in lines:
            # Match patterns like: SECRET_KEY=somevalue or SECRET_KEY: somevalue
            # Also handles: export SECRET_KEY=somevalue, declare -x SECRET_KEY="somevalue"
            match = re.match(
                r"^(\s*(?:export\s+|declare\s+-x\s+)?)"  # optional prefix
                r"([A-Za-z_][A-Za-z0-9_]*)"               # variable name
                r"(\s*[=:]\s*)"                            # separator
                r"(.+)$",                                   # value
                line,
            )
            if match and _SENSITIVE_VAR_NAMES.search(match.group(2)):
                # Replace the value portion, keep the key
                result.append(f"{match.group(1)}{match.group(2)}{match.group(3)}{replacement}")
            else:
                result.append(line)
        return "\n".join(result)
