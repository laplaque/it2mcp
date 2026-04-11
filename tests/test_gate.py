"""Tests for the command confirmation gate."""

from __future__ import annotations

import pytest

from it2mcp.gate import GateResult, check_command, match_pattern, _extract_command_prefix, _session_allowed


class TestMatchPattern:
    def test_exact_match(self) -> None:
        assert match_pattern("pwd", ["pwd"])

    def test_exact_no_match(self) -> None:
        assert not match_pattern("ls", ["pwd"])

    def test_prefix_match(self) -> None:
        assert match_pattern("sudo rm -rf /", ["sudo"])

    def test_prefix_no_partial_word(self) -> None:
        """'sudo' should not match 'sudoku'."""
        assert not match_pattern("sudoku", ["sudo"])

    def test_wildcard_match(self) -> None:
        assert match_pattern("git status", ["git *"])

    def test_wildcard_match_with_args(self) -> None:
        assert match_pattern("git diff --cached", ["git *"])

    def test_wildcard_no_match(self) -> None:
        assert not match_pattern("hg status", ["git *"])

    def test_wildcard_bare_command(self) -> None:
        """'git *' should not match bare 'git' (no space + args)."""
        assert not match_pattern("git", ["git *"])

    def test_multiple_patterns(self) -> None:
        patterns = ["git *", "ls *", "pwd"]
        assert match_pattern("git log", patterns)
        assert match_pattern("ls -la", patterns)
        assert match_pattern("pwd", patterns)
        assert not match_pattern("rm -rf /", patterns)

    def test_whitespace_handling(self) -> None:
        assert match_pattern("  git status  ", ["git *"])

    def test_empty_patterns(self) -> None:
        assert not match_pattern("anything", [])


class TestExtractCommandPrefix:
    def test_two_word_command(self) -> None:
        assert _extract_command_prefix("go test -v ./...") == "go test"

    def test_single_word(self) -> None:
        assert _extract_command_prefix("pwd") == "pwd"

    def test_long_command(self) -> None:
        assert _extract_command_prefix("git diff --cached --stat") == "git diff"


class TestCheckCommand:
    """Tests for check_command using monkeypatched config."""

    @pytest.fixture(autouse=True)
    def _reset_session_allowed(self) -> None:
        _session_allowed.clear()

    @pytest.fixture
    def mock_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set up a mock config with allow/deny lists."""
        from it2mcp import security

        class MockConfig:
            commands = {
                "enabled": True,
                "timeout": 30,
                "allow": ["git *", "ls *", "pwd"],
                "deny": ["sudo *", "ssh *", "gh auth *"],
            }
            permissions = set()
            require_tag = True
            audit_log = None
            redact_engine = security.RedactEngine(enabled=False)
            _raw = {}

        monkeypatch.setattr(security, "_config", MockConfig())

    def test_allowed_command(self, mock_config: None) -> None:
        assert check_command("git status") == GateResult.ALLOW

    def test_denied_command(self, mock_config: None) -> None:
        assert check_command("sudo rm -rf /") == GateResult.DENY

    def test_denied_auth_command(self, mock_config: None) -> None:
        assert check_command("gh auth token") == GateResult.DENY

    def test_unknown_command_asks(self, mock_config: None) -> None:
        assert check_command("docker run hello") == GateResult.ASK

    def test_allowed_exact(self, mock_config: None) -> None:
        assert check_command("pwd") == GateResult.ALLOW

    def test_session_allowed(self, mock_config: None) -> None:
        _session_allowed.add("docker *")
        assert check_command("docker run hello") == GateResult.ALLOW

    def test_deny_takes_precedence(self, mock_config: None) -> None:
        """Deny list is checked before allow list."""
        _session_allowed.add("sudo *")
        assert check_command("sudo whoami") == GateResult.DENY

    def test_disabled_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from it2mcp import security

        class MockConfig:
            commands = {"enabled": False, "timeout": 30, "allow": [], "deny": []}
            permissions = set()
            require_tag = True
            audit_log = None
            redact_engine = security.RedactEngine(enabled=False)
            _raw = {}

        monkeypatch.setattr(security, "_config", MockConfig())
        assert check_command("anything at all") == GateResult.ALLOW
