"""Tests for session_status and session_interrupt tools.

This module tests the pure functions extracted from the MCP tools,
which can be tested without mocking iTerm2.
"""

from __future__ import annotations

import inspect

import pytest

from it2mcp.server import (
    InterruptAction,
    _SHELL_NAMES,
    build_session_status,
    determine_interrupt_action,
    is_at_shell_prompt,
    parse_pid,
)


# ---------------------------------------------------------------------------
# Tests for _SHELL_NAMES constant
# ---------------------------------------------------------------------------


class TestShellNames:
    """Tests for the _SHELL_NAMES constant."""

    def test_contains_common_shells(self) -> None:
        assert "bash" in _SHELL_NAMES
        assert "zsh" in _SHELL_NAMES
        assert "fish" in _SHELL_NAMES
        assert "sh" in _SHELL_NAMES

    def test_contains_login_shell_variants(self) -> None:
        assert "-bash" in _SHELL_NAMES
        assert "-zsh" in _SHELL_NAMES
        assert "-fish" in _SHELL_NAMES
        assert "-sh" in _SHELL_NAMES

    def test_contains_other_shells(self) -> None:
        assert "tcsh" in _SHELL_NAMES
        assert "csh" in _SHELL_NAMES
        assert "ksh" in _SHELL_NAMES
        assert "dash" in _SHELL_NAMES
        assert "ash" in _SHELL_NAMES

    def test_is_frozenset(self) -> None:
        assert isinstance(_SHELL_NAMES, frozenset)

    def test_shell_count(self) -> None:
        # 9 base shells + 4 login variants with dash
        assert len(_SHELL_NAMES) == 13


# ---------------------------------------------------------------------------
# Tests for parse_pid function
# ---------------------------------------------------------------------------


class TestParsePid:
    """Tests for the parse_pid function."""

    def test_valid_pid_string(self) -> None:
        assert parse_pid("1234") == 1234

    def test_empty_string_returns_none(self) -> None:
        assert parse_pid("") is None

    def test_whitespace_only_returns_none(self) -> None:
        # Empty after strip would fail int(), but our impl doesn't strip
        # Let's test what it actually does
        result = parse_pid("   ")
        assert result is None  # Will fail int() conversion

    def test_non_numeric_returns_none(self) -> None:
        assert parse_pid("abc") is None

    def test_float_string_returns_none(self) -> None:
        assert parse_pid("123.45") is None

    def test_negative_number(self) -> None:
        # PIDs are positive, but parse_pid doesn't validate this
        assert parse_pid("-1") == -1

    def test_zero(self) -> None:
        assert parse_pid("0") == 0

    def test_large_pid(self) -> None:
        assert parse_pid("999999") == 999999


# ---------------------------------------------------------------------------
# Tests for is_at_shell_prompt function
# ---------------------------------------------------------------------------


class TestIsAtShellPrompt:
    """Tests for the is_at_shell_prompt function."""

    # Test detection by shell name

    def test_bash_is_shell(self) -> None:
        assert is_at_shell_prompt("bash", 1234, 5678) is True

    def test_zsh_is_shell(self) -> None:
        assert is_at_shell_prompt("zsh", 1234, 5678) is True

    def test_fish_is_shell(self) -> None:
        assert is_at_shell_prompt("fish", 1234, 5678) is True

    def test_sh_is_shell(self) -> None:
        assert is_at_shell_prompt("sh", 1234, 5678) is True

    def test_tcsh_is_shell(self) -> None:
        assert is_at_shell_prompt("tcsh", 1234, 5678) is True

    def test_ksh_is_shell(self) -> None:
        assert is_at_shell_prompt("ksh", 1234, 5678) is True

    def test_dash_is_shell(self) -> None:
        assert is_at_shell_prompt("dash", 1234, 5678) is True

    # Test login shells with leading dash

    def test_login_bash_is_shell(self) -> None:
        assert is_at_shell_prompt("-bash", 1234, 5678) is True

    def test_login_zsh_is_shell(self) -> None:
        assert is_at_shell_prompt("-zsh", 1234, 5678) is True

    def test_login_fish_is_shell(self) -> None:
        assert is_at_shell_prompt("-fish", 1234, 5678) is True

    # Test full paths

    def test_full_path_bash(self) -> None:
        assert is_at_shell_prompt("/bin/bash", 1234, 5678) is True

    def test_full_path_zsh(self) -> None:
        assert is_at_shell_prompt("/usr/bin/zsh", 1234, 5678) is True

    def test_usr_local_bin_fish(self) -> None:
        assert is_at_shell_prompt("/usr/local/bin/fish", 1234, 5678) is True

    def test_full_path_login_bash(self) -> None:
        assert is_at_shell_prompt("/bin/-bash", 1234, 5678) is True

    # Test detection by PID match

    def test_pid_match_indicates_idle(self) -> None:
        # Even unknown shell, same PID means idle
        assert is_at_shell_prompt("unknown_shell", 1234, 1234) is True

    def test_custom_shell_with_pid_match(self) -> None:
        assert is_at_shell_prompt("my_custom_shell", 5678, 5678) is True

    # Test non-shell cases

    def test_npm_is_not_shell(self) -> None:
        assert is_at_shell_prompt("npm", 9999, 1234) is False

    def test_python_is_not_shell(self) -> None:
        assert is_at_shell_prompt("python", 8888, 1234) is False

    def test_vim_is_not_shell(self) -> None:
        assert is_at_shell_prompt("vim", 7777, 1234) is False

    def test_node_is_not_shell(self) -> None:
        assert is_at_shell_prompt("node", 6666, 1234) is False

    def test_curl_is_not_shell(self) -> None:
        assert is_at_shell_prompt("curl", 5555, 1234) is False

    # Test edge cases

    def test_empty_job_name_with_different_pids(self) -> None:
        assert is_at_shell_prompt("", 1234, 5678) is False

    def test_empty_job_name_with_matching_pids(self) -> None:
        assert is_at_shell_prompt("", 1234, 1234) is True

    def test_none_pids(self) -> None:
        # Non-shell name with None PIDs
        assert is_at_shell_prompt("npm", None, None) is False

    def test_shell_name_with_none_pids(self) -> None:
        # Shell name should still be detected
        assert is_at_shell_prompt("bash", None, None) is True

    def test_none_job_pid_only(self) -> None:
        assert is_at_shell_prompt("npm", None, 1234) is False

    def test_none_shell_pid_only(self) -> None:
        assert is_at_shell_prompt("npm", 1234, None) is False


# ---------------------------------------------------------------------------
# Tests for build_session_status function
# ---------------------------------------------------------------------------


class TestBuildSessionStatus:
    """Tests for the build_session_status function."""

    def test_returns_dict_with_all_fields(self) -> None:
        result = build_session_status(
            job_name="bash",
            job_pid=1234,
            shell_pid=1234,
            tty="/dev/ttys001",
            command_line="-bash",
        )

        assert isinstance(result, dict)
        assert "job_name" in result
        assert "job_pid" in result
        assert "shell_pid" in result
        assert "tty" in result
        assert "command_line" in result
        assert "is_at_shell_prompt" in result

    def test_idle_at_bash_prompt(self) -> None:
        result = build_session_status(
            job_name="bash",
            job_pid=1234,
            shell_pid=1234,
            tty="/dev/ttys001",
            command_line="-bash",
        )

        assert result["job_name"] == "bash"
        assert result["job_pid"] == 1234
        assert result["shell_pid"] == 1234
        assert result["tty"] == "/dev/ttys001"
        assert result["command_line"] == "-bash"
        assert result["is_at_shell_prompt"] is True

    def test_busy_running_npm(self) -> None:
        result = build_session_status(
            job_name="npm",
            job_pid=9999,
            shell_pid=1234,
            tty="/dev/ttys002",
            command_line="npm run dev",
        )

        assert result["job_name"] == "npm"
        assert result["job_pid"] == 9999
        assert result["shell_pid"] == 1234
        assert result["command_line"] == "npm run dev"
        assert result["is_at_shell_prompt"] is False

    def test_with_none_pids(self) -> None:
        result = build_session_status(
            job_name="bash",
            job_pid=None,
            shell_pid=None,
            tty="",
            command_line="",
        )

        assert result["job_pid"] is None
        assert result["shell_pid"] is None
        assert result["is_at_shell_prompt"] is True  # bash is a shell

    def test_empty_values(self) -> None:
        result = build_session_status(
            job_name="",
            job_pid=None,
            shell_pid=None,
            tty="",
            command_line="",
        )

        assert result["job_name"] == ""
        assert result["is_at_shell_prompt"] is False


# ---------------------------------------------------------------------------
# Tests for InterruptAction class
# ---------------------------------------------------------------------------


class TestInterruptAction:
    """Tests for the InterruptAction class."""

    def test_etx_fallback_action(self) -> None:
        action = InterruptAction(
            InterruptAction.ETX_FALLBACK,
            message="test message",
        )
        assert action.action == "etx_fallback"
        assert action.job_pid is None
        assert action.message == "test message"

    def test_no_op_action(self) -> None:
        action = InterruptAction(
            InterruptAction.NO_OP,
            job_pid=1234,
            message="at prompt",
        )
        assert action.action == "no_op"
        assert action.job_pid == 1234
        assert action.message == "at prompt"

    def test_sigint_action(self) -> None:
        action = InterruptAction(
            InterruptAction.SIGINT,
            job_pid=9999,
            message="sending sigint",
        )
        assert action.action == "sigint"
        assert action.job_pid == 9999
        assert action.message == "sending sigint"

    def test_action_constants(self) -> None:
        assert InterruptAction.ETX_FALLBACK == "etx_fallback"
        assert InterruptAction.NO_OP == "no_op"
        assert InterruptAction.SIGINT == "sigint"


# ---------------------------------------------------------------------------
# Tests for determine_interrupt_action function
# ---------------------------------------------------------------------------


class TestDetermineInterruptAction:
    """Tests for the determine_interrupt_action function."""

    def test_no_job_pid_returns_etx_fallback(self) -> None:
        action = determine_interrupt_action(
            job_pid=None,
            shell_pid=1234,
            session_id="test-session",
        )

        assert action.action == InterruptAction.ETX_FALLBACK
        assert action.job_pid is None
        assert "test-session" in action.message
        assert "ETX" in action.message or "Ctrl+C" in action.message

    def test_both_pids_none_returns_etx_fallback(self) -> None:
        action = determine_interrupt_action(
            job_pid=None,
            shell_pid=None,
            session_id="session-123",
        )

        assert action.action == InterruptAction.ETX_FALLBACK

    def test_pid_match_returns_no_op(self) -> None:
        action = determine_interrupt_action(
            job_pid=1234,
            shell_pid=1234,
            session_id="idle-session",
        )

        assert action.action == InterruptAction.NO_OP
        assert action.job_pid == 1234
        assert "idle-session" in action.message
        assert "shell prompt" in action.message

    def test_different_pids_returns_sigint(self) -> None:
        action = determine_interrupt_action(
            job_pid=9999,
            shell_pid=1234,
            session_id="busy-session",
        )

        assert action.action == InterruptAction.SIGINT
        assert action.job_pid == 9999
        assert "busy-session" in action.message
        assert "SIGINT" in action.message
        assert "9999" in action.message

    def test_session_id_in_all_messages(self) -> None:
        session_id = "unique-test-id-xyz"

        action1 = determine_interrupt_action(None, 1234, session_id)
        assert session_id in action1.message

        action2 = determine_interrupt_action(1234, 1234, session_id)
        assert session_id in action2.message

        action3 = determine_interrupt_action(9999, 1234, session_id)
        assert session_id in action3.message


# ---------------------------------------------------------------------------
# Tests for security tier configuration
# ---------------------------------------------------------------------------


class TestSecurityTiers:
    """Tests for correct security tier assignment."""

    def test_session_status_is_read_tier(self) -> None:
        from it2mcp.security import TOOL_TIERS, Tier

        assert TOOL_TIERS["session_status"] == Tier.READ

    def test_session_interrupt_is_interact_tier(self) -> None:
        from it2mcp.security import TOOL_TIERS, Tier

        assert TOOL_TIERS["session_interrupt"] == Tier.INTERACT

    def test_session_status_not_destructive(self) -> None:
        from it2mcp.security import TOOL_TIERS, Tier

        assert TOOL_TIERS["session_status"] != Tier.DESTRUCTIVE

    def test_session_interrupt_not_destructive(self) -> None:
        from it2mcp.security import TOOL_TIERS, Tier

        assert TOOL_TIERS["session_interrupt"] != Tier.DESTRUCTIVE


# ---------------------------------------------------------------------------
# Tests for batch handler registration
# ---------------------------------------------------------------------------


class TestBatchHandlerRegistration:
    """Tests for batch handler dict registration."""

    def test_session_status_in_batch_handlers(self) -> None:
        from it2mcp.server import _BATCH_HANDLERS, _b_session_status

        assert "session_status" in _BATCH_HANDLERS
        assert _BATCH_HANDLERS["session_status"] == _b_session_status

    def test_session_interrupt_in_batch_handlers(self) -> None:
        from it2mcp.server import _BATCH_HANDLERS, _b_session_interrupt

        assert "session_interrupt" in _BATCH_HANDLERS
        assert _BATCH_HANDLERS["session_interrupt"] == _b_session_interrupt

    def test_batch_handlers_are_callable(self) -> None:
        from it2mcp.server import _BATCH_HANDLERS

        assert callable(_BATCH_HANDLERS["session_status"])
        assert callable(_BATCH_HANDLERS["session_interrupt"])


# ---------------------------------------------------------------------------
# Tests for MCP tool registration
# ---------------------------------------------------------------------------


class TestMCPToolRegistration:
    """Tests for MCP tool function existence and signatures."""

    def test_session_status_tool_exists(self) -> None:
        from it2mcp.server import session_status

        assert callable(session_status)

    def test_session_interrupt_tool_exists(self) -> None:
        from it2mcp.server import session_interrupt

        assert callable(session_interrupt)

    def test_session_status_is_async(self) -> None:
        from it2mcp.server import session_status

        assert inspect.iscoroutinefunction(session_status)

    def test_session_interrupt_is_async(self) -> None:
        from it2mcp.server import session_interrupt

        assert inspect.iscoroutinefunction(session_interrupt)
