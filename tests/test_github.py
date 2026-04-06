"""Tests for the GitHub redaction plugin."""

from __future__ import annotations

import pytest

from it2mcp.redact.builtin.github import GitHubPlugin


@pytest.fixture
def plugin() -> GitHubPlugin:
    return GitHubPlugin()


class TestGitHubPlugin:
    def test_name(self, plugin: GitHubPlugin) -> None:
        assert plugin.name == "github"

    def test_classic_pat(self, plugin: GitHubPlugin) -> None:
        token = "ghp_" + "a" * 36
        assert plugin.redact(f"token: {token}") == "token: [REDACTED]"

    def test_fine_grained_pat(self, plugin: GitHubPlugin) -> None:
        token = "github_pat_" + "A" * 82
        assert plugin.redact(token) == "[REDACTED]"

    def test_oauth_token(self, plugin: GitHubPlugin) -> None:
        token = "gho_" + "x" * 36
        assert plugin.redact(token) == "[REDACTED]"

    def test_user_to_server_token(self, plugin: GitHubPlugin) -> None:
        token = "ghu_" + "B" * 36
        assert plugin.redact(token) == "[REDACTED]"

    def test_server_to_server_token(self, plugin: GitHubPlugin) -> None:
        token = "ghs_" + "C" * 36
        assert plugin.redact(token) == "[REDACTED]"

    def test_refresh_token(self, plugin: GitHubPlugin) -> None:
        token = "ghr_" + "D" * 36
        assert plugin.redact(token) == "[REDACTED]"

    def test_too_short_not_matched(self, plugin: GitHubPlugin) -> None:
        short = "ghp_abc123"
        assert plugin.redact(short) == short

    def test_embedded_in_text(self, plugin: GitHubPlugin) -> None:
        token = "ghp_" + "z" * 36
        text = f"export GITHUB_TOKEN={token} && echo done"
        result = plugin.redact(text)
        assert "ghp_" not in result
        assert "echo done" in result

    def test_multiple_tokens(self, plugin: GitHubPlugin) -> None:
        t1 = "ghp_" + "a" * 36
        t2 = "gho_" + "b" * 36
        result = plugin.redact(f"{t1} and {t2}")
        assert result == "[REDACTED] and [REDACTED]"

    def test_normal_text_unchanged(self, plugin: GitHubPlugin) -> None:
        assert plugin.redact("nothing secret here") == "nothing secret here"

    def test_custom_replacement(self, plugin: GitHubPlugin) -> None:
        token = "ghp_" + "a" * 36
        assert plugin.redact(token, "***") == "***"
