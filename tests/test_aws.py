"""Tests for the AWS redaction plugin."""

from __future__ import annotations

import pytest

from it2mcp.redact.builtin.aws import AWSPlugin


@pytest.fixture
def plugin() -> AWSPlugin:
    return AWSPlugin()


class TestAWSPlugin:
    def test_name(self, plugin: AWSPlugin) -> None:
        assert plugin.name == "aws"

    def test_akia_access_key(self, plugin: AWSPlugin) -> None:
        key = "AKIAIOSFODNN7EXAMPLE"
        assert "[REDACTED]" in plugin.redact(f"key: {key}")
        assert "AKIA" not in plugin.redact(key)

    def test_asia_temporary_key(self, plugin: AWSPlugin) -> None:
        key = "ASIA1234567890ABCDEF"
        assert "ASIA" not in plugin.redact(key)

    def test_secret_access_key_with_equals(self, plugin: AWSPlugin) -> None:
        line = "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        result = plugin.redact(line)
        assert "wJalrXUtnFEMI" not in result

    def test_secret_access_key_with_colon(self, plugin: AWSPlugin) -> None:
        line = "secret_access_key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        result = plugin.redact(line)
        assert "wJalrXUtnFEMI" not in result

    def test_session_token(self, plugin: AWSPlugin) -> None:
        token = "A" * 120
        line = f"aws_session_token = {token}"
        result = plugin.redact(line)
        assert token not in result

    def test_short_akia_not_matched(self, plugin: AWSPlugin) -> None:
        short = "AKIA1234"  # only 8 after prefix, need 16
        assert plugin.redact(short) == short

    def test_normal_text_unchanged(self, plugin: AWSPlugin) -> None:
        assert plugin.redact("no aws keys here") == "no aws keys here"

    def test_embedded_in_env_output(self, plugin: AWSPlugin) -> None:
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\nAWS_DEFAULT_REGION=us-east-1"
        result = plugin.redact(text)
        assert "AKIA" not in result
        assert "us-east-1" in result
