"""Tests for the cloud CLI redaction plugin."""

from __future__ import annotations

import pytest

from it2mcp.redact.builtin.cloud_cli import CloudCLIPlugin


@pytest.fixture
def plugin() -> CloudCLIPlugin:
    return CloudCLIPlugin()


class TestGCP:
    def test_gcloud_access_token(self, plugin: CloudCLIPlugin) -> None:
        token = "ya29." + "A" * 100
        assert "ya29." not in plugin.redact(token)

    def test_gcloud_access_token_in_output(self, plugin: CloudCLIPlugin) -> None:
        text = "$ gcloud auth print-access-token\nya29." + "B" * 150 + "\n$"
        result = plugin.redact(text)
        assert "ya29." not in result
        assert "gcloud auth" in result

    def test_short_ya29_not_matched(self, plugin: CloudCLIPlugin) -> None:
        short = "ya29.short"
        assert plugin.redact(short) == short


class TestAzure:
    def test_azure_access_token_json(self, plugin: CloudCLIPlugin) -> None:
        text = '{"accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.' + 'A' * 100 + '"}'
        result = plugin.redact(text)
        assert "eyJhbGci" not in result

    def test_azure_bare_token_tsv(self, plugin: CloudCLIPlugin) -> None:
        # az account get-access-token --query accessToken -o tsv outputs bare token
        token = "eyJ" + "C" * 600
        result = plugin.redact(token)
        assert "eyJ" not in result

    def test_short_eyj_not_matched(self, plugin: CloudCLIPlugin) -> None:
        """Short eyJ strings should not be caught by the Azure bare token pattern."""
        short = "eyJhbGciOiJIUzI1NiJ9"
        assert plugin.redact(short) == short


class TestPassthrough:
    def test_normal_text_unchanged(self, plugin: CloudCLIPlugin) -> None:
        assert plugin.redact("hello world") == "hello world"

    def test_gcloud_command_itself_not_matched(self, plugin: CloudCLIPlugin) -> None:
        cmd = "gcloud auth print-access-token"
        assert plugin.redact(cmd) == cmd
