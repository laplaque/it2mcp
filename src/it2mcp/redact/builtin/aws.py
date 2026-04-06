"""Redaction plugin for AWS credentials."""

from __future__ import annotations

import re

from ..base import RedactPlugin


class AWSPlugin(RedactPlugin):
    """Detects and redacts AWS access keys and secret keys.

    Covers:
        - Access Key IDs: AKIA...
        - Secret Access Keys: 40-char base64 strings preceded by common key labels
        - Session tokens: long base64 strings preceded by session token labels
    """

    @property
    def name(self) -> str:
        return "aws"

    @property
    def description(self) -> str:
        return "AWS access key IDs, secret access keys, and session tokens"

    def patterns(self) -> list[re.Pattern[str]]:
        return [
            # Access Key IDs (always start with AKIA, ABIA, ACCA, or ASIA)
            re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}"),
            # Secret Access Keys: 40-char base64 when preceded by a label
            re.compile(
                r"(?i)(?:aws_secret_access_key|secret_access_key|aws_secret)\s*[=:]\s*"
                r"([A-Za-z0-9/+=]{40})"
            ),
            # Session tokens
            re.compile(
                r"(?i)(?:aws_session_token|session_token)\s*[=:]\s*"
                r"([A-Za-z0-9/+=]{100,})"
            ),
        ]
