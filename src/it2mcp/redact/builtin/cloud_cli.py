"""Redaction plugin for cloud provider CLI token output."""

from __future__ import annotations

import re

from ..base import RedactPlugin


class CloudCLIPlugin(RedactPlugin):
    """Detects and redacts access tokens from cloud provider CLI output.

    Covers:
        - GCP: `gcloud auth print-access-token` outputs a bare ya29.xxx token
        - GCP: `gcloud auth print-identity-token` outputs a bare eyXxx JWT
        - Azure: `az account get-access-token` outputs JSON with accessToken field
        - Azure: `az account get-access-token --query accessToken -o tsv` outputs bare token
        - Kubernetes: service account tokens (long base64 JWTs)
    """

    @property
    def name(self) -> str:
        return "cloud_cli"

    @property
    def description(self) -> str:
        return "Cloud provider CLI tokens: GCP access/identity tokens, Azure access tokens"

    def patterns(self) -> list[re.Pattern[str]]:
        return [
            # GCP access tokens (ya29.xxx format, typically 150+ chars)
            re.compile(r"ya29\.[A-Za-z0-9_\-]{50,}"),
            # Azure accessToken in JSON output
            re.compile(r"(?i)\"accessToken\"\s*:\s*\"[A-Za-z0-9_\-./+=]{50,}\""),
            # Azure bare token output (long base64-like string on its own line,
            # from --query accessToken -o tsv)
            # This is intentionally conservative — only matches when the token
            # looks like an Azure AD JWT (eyJ prefix with 500+ chars)
            re.compile(r"^eyJ[A-Za-z0-9_\-]{500,}$", re.MULTILINE),
        ]
