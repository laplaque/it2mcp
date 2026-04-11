"""Redaction plugin for generic secret patterns."""

from __future__ import annotations

import re

from ..base import RedactPlugin


class GenericSecretsPlugin(RedactPlugin):
    """Detects and redacts common secret patterns that aren't vendor-specific.

    Covers:
        - OpenAI API keys: sk-xxxx
        - Anthropic API keys: sk-ant-xxxx
        - JWTs: eyJxxx.eyJxxx.xxx
        - Bearer tokens in output: Bearer xxxx
        - Slack tokens: xoxb-, xoxp-, xoxs-, xoxa-
        - Stripe keys: sk_live_, sk_test_, rk_live_, rk_test_
        - SendGrid: SG.xxxx
        - Twilio: SK + 32 hex chars
        - Private key blocks: full PEM/OpenSSH key blocks (header + body + footer)
        - Standalone private key headers (when END marker is absent or truncated)
    """

    @property
    def name(self) -> str:
        return "generic"

    @property
    def description(self) -> str:
        return "Generic secret patterns: JWTs, bearer tokens, common API key formats, private key blocks"

    def patterns(self) -> list[re.Pattern[str]]:
        return [
            # OpenAI
            re.compile(r"sk-[A-Za-z0-9]{20,}T3BlbkFJ[A-Za-z0-9]{20,}"),
            re.compile(r"sk-proj-[A-Za-z0-9_\-]{40,}"),
            # Anthropic
            re.compile(r"sk-ant-[A-Za-z0-9_\-]{40,}"),
            # JWTs (three base64url segments separated by dots)
            re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_\-]{20,}"),
            # Bearer tokens in output (e.g. from curl -v)
            re.compile(r"(?i)Bearer\s+[A-Za-z0-9_\-.]{20,}"),
            # Slack
            re.compile(r"xox[bpsa]-[A-Za-z0-9\-]{10,}"),
            # Stripe
            re.compile(r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}"),
            # SendGrid
            re.compile(r"SG\.[A-Za-z0-9_\-]{22,}\.[A-Za-z0-9_\-]{22,}"),
            # Twilio
            re.compile(r"SK[0-9a-fA-F]{32}"),
            # Full PEM/OpenSSH private key blocks (header + base64 body + footer)
            # Must come before the standalone header pattern so full blocks are
            # replaced as a unit rather than leaving the body exposed.
            re.compile(
                r"-----BEGIN\s[A-Z\s]*PRIVATE\sKEY-----"
                r"[\s\S]*?"
                r"-----END\s[A-Z\s]*PRIVATE\sKEY-----",
                re.MULTILINE,
            ),
            # Standalone private key header (fallback for truncated output
            # where the END marker is absent)
            re.compile(r"-----BEGIN\s[A-Z\s]*PRIVATE\sKEY-----"),
        ]
