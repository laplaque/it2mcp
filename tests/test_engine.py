"""Tests for the RedactEngine."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import ClassVar

import pytest

from it2mcp.redact import RedactEngine
from it2mcp.redact.base import RedactPlugin


class DummyPlugin(RedactPlugin):
    """Test plugin that redacts 'DUMMY_SECRET_xxx'."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "Test plugin"

    def patterns(self) -> list[re.Pattern[str]]:
        return [re.compile(r"DUMMY_SECRET_[A-Za-z0-9]+")]


class FailingPlugin(RedactPlugin):
    """Plugin that raises on redact — tests error resilience."""

    @property
    def name(self) -> str:
        return "failing"

    @property
    def description(self) -> str:
        return "Always fails"

    def patterns(self) -> list[re.Pattern[str]]:
        return []

    def redact(self, text: str, replacement: str = "[REDACTED]") -> str:
        raise RuntimeError("boom")


class TestEngineBasics:
    def test_enabled_by_default(self) -> None:
        engine = RedactEngine()
        assert engine.enabled is True

    def test_disabled_engine_passes_through(self) -> None:
        engine = RedactEngine(enabled=False)
        text = "ghp_abc123def456ghi789jklmnopqrstuv0123456"
        assert engine.redact(text) == text

    def test_loads_all_builtin_plugins(self) -> None:
        engine = RedactEngine()
        names = engine.plugin_names
        assert "github" in names
        assert "gitlab" in names
        assert "aws" in names
        assert "generic" in names
        assert "env_vars" in names

    def test_custom_replacement_string(self) -> None:
        engine = RedactEngine(replacement="***")
        text = "token: ghp_abc123def456ghi789jklmnopqrstuv0123456"
        result = engine.redact(text)
        assert "***" in result
        assert "ghp_" not in result


class TestDisabledPlugins:
    def test_disable_single_plugin(self) -> None:
        engine = RedactEngine(disabled_plugins=["github"])
        assert "github" not in engine.plugin_names
        assert "gitlab" in engine.plugin_names

    def test_disable_multiple_plugins(self) -> None:
        engine = RedactEngine(disabled_plugins=["github", "gitlab", "aws"])
        names = engine.plugin_names
        assert "github" not in names
        assert "gitlab" not in names
        assert "aws" not in names
        assert "generic" in names

    def test_disable_nonexistent_plugin_is_harmless(self) -> None:
        engine = RedactEngine(disabled_plugins=["nonexistent"])
        assert len(engine.plugins) > 0


class TestFromConfig:
    def test_from_empty_config(self) -> None:
        engine = RedactEngine.from_config({})
        assert engine.enabled is True
        assert engine.replacement == "[REDACTED]"

    def test_from_config_disabled(self) -> None:
        config = {"redact": {"enabled": False}}
        engine = RedactEngine.from_config(config)
        assert engine.enabled is False
        assert len(engine.plugins) == 0

    def test_from_config_custom_replacement(self) -> None:
        config = {"redact": {"replacement": "<SCRUBBED>"}}
        engine = RedactEngine.from_config(config)
        assert engine.replacement == "<SCRUBBED>"

    def test_from_config_disabled_plugins(self) -> None:
        config = {"redact": {"disabled_plugins": ["aws", "gitlab"]}}
        engine = RedactEngine.from_config(config)
        assert "aws" not in engine.plugin_names
        assert "gitlab" not in engine.plugin_names

    def test_from_config_custom_plugin_dir(self, tmp_path: Path) -> None:
        config = {"redact": {"custom_plugin_dir": str(tmp_path)}}
        engine = RedactEngine.from_config(config)
        # No crash, no custom plugins found in empty dir
        assert engine.enabled is True


class TestPipeline:
    def test_plugins_run_in_sequence(self) -> None:
        engine = RedactEngine()
        text = "github: ghp_abc123def456ghi789jklmnopqrstuv0123456 aws: AKIAIOSFODNN7EXAMPLE"
        result = engine.redact(text)
        assert "ghp_" not in result
        assert "AKIA" not in result
        assert "[REDACTED]" in result

    def test_normal_text_passes_through(self) -> None:
        engine = RedactEngine()
        text = "just some normal output with no secrets"
        assert engine.redact(text) == text

    def test_empty_string(self) -> None:
        engine = RedactEngine()
        assert engine.redact("") == ""

    def test_plugin_failure_doesnt_break_pipeline(self) -> None:
        engine = RedactEngine(enabled=False)  # skip builtins
        engine._plugins = [FailingPlugin(), DummyPlugin()]
        engine.enabled = True
        text = "hello DUMMY_SECRET_abc123 world"
        result = engine.redact(text)
        # FailingPlugin raised but DummyPlugin still ran
        assert "DUMMY_SECRET" not in result


class TestCustomPluginDiscovery:
    def test_discovers_plugin_from_directory(self, tmp_path: Path) -> None:
        plugin_code = textwrap.dedent("""\
            import re
            from it2mcp.redact.base import RedactPlugin

            class TestCustomPlugin(RedactPlugin):
                @property
                def name(self) -> str:
                    return "test_custom"

                @property
                def description(self) -> str:
                    return "Test custom plugin"

                def patterns(self) -> list[re.Pattern[str]]:
                    return [re.compile(r"CUSTOM_KEY_[A-Za-z0-9]+")]
        """)
        (tmp_path / "my_plugin.py").write_text(plugin_code)

        engine = RedactEngine(custom_plugin_dir=tmp_path)
        assert "test_custom" in engine.plugin_names
        result = engine.redact("found CUSTOM_KEY_abc123xyz")
        assert "CUSTOM_KEY" not in result

    def test_ignores_underscore_prefixed_files(self, tmp_path: Path) -> None:
        (tmp_path / "_internal.py").write_text("# should be skipped")
        engine = RedactEngine(custom_plugin_dir=tmp_path)
        # No crash, underscore file ignored
        assert engine.enabled is True

    def test_handles_invalid_plugin_file(self, tmp_path: Path) -> None:
        (tmp_path / "bad_plugin.py").write_text("raise SyntaxError('broken')")
        engine = RedactEngine(custom_plugin_dir=tmp_path)
        # No crash, bad file logged and skipped
        assert engine.enabled is True

    def test_nonexistent_plugin_dir(self) -> None:
        engine = RedactEngine(custom_plugin_dir=Path("/nonexistent/dir"))
        assert engine.enabled is True
