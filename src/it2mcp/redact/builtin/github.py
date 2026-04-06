"""Redaction plugin for GitHub tokens."""

from __future__ import annotations

import re

from ..base import RedactPlugin


class GitHubPlugin(RedactPlugin):
    """Detects and redacts GitHub personal access tokens and OAuth tokens.

    Covers:
        - Classic PATs: ghp_xxxx
        - Fine-grained PATs: github_pat_xxxx
        - OAuth tokens: gho_xxxx
        - User-to-server tokens: ghu_xxxx
        - Server-to-server tokens: ghs_xxxx
        - Refresh tokens: ghr_xxxx
    """

    @property
    def name(self) -> str:
        return "github"

    @property
    def description(self) -> str:
        return "GitHub personal access tokens, OAuth tokens, and app tokens"

    def patterns(self) -> list[re.Pattern[str]]:
        return [
            re.compile(r"ghp_[A-Za-z0-9_]{36,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{82,}"),
            re.compile(r"gho_[A-Za-z0-9_]{36,}"),
            re.compile(r"ghu_[A-Za-z0-9_]{36,}"),
            re.compile(r"ghs_[A-Za-z0-9_]{36,}"),
            re.compile(r"ghr_[A-Za-z0-9_]{36,}"),
        ]
