"""Tests for the GitLab redaction plugin."""

from __future__ import annotations

import pytest

from it2mcp.redact.builtin.gitlab import GitLabPlugin


@pytest.fixture
def plugin() -> GitLabPlugin:
    return GitLabPlugin()


class TestGitLabPlugin:
    def test_name(self, plugin: GitLabPlugin) -> None:
        assert plugin.name == "gitlab"

    def test_personal_access_token(self, plugin: GitLabPlugin) -> None:
        token = "glpat-" + "a" * 20
        assert plugin.redact(token) == "[REDACTED]"

    def test_deploy_token(self, plugin: GitLabPlugin) -> None:
        token = "gldt-" + "b" * 20
        assert plugin.redact(token) == "[REDACTED]"

    def test_runner_token(self, plugin: GitLabPlugin) -> None:
        token = "glrt-" + "c" * 20
        assert plugin.redact(token) == "[REDACTED]"

    def test_ci_job_token(self, plugin: GitLabPlugin) -> None:
        token = "glcbt-" + "d" * 64
        assert plugin.redact(token) == "[REDACTED]"

    def test_feed_token(self, plugin: GitLabPlugin) -> None:
        token = "glft-" + "e" * 20
        assert plugin.redact(token) == "[REDACTED]"

    def test_oauth_token(self, plugin: GitLabPlugin) -> None:
        token = "glsoat-" + "f" * 20
        assert plugin.redact(token) == "[REDACTED]"

    def test_too_short_not_matched(self, plugin: GitLabPlugin) -> None:
        short = "glpat-abc"
        assert plugin.redact(short) == short

    def test_ci_job_token_too_short(self, plugin: GitLabPlugin) -> None:
        short = "glcbt-" + "a" * 30  # needs 64
        assert plugin.redact(short) == short

    def test_embedded_in_text(self, plugin: GitLabPlugin) -> None:
        token = "glpat-" + "x" * 20
        text = f"GITLAB_TOKEN={token} make deploy"
        result = plugin.redact(text)
        assert "glpat-" not in result
        assert "make deploy" in result

    def test_normal_text_unchanged(self, plugin: GitLabPlugin) -> None:
        assert plugin.redact("no gitlab tokens") == "no gitlab tokens"
