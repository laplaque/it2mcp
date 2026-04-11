"""Tests for the generic secrets redaction plugin."""

from __future__ import annotations

import pytest

from it2mcp.redact.builtin.generic import GenericSecretsPlugin


@pytest.fixture
def plugin() -> GenericSecretsPlugin:
    return GenericSecretsPlugin()


class TestOpenAI:
    def test_classic_openai_key(self, plugin: GenericSecretsPlugin) -> None:
        key = "sk-" + "a" * 20 + "T3BlbkFJ" + "b" * 20
        assert "sk-" not in plugin.redact(key)

    def test_project_openai_key(self, plugin: GenericSecretsPlugin) -> None:
        key = "sk-proj-" + "c" * 40
        assert "sk-proj-" not in plugin.redact(key)


class TestAnthropic:
    def test_anthropic_key(self, plugin: GenericSecretsPlugin) -> None:
        key = "sk-ant-" + "d" * 40
        assert "sk-ant-" not in plugin.redact(key)

    def test_too_short_anthropic_key(self, plugin: GenericSecretsPlugin) -> None:
        short = "sk-ant-abc123"
        assert plugin.redact(short) == short


class TestJWT:
    def test_jwt_redacted(self, plugin: GenericSecretsPlugin) -> None:
        jwt = "eyJ" + "A" * 30 + ".eyJ" + "B" * 30 + "." + "C" * 30
        assert "eyJ" not in plugin.redact(jwt)

    def test_partial_jwt_not_matched(self, plugin: GenericSecretsPlugin) -> None:
        partial = "eyJhbGciOi.notajwt"
        assert plugin.redact(partial) == partial


class TestBearer:
    def test_bearer_token(self, plugin: GenericSecretsPlugin) -> None:
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9token1234"
        result = plugin.redact(text)
        assert "Bearer" not in result or "eyJ" not in result

    def test_bearer_case_insensitive(self, plugin: GenericSecretsPlugin) -> None:
        text = "bearer ABCDEFGHIJKLMNOPQRSTU12345"
        result = plugin.redact(text)
        assert "ABCDEFG" not in result


class TestSlack:
    def test_slack_bot_token(self, plugin: GenericSecretsPlugin) -> None:
        token = "xoxb-" + "1234567890-" * 3
        assert "xoxb-" not in plugin.redact(token)

    def test_slack_user_token(self, plugin: GenericSecretsPlugin) -> None:
        token = "xoxp-" + "abcdefghij"
        assert "xoxp-" not in plugin.redact(token)


class TestStripe:
    def test_stripe_live_secret(self, plugin: GenericSecretsPlugin) -> None:
        key = "sk_live_" + "a" * 24
        assert "sk_live_" not in plugin.redact(key)

    def test_stripe_test_secret(self, plugin: GenericSecretsPlugin) -> None:
        key = "sk_test_" + "b" * 24
        assert "sk_test_" not in plugin.redact(key)

    def test_stripe_restricted_live(self, plugin: GenericSecretsPlugin) -> None:
        key = "rk_live_" + "c" * 24
        assert "rk_live_" not in plugin.redact(key)


class TestSendGrid:
    def test_sendgrid_key(self, plugin: GenericSecretsPlugin) -> None:
        key = "SG." + "A" * 22 + "." + "B" * 22
        assert "SG." not in plugin.redact(key)


class TestTwilio:
    def test_twilio_key(self, plugin: GenericSecretsPlugin) -> None:
        key = "SK" + "a" * 32
        assert "SK" not in plugin.redact(key) or len(plugin.redact(key)) < len(key)

    def test_short_sk_not_matched(self, plugin: GenericSecretsPlugin) -> None:
        short = "SKabc123"  # only 6 hex, need 32
        assert plugin.redact(short) == short


class TestPEM:
    def test_pem_rsa_full_block(self, plugin: GenericSecretsPlugin) -> None:
        text = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF9PbnGcY\n"
            "7GkmUVhOv/eN3MIWEg==\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = plugin.redact(text)
        assert "MIIEpA" not in result
        assert "PRIVATE KEY" not in result

    def test_pem_ec_full_block(self, plugin: GenericSecretsPlugin) -> None:
        text = (
            "-----BEGIN EC PRIVATE KEY-----\n"
            "MHQCAQEEIBkg0K3n5wPsTEfy8bR2KU\n"
            "-----END EC PRIVATE KEY-----"
        )
        result = plugin.redact(text)
        assert "MHQCAQEEIBkg" not in result

    def test_openssh_full_block(self, plugin: GenericSecretsPlugin) -> None:
        text = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "b3BlbnNzaC1rZXktdjEAAAAABG5vbmU\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
        result = plugin.redact(text)
        assert "b3Blbn" not in result

    def test_encrypted_private_key(self, plugin: GenericSecretsPlugin) -> None:
        text = (
            "-----BEGIN ENCRYPTED PRIVATE KEY-----\n"
            "MIIFHDBOBgkqhkiG9w0BBQ0wQTApBg\n"
            "-----END ENCRYPTED PRIVATE KEY-----"
        )
        result = plugin.redact(text)
        assert "MIIFHDBOBg" not in result

    def test_dsa_private_key(self, plugin: GenericSecretsPlugin) -> None:
        text = (
            "-----BEGIN DSA PRIVATE KEY-----\n"
            "MIIBugIBAAKBgQC3teJGAD0t\n"
            "-----END DSA PRIVATE KEY-----"
        )
        result = plugin.redact(text)
        assert "MIIBug" not in result

    def test_pem_header_only_still_redacted(self, plugin: GenericSecretsPlugin) -> None:
        """Even a header without a matching END should be caught."""
        text = "found key: -----BEGIN RSA PRIVATE KEY-----"
        result = plugin.redact(text)
        assert "PRIVATE KEY" not in result

    def test_key_embedded_in_text(self, plugin: GenericSecretsPlugin) -> None:
        text = (
            "Config loaded.\n"
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF9PbnGcY\n"
            "-----END RSA PRIVATE KEY-----\n"
            "Server started on port 8080."
        )
        result = plugin.redact(text)
        assert "MIIEpA" not in result
        assert "Config loaded." in result
        assert "Server started" in result


class TestPassthrough:
    def test_normal_text_unchanged(self, plugin: GenericSecretsPlugin) -> None:
        assert plugin.redact("hello world") == "hello world"

    def test_sk_prefix_alone_not_matched(self, plugin: GenericSecretsPlugin) -> None:
        assert plugin.redact("sk-short") == "sk-short"
