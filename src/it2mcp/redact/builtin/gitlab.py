"""Redaction plugin for GitLab tokens."""

from __future__ import annotations

import re

from ..base import RedactPlugin


class GitLabPlugin(RedactPlugin):
    """Detects and redacts GitLab personal access tokens, deploy tokens, and pipeline tokens.

    Covers:
        - Personal access tokens: glpat-xxxx
        - Deploy tokens: gldt-xxxx
        - Runner tokens: glrt-xxxx
        - CI job tokens: glcbt-xxxx
        - Feed tokens: glft-xxxx
        - OAuth tokens: glsoat-xxxx
    """

    @property
    def name(self) -> str:
        return "gitlab"

    @property
    def description(self) -> str:
        return "GitLab personal access tokens, deploy tokens, and pipeline tokens"

    def patterns(self) -> list[re.Pattern[str]]:
        return [
            re.compile(r"glpat-[A-Za-z0-9_\-]{20,}"),
            re.compile(r"gldt-[A-Za-z0-9_\-]{20,}"),
            re.compile(r"glrt-[A-Za-z0-9_\-]{20,}"),
            re.compile(r"glcbt-[A-Za-z0-9_\-]{64,}"),
            re.compile(r"glft-[A-Za-z0-9_\-]{20,}"),
            re.compile(r"glsoat-[A-Za-z0-9_\-]{20,}"),
        ]
