#!/bin/bash
# sandboxed-shell.sh — Wrapper for iTerm MCP sessions ONLY
# Normal iTerm usage is completely unaffected.
#
# Install:
#   mkdir -p ~/.config
#   cp sandboxed-shell.sh ~/.config/sandboxed-shell.sh
#   chmod +x ~/.config/sandboxed-shell.sh
#
# This is used in two places:
#   1. As the "Command" in a dedicated iTerm Profile called "MCP Sandboxed"
#   2. Referenced by the iterm-mcp server config so Claude sessions use that profile
#
# --no-rcs prevents zsh from sourcing ANY rc files on startup,
# which is the belt to the sandbox's suspenders.
#
# env -i strips ALL inherited environment variables, preventing secret leakage
# (e.g. GITHUB_TOKEN, AWS_SECRET_ACCESS_KEY from the parent shell).
# Only variables listed in env-passthrough.conf are passed through.

# Auto-tag this session for it2mcp before launching the sandbox.
# The escape sequence is interpreted by iTerm2 (the terminal emulator),
# not by the shell, so it works regardless of sandbox restrictions.
# Tags reset when the session ends — you opt in per-session, per-lifetime.
printf '\033]1337;SetUserVar=%s=%s\007' mcp_enabled "$(printf 'true' | base64)"

# --- Build env var passthrough from config file ---
# PATH is always hardcoded (not inherited) to prevent PATH manipulation.
# Even if PATH appears in env-passthrough.conf, it is silently skipped.
ENV_CONF="${HOME}/.config/it2mcp/env-passthrough.conf"

ENV_ARGS=()
ENV_ARGS+=("PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin")

if [[ -f "$ENV_CONF" ]]; then
    while IFS= read -r line; do
        # Skip comments and blank lines
        line="${line%%#*}"
        line="${line// /}"
        [[ -z "$line" ]] && continue
        # PATH is hardcoded above — never inherit it from the parent
        [[ "$line" == "PATH" ]] && continue
        # Only pass through if the variable is actually set
        if [[ -n "${!line+x}" ]]; then
            ENV_ARGS+=("${line}=${!line}")
        fi
    done < "$ENV_CONF"
else
    # Fallback defaults if no config file exists
    ENV_ARGS+=("HOME=$HOME")
    ENV_ARGS+=("USER=$USER")
    ENV_ARGS+=("SHELL=/bin/zsh")
    ENV_ARGS+=("TERM=${TERM:-xterm-256color}")
    ENV_ARGS+=("LANG=${LANG:-en_US.UTF-8}")
    ENV_ARGS+=("TMPDIR=${TMPDIR:-/tmp}")
fi

exec env -i "${ENV_ARGS[@]}" \
    /usr/bin/sandbox-exec -f "$HOME/.config/iterm-sandbox.sb" /bin/zsh --no-rcs "$@"
