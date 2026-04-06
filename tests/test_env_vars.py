"""Tests for the environment variable redaction plugin."""

from __future__ import annotations

import pytest

from it2mcp.redact.builtin.env_vars import EnvVarsPlugin


@pytest.fixture
def plugin() -> EnvVarsPlugin:
    return EnvVarsPlugin()


class TestEnvVarsKeyValueRedaction:
    def test_simple_key_value(self, plugin: EnvVarsPlugin) -> None:
        line = "SECRET_KEY=mysecretvalue123"
        result = plugin.redact(line)
        assert "mysecretvalue123" not in result
        assert "SECRET_KEY=" in result

    def test_export_prefix(self, plugin: EnvVarsPlugin) -> None:
        line = "export GITHUB_TOKEN=ghp_abc123"
        result = plugin.redact(line)
        assert "ghp_abc123" not in result
        assert "GITHUB_TOKEN" in result

    def test_declare_prefix(self, plugin: EnvVarsPlugin) -> None:
        line = 'declare -x API_KEY="sk-some-key"'
        result = plugin.redact(line)
        assert "sk-some-key" not in result
        assert "API_KEY" in result

    def test_colon_separator(self, plugin: EnvVarsPlugin) -> None:
        line = "password: hunter2"
        result = plugin.redact(line)
        assert "hunter2" not in result

    def test_equals_with_spaces(self, plugin: EnvVarsPlugin) -> None:
        line = "AWS_SECRET = my_aws_secret_value"
        result = plugin.redact(line)
        assert "my_aws_secret_value" not in result


class TestEnvVarsSensitiveNames:
    def test_token_var(self, plugin: EnvVarsPlugin) -> None:
        result = plugin.redact("AUTH_TOKEN=abc123")
        assert "abc123" not in result

    def test_password_var(self, plugin: EnvVarsPlugin) -> None:
        result = plugin.redact("DB_PASSWORD=secret")
        assert "secret" not in result

    def test_api_key_var(self, plugin: EnvVarsPlugin) -> None:
        result = plugin.redact("OPENAI_API_KEY=sk-xxx")
        assert "sk-xxx" not in result

    def test_client_secret_var(self, plugin: EnvVarsPlugin) -> None:
        result = plugin.redact("CLIENT_SECRET=oauth_secret_value")
        assert "oauth_secret_value" not in result

    def test_connection_string_var(self, plugin: EnvVarsPlugin) -> None:
        result = plugin.redact("CONNECTION_STRING=postgres://user:pass@host/db")
        assert "postgres://" not in result

    def test_credential_var(self, plugin: EnvVarsPlugin) -> None:
        result = plugin.redact("MY_CREDENTIAL=somecred")
        assert "somecred" not in result


class TestEnvVarsNonSensitive:
    def test_path_not_redacted(self, plugin: EnvVarsPlugin) -> None:
        line = "PATH=/usr/bin:/usr/local/bin"
        assert plugin.redact(line) == line

    def test_home_not_redacted(self, plugin: EnvVarsPlugin) -> None:
        line = "HOME=/Users/testuser"
        assert plugin.redact(line) == line

    def test_editor_not_redacted(self, plugin: EnvVarsPlugin) -> None:
        line = "EDITOR=vim"
        assert plugin.redact(line) == line

    def test_lang_not_redacted(self, plugin: EnvVarsPlugin) -> None:
        line = "LANG=en_US.UTF-8"
        assert plugin.redact(line) == line

    def test_shell_not_redacted(self, plugin: EnvVarsPlugin) -> None:
        line = "SHELL=/bin/zsh"
        assert plugin.redact(line) == line


class TestEnvVarsMultiline:
    def test_mixed_env_output(self, plugin: EnvVarsPlugin) -> None:
        text = (
            "HOME=/Users/test\n"
            "PATH=/usr/bin\n"
            "SECRET_TOKEN=abc123secret\n"
            "LANG=en_US.UTF-8\n"
            "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI\n"
        )
        result = plugin.redact(text)
        assert "/Users/test" in result
        assert "/usr/bin" in result
        assert "abc123secret" not in result
        assert "en_US.UTF-8" in result
        assert "wJalrXUtnFEMI" not in result

    def test_empty_string(self, plugin: EnvVarsPlugin) -> None:
        assert plugin.redact("") == ""

    def test_normal_command_output(self, plugin: EnvVarsPlugin) -> None:
        text = "total 42\ndrwxr-xr-x  5 user staff 160 Apr  3 12:00 .\n"
        assert plugin.redact(text) == text

    def test_custom_replacement(self, plugin: EnvVarsPlugin) -> None:
        line = "SECRET_KEY=mysecret"
        result = plugin.redact(line, "***")
        assert "mysecret" not in result
        assert "***" in result
