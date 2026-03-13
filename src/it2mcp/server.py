"""MCP server for controlling iTerm2.

Wraps the iterm2 Python API and exposes iTerm2 operations as MCP tools.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import iterm2
from mcp.server.fastmcp import FastMCP

from .security import (
    Tier,
    assert_permission,
    audit_log,
    check_session_allowed,
    check_sessions_allowed,
    is_session_enabled,
)

T = TypeVar("T")

mcp = FastMCP(
    "it2mcp",
    instructions="Control iTerm2 from MCP — manage sessions, windows, tabs, profiles, and more.",
)


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

async def _run(func: Callable[..., Awaitable[T]], **kwargs: Any) -> T:
    """Create a connection to iTerm2, run *func*, and return its result."""
    connection = await iterm2.Connection.async_create()
    app = await iterm2.async_get_app(connection)
    return await func(connection=connection, app=app, **kwargs)


# ---------------------------------------------------------------------------
# Session helpers (mirrors it2/core/session_handler.py)
# ---------------------------------------------------------------------------

_UUID_RE = r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
_ITERM_SID_RE = re.compile(rf"^w\d+t\d+p\d+:(?P<uuid>{_UUID_RE})$")
_TERMID_RE = re.compile(rf"^w\d+t\d+p\d+\.(?P<uuid>{_UUID_RE})$")


def _normalize_session_id(sid: str | None) -> str | None:
    if sid is None:
        return None
    for pat in (_ITERM_SID_RE, _TERMID_RE):
        m = pat.match(sid)
        if m:
            return m.group("uuid")
    return sid


def _get_session_by_id(app: iterm2.App, sid: str) -> iterm2.Session | None:
    normalized = _normalize_session_id(sid)
    if normalized is None:
        return None
    session = app.get_session_by_id(normalized)
    if session:
        return session
    if normalized != sid:
        return app.get_session_by_id(sid)
    return None


def _get_all_sessions(app: iterm2.App) -> list[iterm2.Session]:
    sessions: list[iterm2.Session] = []
    for window in app.windows:
        for tab in window.tabs:
            sessions.extend(tab.sessions)
    return sessions


def _get_active_session(app: iterm2.App) -> iterm2.Session:
    window = app.current_terminal_window
    if not window:
        raise RuntimeError("No active window")
    tab = window.current_tab
    if not tab:
        raise RuntimeError("No active tab")
    session = tab.current_session
    if not session:
        raise RuntimeError("No active session")
    return session


def _resolve_sessions(
    app: iterm2.App,
    session_id: str | None = None,
    all_sessions: bool = False,
) -> list[iterm2.Session]:
    if all_sessions:
        return _get_all_sessions(app)
    if session_id:
        s = _get_session_by_id(app, session_id)
        if not s:
            raise RuntimeError(f"Session '{session_id}' not found")
        return [s]
    return [_get_active_session(app)]


def _find_window(app: iterm2.App, window_id: str | None) -> iterm2.Window:
    if window_id:
        for w in app.windows:
            if w.window_id == window_id:
                return w
        raise RuntimeError(f"Window '{window_id}' not found")
    w = app.current_terminal_window
    if not w:
        raise RuntimeError("No active window")
    return w


def _find_tab(app: iterm2.App, tab_id: str | None) -> iterm2.Tab:
    if tab_id:
        for w in app.windows:
            for t in w.tabs:
                if t.tab_id == tab_id:
                    return t
        raise RuntimeError(f"Tab '{tab_id}' not found")
    w = _find_window(app, None)
    t = w.current_tab
    if not t:
        raise RuntimeError("No active tab")
    return t


# ---------------------------------------------------------------------------
# Session info helper
# ---------------------------------------------------------------------------

async def _session_info(session: iterm2.Session) -> dict[str, Any]:
    return {
        "id": session.session_id,
        "name": await session.async_get_variable("session.name") or "",
        "title": await session.async_get_variable("session.title") or "",
        "tty": await session.async_get_variable("session.tty") or "",
        "rows": session.grid_size.height,
        "cols": session.grid_size.width,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SESSION TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def session_list() -> str:
    """List all iTerm2 sessions with their IDs, names, titles, sizes, TTYs, and mcp_enabled status.

    Shows all sessions regardless of mcp_enabled status so you can see which
    sessions need to be tagged. Only mcp_enabled sessions can be targeted by
    other tools.

    To enable a session for MCP access, run in that session's terminal:
        it2 session set-var user.mcp_enabled true
    """
    assert_permission("session_list")

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        data = []
        for window in app.windows:
            for tab in window.tabs:
                for session in tab.sessions:
                    info = await _session_info(session)
                    info["window_id"] = window.window_id
                    info["tab_id"] = tab.tab_id
                    info["mcp_enabled"] = await is_session_enabled(session)
                    data.append(info)
        result = json.dumps(data, indent=2)
        audit_log("session_list", result=f"{len(data)} sessions")
        return result

    return await _run(_impl)


@mcp.tool()
async def session_send(text: str, session_id: str | None = None, all_sessions: bool = False) -> str:
    """Send text to an iTerm2 session without pressing Enter.

    Args:
        text: The text to send.
        session_id: Target session ID. Omit for the active session.
        all_sessions: If true, send to every session.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = _resolve_sessions(app, session_id, all_sessions)
        await check_sessions_allowed(sessions)
        for s in sessions:
            await s.async_send_text(text)
        result = f"Sent text to {len(sessions)} session(s)"
        audit_log("session_send", {"text": text, "session_id": session_id, "all": all_sessions}, result=result)
        return result

    assert_permission("session_send")
    return await _run(_impl)


@mcp.tool()
async def session_run(command: str, session_id: str | None = None, all_sessions: bool = False) -> str:
    """Execute a command in an iTerm2 session (sends text + Enter).

    Args:
        command: The command string to execute.
        session_id: Target session ID. Omit for the active session.
        all_sessions: If true, run in every session.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = _resolve_sessions(app, session_id, all_sessions)
        await check_sessions_allowed(sessions)
        for s in sessions:
            await s.async_send_text(command + "\r")
        result = f"Executed command in {len(sessions)} session(s)"
        audit_log("session_run", {"command": command, "session_id": session_id, "all": all_sessions}, result=result)
        return result

    assert_permission("session_run")
    return await _run(_impl)


@mcp.tool()
async def session_read(session_id: str | None = None, lines: int | None = None) -> str:
    """Read the visible screen contents of an iTerm2 session.

    Args:
        session_id: Target session ID. Omit for the active session.
        lines: Number of lines to return from the bottom. Omit for all visible lines.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = _resolve_sessions(app, session_id)
        await check_sessions_allowed(sessions)
        session = sessions[0]
        contents = await session.async_get_screen_contents()
        text_lines = [contents.line(i).string for i in range(contents.number_of_lines)]
        if lines is not None:
            text_lines = text_lines[-lines:] if lines < len(text_lines) else text_lines
        result = "\n".join(text_lines)
        audit_log("session_read", {"session_id": session_id, "lines": lines})
        return result

    assert_permission("session_read")
    return await _run(_impl)


@mcp.tool()
async def session_split(
    vertical: bool = False,
    session_id: str | None = None,
    profile: str | None = None,
) -> str:
    """Split an iTerm2 session into a new pane.

    Args:
        vertical: If true, split vertically (side by side). Default is horizontal (top/bottom).
        session_id: Target session ID. Omit for the active session.
        profile: Profile name to use for the new pane.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = _resolve_sessions(app, session_id)
        await check_sessions_allowed(sessions)
        target = sessions[0]
        new_session = await target.async_split_pane(vertical=vertical, profile=profile)
        if new_session:
            result = json.dumps({"new_session_id": new_session.session_id})
            audit_log("session_split", {"vertical": vertical, "session_id": session_id}, result=result)
            return result
        raise RuntimeError("Failed to split pane")

    assert_permission("session_split")
    return await _run(_impl)


@mcp.tool()
async def session_close(session_id: str | None = None) -> str:
    """Close an iTerm2 session.

    Args:
        session_id: Target session ID. Omit for the active session.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = _resolve_sessions(app, session_id)
        await check_sessions_allowed(sessions)
        target = sessions[0]
        sid = target.session_id
        await target.async_close()
        result = f"Closed session {sid}"
        audit_log("session_close", {"session_id": sid}, result=result)
        return result

    assert_permission("session_close")
    return await _run(_impl)


@mcp.tool()
async def session_restart(session_id: str | None = None) -> str:
    """Restart an iTerm2 session.

    Args:
        session_id: Target session ID. Omit for the active session.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = _resolve_sessions(app, session_id)
        await check_sessions_allowed(sessions)
        target = sessions[0]
        await target.async_restart()
        result = f"Restarted session {target.session_id}"
        audit_log("session_restart", {"session_id": target.session_id}, result=result)
        return result

    assert_permission("session_restart")
    return await _run(_impl)


@mcp.tool()
async def session_focus(session_id: str) -> str:
    """Focus (activate) a specific iTerm2 session.

    Args:
        session_id: The session ID to focus.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        s = _get_session_by_id(app, session_id)
        if not s:
            raise RuntimeError(f"Session '{session_id}' not found")
        await check_session_allowed(s)
        await s.async_activate()
        result = f"Focused session {session_id}"
        audit_log("session_focus", {"session_id": session_id}, result=result)
        return result

    assert_permission("session_focus")
    return await _run(_impl)


@mcp.tool()
async def session_clear(session_id: str | None = None) -> str:
    """Clear the screen of an iTerm2 session (sends Ctrl+L).

    Args:
        session_id: Target session ID. Omit for the active session.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = _resolve_sessions(app, session_id)
        await check_sessions_allowed(sessions)
        for s in sessions:
            await s.async_send_text("\x0c")
        result = f"Cleared {len(sessions)} session(s)"
        audit_log("session_clear", {"session_id": session_id}, result=result)
        return result

    assert_permission("session_clear")
    return await _run(_impl)


@mcp.tool()
async def session_set_name(name: str, session_id: str | None = None) -> str:
    """Set the name of an iTerm2 session.

    Args:
        name: The new session name.
        session_id: Target session ID. Omit for the active session.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = _resolve_sessions(app, session_id)
        await check_sessions_allowed(sessions)
        target = sessions[0]
        await target.async_set_name(name)
        result = f"Session name set to: {name}"
        audit_log("session_set_name", {"name": name, "session_id": session_id}, result=result)
        return result

    assert_permission("session_set_name")
    return await _run(_impl)


@mcp.tool()
async def session_get_variable(variable: str, session_id: str | None = None) -> str:
    """Get the value of an iTerm2 session variable.

    Args:
        variable: The variable name (e.g. "session.name", "session.path").
        session_id: Target session ID. Omit for the active session.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = _resolve_sessions(app, session_id)
        await check_sessions_allowed(sessions)
        target = sessions[0]
        value = await target.async_get_variable(variable)
        audit_log("session_get_variable", {"variable": variable, "session_id": session_id})
        if value is not None:
            return str(value)
        return f"Variable '{variable}' not set"

    assert_permission("session_get_variable")
    return await _run(_impl)


@mcp.tool()
async def session_set_variable(variable: str, value: str, session_id: str | None = None) -> str:
    """Set the value of an iTerm2 session variable.

    Args:
        variable: The variable name.
        value: The value to set.
        session_id: Target session ID. Omit for the active session.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = _resolve_sessions(app, session_id)
        await check_sessions_allowed(sessions)
        target = sessions[0]
        await target.async_set_variable(variable, value)
        result = f"Set {variable} = {value}"
        audit_log("session_set_variable", {"variable": variable, "value": value, "session_id": session_id}, result=result)
        return result

    assert_permission("session_set_variable")
    return await _run(_impl)


# ═══════════════════════════════════════════════════════════════════════════
# WINDOW TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def window_list() -> str:
    """List all iTerm2 windows with their IDs, tab counts, positions, sizes, and fullscreen state."""

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        data = []
        for window in app.windows:
            frame = await window.async_get_frame()
            data.append({
                "id": window.window_id,
                "tabs": len(window.tabs),
                "x": frame.origin.x,
                "y": frame.origin.y,
                "width": frame.size.width,
                "height": frame.size.height,
                "is_fullscreen": await window.async_get_fullscreen(),
            })
        return json.dumps(data, indent=2)

    return await _run(_impl)


@mcp.tool()
async def window_new(profile: str | None = None, command: str | None = None) -> str:
    """Create a new iTerm2 window.

    Args:
        profile: Profile name to use. Omit for the default profile.
        command: Command to run in the new window.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        window = await iterm2.Window.async_create(
            connection, profile=profile, command=command  # type: ignore[arg-type]
        )
        if window:
            return json.dumps({"window_id": window.window_id})
        raise RuntimeError("Failed to create window")

    return await _run(_impl)


@mcp.tool()
async def window_close(window_id: str | None = None) -> str:
    """Close an iTerm2 window.

    Args:
        window_id: The window ID to close. Omit for the current window.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        window = _find_window(app, window_id)
        wid = window.window_id
        await window.async_close()
        return f"Closed window {wid}"

    return await _run(_impl)


@mcp.tool()
async def window_focus(window_id: str) -> str:
    """Focus (activate) a specific iTerm2 window.

    Args:
        window_id: The window ID to focus.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        window = _find_window(app, window_id)
        await window.async_activate()
        return f"Focused window {window_id}"

    return await _run(_impl)


@mcp.tool()
async def window_move(x: int, y: int, window_id: str | None = None) -> str:
    """Move an iTerm2 window to a specific screen position.

    Args:
        x: X coordinate (pixels from left).
        y: Y coordinate (pixels from top).
        window_id: The window ID. Omit for the current window.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        window = _find_window(app, window_id)
        point = iterm2.Point(x, y)
        await window.async_set_frame(iterm2.Frame(origin=point))
        return f"Moved window to ({x}, {y})"

    return await _run(_impl)


@mcp.tool()
async def window_resize(width: int, height: int, window_id: str | None = None) -> str:
    """Resize an iTerm2 window.

    Args:
        width: New width in pixels.
        height: New height in pixels.
        window_id: The window ID. Omit for the current window.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        window = _find_window(app, window_id)
        current_frame = await window.async_get_frame()
        new_frame = iterm2.Frame(
            origin=current_frame.origin,
            size=iterm2.Size(width, height),
        )
        await window.async_set_frame(new_frame)
        return f"Resized window to {width}x{height}"

    return await _run(_impl)


@mcp.tool()
async def window_fullscreen(state: str, window_id: str | None = None) -> str:
    """Set fullscreen state for an iTerm2 window.

    Args:
        state: One of "on", "off", or "toggle".
        window_id: The window ID. Omit for the current window.
    """
    if state not in ("on", "off", "toggle"):
        raise ValueError("state must be 'on', 'off', or 'toggle'")

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        window = _find_window(app, window_id)
        is_fs = await window.async_get_fullscreen()
        if state == "toggle":
            new_state = not is_fs
        elif state == "on":
            new_state = True
        else:
            new_state = False
        if new_state != is_fs:
            await window.async_set_fullscreen(new_state)
            return f"Fullscreen {'enabled' if new_state else 'disabled'}"
        return f"Fullscreen already {'enabled' if is_fs else 'disabled'}"

    return await _run(_impl)


@mcp.tool()
async def window_arrange_save(name: str) -> str:
    """Save the current window arrangement.

    Args:
        name: Name for the saved arrangement.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        await iterm2.Arrangement.async_save(connection, name)
        return f"Saved arrangement: {name}"

    return await _run(_impl)


@mcp.tool()
async def window_arrange_restore(name: str) -> str:
    """Restore a saved window arrangement.

    Args:
        name: Name of the arrangement to restore.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        arrangements = await iterm2.Arrangement.async_list(connection)
        if name not in arrangements:
            raise RuntimeError(f"Arrangement '{name}' not found")
        await iterm2.Arrangement.async_restore(connection, name)
        return f"Restored arrangement: {name}"

    return await _run(_impl)


@mcp.tool()
async def window_arrange_list() -> str:
    """List all saved window arrangements."""

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        arrangements = await iterm2.Arrangement.async_list(connection)
        return json.dumps(arrangements)

    return await _run(_impl)


# ═══════════════════════════════════════════════════════════════════════════
# TAB TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def tab_list(window_id: str | None = None) -> str:
    """List all iTerm2 tabs with their IDs, window IDs, indices, session counts, and active state.

    Args:
        window_id: Only list tabs from this window. Omit for all windows.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        windows = app.windows
        if window_id:
            windows = [_find_window(app, window_id)]

        data = []
        for win in windows:
            for idx, t in enumerate(win.tabs):
                data.append({
                    "id": t.tab_id,
                    "window_id": win.window_id,
                    "index": idx,
                    "sessions": len(t.sessions),
                    "is_active": t == win.current_tab,
                })
        return json.dumps(data, indent=2)

    return await _run(_impl)


@mcp.tool()
async def tab_new(
    profile: str | None = None,
    window_id: str | None = None,
    command: str | None = None,
) -> str:
    """Create a new tab in an iTerm2 window.

    Args:
        profile: Profile name for the new tab.
        window_id: Window ID to create the tab in. Omit for the current window.
        command: Command to run in the new tab.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        window = _find_window(app, window_id)
        tab = await window.async_create_tab(profile=profile)
        if tab:
            if command:
                session = tab.current_session
                if session:
                    await session.async_send_text(command + "\r")
            return json.dumps({"tab_id": tab.tab_id})
        raise RuntimeError("Failed to create tab")

    return await _run(_impl)


@mcp.tool()
async def tab_close(tab_id: str | None = None) -> str:
    """Close an iTerm2 tab.

    Args:
        tab_id: The tab ID to close. Omit for the current tab.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        tab = _find_tab(app, tab_id)
        tid = tab.tab_id
        await tab.async_close()
        return f"Closed tab {tid}"

    return await _run(_impl)


@mcp.tool()
async def tab_select(tab_id_or_index: str, window_id: str | None = None) -> str:
    """Select a tab by its ID or numeric index.

    Args:
        tab_id_or_index: Tab ID string, or a numeric index (0-based).
        window_id: Window ID for index-based selection. Omit for the current window.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        try:
            index = int(tab_id_or_index)
            window = _find_window(app, window_id)
            if 0 <= index < len(window.tabs):
                await window.tabs[index].async_select()
                return f"Selected tab at index {index}"
            raise RuntimeError(f"Tab index {index} out of range (0-{len(window.tabs) - 1})")
        except ValueError:
            tab = _find_tab(app, tab_id_or_index)
            await tab.async_select()
            return f"Selected tab {tab_id_or_index}"

    return await _run(_impl)


@mcp.tool()
async def tab_next() -> str:
    """Switch to the next tab in the current window."""

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        window = _find_window(app, None)
        current_tab = window.current_tab
        if not current_tab:
            raise RuntimeError("No current tab")
        idx = window.tabs.index(current_tab)
        next_idx = (idx + 1) % len(window.tabs)
        await window.tabs[next_idx].async_select()
        return f"Switched to tab {next_idx}"

    return await _run(_impl)


@mcp.tool()
async def tab_prev() -> str:
    """Switch to the previous tab in the current window."""

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        window = _find_window(app, None)
        current_tab = window.current_tab
        if not current_tab:
            raise RuntimeError("No current tab")
        idx = window.tabs.index(current_tab)
        prev_idx = (idx - 1) % len(window.tabs)
        await window.tabs[prev_idx].async_select()
        return f"Switched to tab {prev_idx}"

    return await _run(_impl)


@mcp.tool()
async def tab_move(tab_id: str | None = None) -> str:
    """Move a tab to its own new window.

    Args:
        tab_id: The tab ID to move. Omit for the current tab.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        tab = _find_tab(app, tab_id)
        await tab.async_move_to_window()
        return "Moved tab to new window"

    return await _run(_impl)


# ═══════════════════════════════════════════════════════════════════════════
# APP TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def app_activate() -> str:
    """Activate iTerm2 (bring to front)."""

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        await app.async_activate()
        return "iTerm2 activated"

    return await _run(_impl)


@mcp.tool()
async def app_get_focus() -> str:
    """Get information about the currently focused window, tab, and session."""

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        result: dict[str, Any] = {}
        window = app.current_terminal_window
        if window:
            result["window_id"] = window.window_id
            tab = window.current_tab
            if tab:
                result["tab_id"] = tab.tab_id
                session = tab.current_session
                if session:
                    result["session_id"] = session.session_id
                    name = await session.async_get_variable("session.name")
                    if name:
                        result["session_name"] = name
        return json.dumps(result, indent=2)

    return await _run(_impl)


@mcp.tool()
async def app_theme(value: str | None = None) -> str:
    """Get or set the iTerm2 theme.

    Args:
        value: Theme to set. One of: light, dark, light-hc, dark-hc, automatic, minimal.
               Omit to get the current theme.
    """
    theme_map = {
        "light": 0, "dark": 1, "light-hc": 2,
        "dark-hc": 3, "automatic": 4, "minimal": 5,
    }

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        if value is None:
            attrs = await app.async_get_theme()
            return f"Current theme: {', '.join(attrs)}"
        if value not in theme_map:
            raise ValueError(f"Invalid theme. Choose from: {', '.join(theme_map)}")
        await iterm2.async_set_preference(
            connection, iterm2.PreferenceKey.THEME, theme_map[value]
        )
        return f"Theme set to: {value}"

    return await _run(_impl)


@mcp.tool()
async def app_version() -> str:
    """Get the iTerm2 version."""

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        ver = await iterm2.async_get_preference(
            connection, iterm2.PreferenceKey.ITERM_VERSION
        )
        return f"iTerm2 version: {ver or 'unknown'}"

    return await _run(_impl)


@mcp.tool()
async def broadcast_on() -> str:
    """Enable input broadcasting to all sessions in the current tab."""

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        window = _find_window(app, None)
        tab = window.current_tab
        if not tab:
            raise RuntimeError("No current tab")
        domain = iterm2.BroadcastDomain()
        for s in tab.sessions:
            domain.add_session(s)
        await iterm2.async_set_broadcast_domains(connection, [domain])
        return "Broadcasting enabled for current tab"

    return await _run(_impl)


@mcp.tool()
async def broadcast_off() -> str:
    """Disable input broadcasting."""

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        await iterm2.async_set_broadcast_domains(connection, [])
        return "Broadcasting disabled"

    return await _run(_impl)


@mcp.tool()
async def broadcast_add(session_ids: list[str]) -> str:
    """Create a broadcast group with specific sessions.

    Args:
        session_ids: List of session IDs to include in the broadcast group.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        sessions = []
        for sid in session_ids:
            s = _get_session_by_id(app, sid)
            if not s:
                raise RuntimeError(f"Session '{sid}' not found")
            sessions.append(s)
        domain = iterm2.BroadcastDomain()
        for s in sessions:
            domain.add_session(s)
        await iterm2.async_set_broadcast_domains(connection, [domain])
        return f"Created broadcast group with {len(sessions)} sessions"

    return await _run(_impl)


# ═══════════════════════════════════════════════════════════════════════════
# PROFILE TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def profile_list() -> str:
    """List all iTerm2 profiles with their GUIDs and names."""

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        profiles = await iterm2.PartialProfile.async_query(connection)
        data = [{"guid": p.guid, "name": p.name} for p in profiles]
        return json.dumps(data, indent=2)

    return await _run(_impl)


@mcp.tool()
async def profile_show(name: str) -> str:
    """Show detailed information about an iTerm2 profile.

    Args:
        name: The profile name.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        profiles = await iterm2.PartialProfile.async_query(connection)
        target = None
        for p in profiles:
            if p.name == name:
                target = p
                break
        if not target:
            raise RuntimeError(f"Profile '{name}' not found")

        full = await target.async_get_full_profile()
        data = {
            "guid": full.guid,
            "name": full.name,
            "font": full.normal_font,
            "background_color": str(full.background_color),
            "foreground_color": str(full.foreground_color),
            "transparency": full.transparency,
            "blur": full.blur,
            "cursor_color": str(full.cursor_color),
            "selection_color": str(full.selection_color),
            "badge_text": full.badge_text,
        }
        return json.dumps(data, indent=2)

    return await _run(_impl)


@mcp.tool()
async def profile_apply(name: str, session_id: str | None = None) -> str:
    """Apply an iTerm2 profile to a session.

    Args:
        name: The profile name to apply.
        session_id: Target session ID. Omit for the active session.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        profiles = await iterm2.PartialProfile.async_query(connection)
        target_profile = None
        for p in profiles:
            if p.name == name:
                target_profile = p
                break
        if not target_profile:
            raise RuntimeError(f"Profile '{name}' not found")

        sessions = _resolve_sessions(app, session_id)
        session = sessions[0]
        await session.async_set_profile(target_profile)
        return f"Applied profile '{name}' to session {session.session_id}"

    return await _run(_impl)


# ═══════════════════════════════════════════════════════════════════════════
# BATCH TOOL
# ═══════════════════════════════════════════════════════════════════════════

# Maps operation names to the async functions that implement them, plus their
# parameter specs so the batch executor can route correctly.
_BATCH_OPS: dict[str, Callable[..., Awaitable[str]]] = {}


def _register_batch_op(name: str, func: Callable[..., Awaitable[Any]]) -> None:
    _BATCH_OPS[name] = func


async def _batch_run_impl(
    connection: iterm2.Connection,
    app: iterm2.App,
    operations: list[dict[str, Any]],
) -> str:
    """Execute a sequence of operations within a single iTerm2 connection."""
    results: list[dict[str, Any]] = []

    for i, op in enumerate(operations):
        op_type = op.get("op")
        if not op_type:
            results.append({"index": i, "error": "missing 'op' field"})
            continue

        # Sleep is a special built-in operation
        if op_type == "sleep":
            duration = op.get("seconds", op.get("ms", 0))
            if "ms" in op and "seconds" not in op:
                duration = op["ms"] / 1000.0
            await asyncio.sleep(float(duration))
            results.append({"index": i, "op": "sleep", "result": f"slept {duration}s"})
            continue

        # Look up the operation handler
        handler = _BATCH_HANDLERS.get(op_type)
        if not handler:
            results.append({"index": i, "op": op_type, "error": f"unknown operation '{op_type}'"})
            continue

        # Extract params (everything except "op")
        params = {k: v for k, v in op.items() if k != "op"}

        try:
            result = await handler(connection=connection, app=app, **params)
            results.append({"index": i, "op": op_type, "result": result})
        except Exception as e:
            results.append({"index": i, "op": op_type, "error": str(e)})
            # Check if the caller wants to stop on error
            if op.get("stop_on_error", False):
                results.append({"index": i + 1, "error": "batch aborted due to stop_on_error"})
                break

    return json.dumps(results, indent=2)


# --- Batch handler implementations (take connection+app directly) ---

async def _b_session_send(
    connection: iterm2.Connection, app: iterm2.App,
    text: str, session_id: str | None = None, all_sessions: bool = False, **_: Any,
) -> str:
    assert_permission("session_send")
    sessions = _resolve_sessions(app, session_id, all_sessions)
    await check_sessions_allowed(sessions)
    for s in sessions:
        await s.async_send_text(text)
    return f"Sent text to {len(sessions)} session(s)"


async def _b_session_run(
    connection: iterm2.Connection, app: iterm2.App,
    command: str, session_id: str | None = None, all_sessions: bool = False, **_: Any,
) -> str:
    assert_permission("session_run")
    sessions = _resolve_sessions(app, session_id, all_sessions)
    await check_sessions_allowed(sessions)
    for s in sessions:
        await s.async_send_text(command + "\r")
    return f"Executed command in {len(sessions)} session(s)"


async def _b_session_read(
    connection: iterm2.Connection, app: iterm2.App,
    session_id: str | None = None, lines: int | None = None, **_: Any,
) -> str:
    assert_permission("session_read")
    sessions = _resolve_sessions(app, session_id)
    await check_sessions_allowed(sessions)
    session = sessions[0]
    contents = await session.async_get_screen_contents()
    text_lines = [contents.line(i).string for i in range(contents.number_of_lines)]
    if lines is not None:
        text_lines = text_lines[-lines:] if lines < len(text_lines) else text_lines
    return "\n".join(text_lines)


async def _b_session_split(
    connection: iterm2.Connection, app: iterm2.App,
    vertical: bool = False, session_id: str | None = None,
    profile: str | None = None, **_: Any,
) -> str:
    assert_permission("session_split")
    sessions = _resolve_sessions(app, session_id)
    await check_sessions_allowed(sessions)
    new_session = await sessions[0].async_split_pane(vertical=vertical, profile=profile)
    if new_session:
        return json.dumps({"new_session_id": new_session.session_id})
    raise RuntimeError("Failed to split pane")


async def _b_session_close(
    connection: iterm2.Connection, app: iterm2.App,
    session_id: str | None = None, **_: Any,
) -> str:
    assert_permission("session_close")
    sessions = _resolve_sessions(app, session_id)
    await check_sessions_allowed(sessions)
    sid = sessions[0].session_id
    await sessions[0].async_close()
    return f"Closed session {sid}"


async def _b_session_focus(
    connection: iterm2.Connection, app: iterm2.App,
    session_id: str = "", **_: Any,
) -> str:
    assert_permission("session_focus")
    s = _get_session_by_id(app, session_id)
    if not s:
        raise RuntimeError(f"Session '{session_id}' not found")
    await check_session_allowed(s)
    await s.async_activate()
    return f"Focused session {session_id}"


async def _b_session_clear(
    connection: iterm2.Connection, app: iterm2.App,
    session_id: str | None = None, **_: Any,
) -> str:
    assert_permission("session_clear")
    sessions = _resolve_sessions(app, session_id)
    await check_sessions_allowed(sessions)
    for s in sessions:
        await s.async_send_text("\x0c")
    return f"Cleared {len(sessions)} session(s)"


async def _b_session_set_name(
    connection: iterm2.Connection, app: iterm2.App,
    name: str, session_id: str | None = None, **_: Any,
) -> str:
    assert_permission("session_set_name")
    sessions = _resolve_sessions(app, session_id)
    await check_sessions_allowed(sessions)
    await sessions[0].async_set_name(name)
    return f"Session name set to: {name}"


async def _b_session_list(
    connection: iterm2.Connection, app: iterm2.App, **_: Any,
) -> str:
    data = []
    for window in app.windows:
        for tab in window.tabs:
            for session in tab.sessions:
                info = await _session_info(session)
                info["window_id"] = window.window_id
                info["tab_id"] = tab.tab_id
                data.append(info)
    return json.dumps(data)


async def _b_window_new(
    connection: iterm2.Connection, app: iterm2.App,
    profile: str | None = None, command: str | None = None, **_: Any,
) -> str:
    window = await iterm2.Window.async_create(
        connection, profile=profile, command=command  # type: ignore[arg-type]
    )
    if window:
        return json.dumps({"window_id": window.window_id})
    raise RuntimeError("Failed to create window")


async def _b_window_close(
    connection: iterm2.Connection, app: iterm2.App,
    window_id: str | None = None, **_: Any,
) -> str:
    window = _find_window(app, window_id)
    wid = window.window_id
    await window.async_close()
    return f"Closed window {wid}"


async def _b_window_focus(
    connection: iterm2.Connection, app: iterm2.App,
    window_id: str = "", **_: Any,
) -> str:
    window = _find_window(app, window_id)
    await window.async_activate()
    return f"Focused window {window_id}"


async def _b_tab_new(
    connection: iterm2.Connection, app: iterm2.App,
    profile: str | None = None, window_id: str | None = None,
    command: str | None = None, **_: Any,
) -> str:
    window = _find_window(app, window_id)
    tab = await window.async_create_tab(profile=profile)
    if tab:
        if command:
            session = tab.current_session
            if session:
                await session.async_send_text(command + "\r")
        return json.dumps({"tab_id": tab.tab_id})
    raise RuntimeError("Failed to create tab")


async def _b_tab_close(
    connection: iterm2.Connection, app: iterm2.App,
    tab_id: str | None = None, **_: Any,
) -> str:
    tab = _find_tab(app, tab_id)
    tid = tab.tab_id
    await tab.async_close()
    return f"Closed tab {tid}"


async def _b_tab_select(
    connection: iterm2.Connection, app: iterm2.App,
    tab_id_or_index: str = "", window_id: str | None = None, **_: Any,
) -> str:
    try:
        index = int(tab_id_or_index)
        window = _find_window(app, window_id)
        if 0 <= index < len(window.tabs):
            await window.tabs[index].async_select()
            return f"Selected tab at index {index}"
        raise RuntimeError(f"Tab index {index} out of range")
    except ValueError:
        tab = _find_tab(app, tab_id_or_index)
        await tab.async_select()
        return f"Selected tab {tab_id_or_index}"


async def _b_tab_next(
    connection: iterm2.Connection, app: iterm2.App, **_: Any,
) -> str:
    window = _find_window(app, None)
    current_tab = window.current_tab
    if not current_tab:
        raise RuntimeError("No current tab")
    idx = window.tabs.index(current_tab)
    next_idx = (idx + 1) % len(window.tabs)
    await window.tabs[next_idx].async_select()
    return f"Switched to tab {next_idx}"


async def _b_tab_prev(
    connection: iterm2.Connection, app: iterm2.App, **_: Any,
) -> str:
    window = _find_window(app, None)
    current_tab = window.current_tab
    if not current_tab:
        raise RuntimeError("No current tab")
    idx = window.tabs.index(current_tab)
    prev_idx = (idx - 1) % len(window.tabs)
    await window.tabs[prev_idx].async_select()
    return f"Switched to tab {prev_idx}"


async def _b_app_activate(
    connection: iterm2.Connection, app: iterm2.App, **_: Any,
) -> str:
    await app.async_activate()
    return "iTerm2 activated"


async def _b_broadcast_on(
    connection: iterm2.Connection, app: iterm2.App, **_: Any,
) -> str:
    window = _find_window(app, None)
    tab = window.current_tab
    if not tab:
        raise RuntimeError("No current tab")
    domain = iterm2.BroadcastDomain()
    for s in tab.sessions:
        domain.add_session(s)
    await iterm2.async_set_broadcast_domains(connection, [domain])
    return "Broadcasting enabled for current tab"


async def _b_broadcast_off(
    connection: iterm2.Connection, app: iterm2.App, **_: Any,
) -> str:
    await iterm2.async_set_broadcast_domains(connection, [])
    return "Broadcasting disabled"


async def _b_send_keystrokes(
    connection: iterm2.Connection, app: iterm2.App,
    keys: str, session_id: str | None = None, **_: Any,
) -> str:
    """Send raw keystrokes (supports escape sequences like \\x03 for Ctrl+C)."""
    assert_permission("send_keystrokes")
    sessions = _resolve_sessions(app, session_id)
    await check_sessions_allowed(sessions)
    # Decode common escape sequences
    decoded = keys.encode("utf-8").decode("unicode_escape")
    for s in sessions:
        await s.async_send_text(decoded)
    return f"Sent keystrokes to {len(sessions)} session(s)"


async def _b_session_get_variable(
    connection: iterm2.Connection, app: iterm2.App,
    variable: str, session_id: str | None = None, **_: Any,
) -> str:
    assert_permission("session_get_variable")
    sessions = _resolve_sessions(app, session_id)
    await check_sessions_allowed(sessions)
    value = await sessions[0].async_get_variable(variable)
    if value is not None:
        return str(value)
    return f"Variable '{variable}' not set"


async def _b_session_set_variable(
    connection: iterm2.Connection, app: iterm2.App,
    variable: str, value: str, session_id: str | None = None, **_: Any,
) -> str:
    assert_permission("session_set_variable")
    sessions = _resolve_sessions(app, session_id)
    await check_sessions_allowed(sessions)
    await sessions[0].async_set_variable(variable, value)
    return f"Set {variable} = {value}"


async def _b_session_restart(
    connection: iterm2.Connection, app: iterm2.App,
    session_id: str | None = None, **_: Any,
) -> str:
    assert_permission("session_restart")
    sessions = _resolve_sessions(app, session_id)
    await check_sessions_allowed(sessions)
    await sessions[0].async_restart()
    return f"Restarted session {sessions[0].session_id}"


async def _b_profile_apply(
    connection: iterm2.Connection, app: iterm2.App,
    name: str, session_id: str | None = None, **_: Any,
) -> str:
    assert_permission("profile_apply")
    profiles = await iterm2.PartialProfile.async_query(connection)
    target_profile = None
    for p in profiles:
        if p.name == name:
            target_profile = p
            break
    if not target_profile:
        raise RuntimeError(f"Profile '{name}' not found")
    sessions = _resolve_sessions(app, session_id)
    await check_sessions_allowed(sessions)
    await sessions[0].async_set_profile(target_profile)
    return f"Applied profile '{name}'"


# Register all batch handlers
_BATCH_HANDLERS: dict[str, Callable[..., Awaitable[str]]] = {
    "session_send": _b_session_send,
    "session_run": _b_session_run,
    "session_read": _b_session_read,
    "session_split": _b_session_split,
    "session_close": _b_session_close,
    "session_focus": _b_session_focus,
    "session_clear": _b_session_clear,
    "session_set_name": _b_session_set_name,
    "session_list": _b_session_list,
    "window_new": _b_window_new,
    "window_close": _b_window_close,
    "window_focus": _b_window_focus,
    "tab_new": _b_tab_new,
    "tab_close": _b_tab_close,
    "tab_select": _b_tab_select,
    "tab_next": _b_tab_next,
    "tab_prev": _b_tab_prev,
    "app_activate": _b_app_activate,
    "broadcast_on": _b_broadcast_on,
    "broadcast_off": _b_broadcast_off,
    "send_keystrokes": _b_send_keystrokes,
    "session_get_variable": _b_session_get_variable,
    "session_set_variable": _b_session_set_variable,
    "session_restart": _b_session_restart,
    "profile_apply": _b_profile_apply,
}


@mcp.tool()
async def batch(operations: list[dict[str, Any]], stop_on_error: bool = False) -> str:
    """Execute a batch of iTerm2 operations sequentially within a single connection.

    Each operation is a dict with an "op" field naming the operation, plus any
    parameters for that operation. A special "sleep" operation pauses between steps.

    Args:
        operations: List of operation dicts. Each must have an "op" field.
            Available ops: session_send, session_run, session_read, session_split,
            session_close, session_focus, session_clear, session_set_name,
            session_list, session_get_variable, session_set_variable,
            session_restart, window_new, window_close, window_focus, tab_new,
            tab_close, tab_select, tab_next, tab_prev, app_activate,
            broadcast_on, broadcast_off, send_keystrokes, profile_apply, sleep.

            Sleep op: {"op": "sleep", "seconds": 0.5} or {"op": "sleep", "ms": 500}

            Example batch:
            [
                {"op": "session_run", "command": "echo hello"},
                {"op": "sleep", "seconds": 1.0},
                {"op": "session_read"},
                {"op": "session_send", "text": "world"}
            ]
        stop_on_error: If true, abort the batch on the first error.

    Returns:
        JSON array of results, one per operation, with index, op name, and result or error.
    """

    async def _impl(connection: iterm2.Connection, app: iterm2.App) -> str:
        results: list[dict[str, Any]] = []
        for i, op in enumerate(operations):
            op_type = op.get("op")
            if not op_type:
                results.append({"index": i, "error": "missing 'op' field"})
                if stop_on_error:
                    break
                continue

            if op_type == "sleep":
                duration = op.get("seconds", 0)
                if "ms" in op and "seconds" not in op:
                    duration = op["ms"] / 1000.0
                await asyncio.sleep(float(duration))
                results.append({"index": i, "op": "sleep", "result": f"slept {duration}s"})
                continue

            handler = _BATCH_HANDLERS.get(op_type)
            if not handler:
                results.append({"index": i, "op": op_type, "error": f"unknown operation '{op_type}'"})
                if stop_on_error:
                    break
                continue

            params = {k: v for k, v in op.items() if k != "op"}
            try:
                result = await handler(connection=connection, app=app, **params)
                results.append({"index": i, "op": op_type, "result": result})
                audit_log(f"batch.{op_type}", params, result=result)
            except Exception as e:
                results.append({"index": i, "op": op_type, "error": str(e)})
                audit_log(f"batch.{op_type}", params, error=str(e))
                if stop_on_error:
                    break

        return json.dumps(results, indent=2)

    assert_permission("batch")
    return await _run(_impl)


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
