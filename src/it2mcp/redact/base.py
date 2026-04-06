"""Abstract base class for redaction plugins."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod


class RedactPlugin(ABC):
    """Base class for secret redaction plugins.

    Each plugin is responsible for detecting and redacting a specific category
    of secrets from terminal output. Plugins are self-contained and independent.

    To create a custom plugin, subclass this and implement:
        - name: unique identifier for config (e.g. "github")
        - description: human-readable description
        - patterns(): return list of compiled regex patterns
        - redact(text, replacement): apply redaction and return cleaned text

    Drop custom plugin files in ~/.config/it2mcp/redact-plugins/ and they
    will be auto-discovered on startup.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this plugin (used in config to enable/disable)."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this plugin redacts."""
        ...

    @abstractmethod
    def patterns(self) -> list[re.Pattern[str]]:
        """Return compiled regex patterns that match secrets.

        Each pattern should match the full secret token/value.
        Patterns are applied in order; first match wins per position.
        """
        ...

    def redact(self, text: str, replacement: str = "[REDACTED]") -> str:
        """Apply all patterns to text, replacing matches with replacement.

        Override this method if you need custom redaction logic beyond
        simple pattern replacement (e.g. partial masking, context-aware).

        Args:
            text: the terminal output to scan
            replacement: the string to substitute for detected secrets

        Returns:
            the text with secrets replaced
        """
        for pattern in self.patterns():
            text = pattern.sub(replacement, text)
        return text
