"""Redaction engine — loads and runs plugins to scrub secrets from terminal output."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from .base import RedactPlugin

logger = logging.getLogger(__name__)

# Built-in plugins — imported eagerly so they're always available
_BUILTIN_PLUGINS: list[type[RedactPlugin]] = []


def _load_builtins() -> None:
    """Import all built-in plugin classes."""
    from .builtin.github import GitHubPlugin
    from .builtin.gitlab import GitLabPlugin
    from .builtin.aws import AWSPlugin
    from .builtin.generic import GenericSecretsPlugin
    from .builtin.env_vars import EnvVarsPlugin

    _BUILTIN_PLUGINS.extend([
        GitHubPlugin,
        GitLabPlugin,
        AWSPlugin,
        GenericSecretsPlugin,
        EnvVarsPlugin,
    ])


def _discover_custom_plugins(plugin_dir: Path) -> list[type[RedactPlugin]]:
    """Discover and load custom plugin classes from a directory.

    Each .py file in the directory is imported. Any class that subclasses
    RedactPlugin is collected and returned.
    """
    plugins: list[type[RedactPlugin]] = []
    if not plugin_dir.is_dir():
        return plugins

    for py_file in sorted(plugin_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"it2mcp.redact.custom.{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, RedactPlugin)
                    and attr is not RedactPlugin
                ):
                    plugins.append(attr)
                    logger.info("Loaded custom redact plugin: %s from %s", attr_name, py_file.name)
        except Exception:
            logger.warning("Failed to load custom plugin %s", py_file, exc_info=True)

    return plugins


class RedactEngine:
    """Loads plugins and applies redaction to text.

    Usage:
        engine = RedactEngine(config)
        clean_text = engine.redact(terminal_output)
    """

    def __init__(
        self,
        enabled: bool = True,
        replacement: str = "[REDACTED]",
        disabled_plugins: list[str] | None = None,
        custom_plugin_dir: Path | None = None,
    ) -> None:
        self.enabled = enabled
        self.replacement = replacement
        self._disabled = set(disabled_plugins or [])
        self._plugins: list[RedactPlugin] = []

        if not self.enabled:
            return

        # Load builtins
        if not _BUILTIN_PLUGINS:
            _load_builtins()

        for cls in _BUILTIN_PLUGINS:
            instance = cls()
            if instance.name not in self._disabled:
                self._plugins.append(instance)
                logger.debug("Enabled built-in redact plugin: %s", instance.name)
            else:
                logger.debug("Disabled built-in redact plugin: %s", instance.name)

        # Load custom plugins
        if custom_plugin_dir:
            for cls in _discover_custom_plugins(custom_plugin_dir):
                instance = cls()
                if instance.name not in self._disabled:
                    self._plugins.append(instance)
                else:
                    logger.debug("Disabled custom redact plugin: %s", instance.name)

    @property
    def plugins(self) -> list[RedactPlugin]:
        """Return the list of active plugins."""
        return list(self._plugins)

    @property
    def plugin_names(self) -> list[str]:
        """Return the names of all active plugins."""
        return [p.name for p in self._plugins]

    def redact(self, text: str) -> str:
        """Apply all active plugins to the text, returning the redacted version.

        Each plugin is applied in sequence. The output of one plugin becomes
        the input of the next. This means plugins can build on each other's
        redactions without interfering.
        """
        if not self.enabled or not self._plugins:
            return text

        for plugin in self._plugins:
            try:
                text = plugin.redact(text, self.replacement)
            except Exception:
                logger.warning("Redact plugin %s failed", plugin.name, exc_info=True)

        return text

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> RedactEngine:
        """Create a RedactEngine from a config dict (the 'redact' section of config.yaml).

        Expected config structure:
            redact:
              enabled: true
              replacement: "[REDACTED]"
              disabled_plugins: []
              custom_plugin_dir: ~/.config/it2mcp/redact-plugins/
        """
        redact_config = config.get("redact", {})
        return cls(
            enabled=redact_config.get("enabled", True),
            replacement=redact_config.get("replacement", "[REDACTED]"),
            disabled_plugins=redact_config.get("disabled_plugins", []),
            custom_plugin_dir=(
                Path(redact_config["custom_plugin_dir"]).expanduser()
                if redact_config.get("custom_plugin_dir")
                else None
            ),
        )
