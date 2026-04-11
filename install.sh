#!/bin/bash
set -euo pipefail

# it2mcp installer
# Sets up sandboxed iTerm2 environment with command gate and secret redaction

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="$HOME/.config"
IT2MCP_CONFIG_DIR="$CONFIG_DIR/it2mcp"
PROFILE_NAME="MCP Sandboxed"
SHELL_PATH="$CONFIG_DIR/sandboxed-shell.sh"

echo "=== it2mcp installer ==="
echo ""

# ── Check prerequisites ──────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: This tool is macOS only."
    exit 1
fi

if ! command -v sandbox-exec &>/dev/null; then
    echo "ERROR: sandbox-exec not found."
    exit 1
fi

if [[ ! -d /Applications/iTerm.app ]]; then
    echo "ERROR: iTerm2 not found at /Applications/iTerm.app"
    exit 1
fi

# Detect Homebrew prefix (Apple Silicon vs Intel)
if [[ -x /opt/homebrew/bin/brew ]]; then
    BREW_PREFIX="/opt/homebrew"
elif [[ -x /usr/local/bin/brew ]]; then
    BREW_PREFIX="/usr/local"
else
    BREW_PREFIX=""
fi

if ! command -v uv &>/dev/null; then
    echo "ERROR: uv is not installed."
    echo ""
    if [[ -n "$BREW_PREFIX" ]]; then
        echo "  Install with Homebrew:  brew install uv"
    else
        echo "  Install with:  curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
    echo ""
    echo "  Then re-run this installer."
    exit 1
fi

UV_PATH="$(command -v uv)"

echo "[✓] macOS detected"
echo "[✓] sandbox-exec available"
echo "[✓] iTerm2 installed"
echo "[✓] uv found at $UV_PATH"
echo ""

# ── Copy sandbox files ───────────────────────────────────────────
mkdir -p "$CONFIG_DIR"

cp "$SCRIPT_DIR/sandbox/iterm-sandbox.sb" "$CONFIG_DIR/iterm-sandbox.sb"
echo "[✓] Copied iterm-sandbox.sb → $CONFIG_DIR/"

cp "$SCRIPT_DIR/sandbox/sandboxed-shell.sh" "$CONFIG_DIR/sandboxed-shell.sh"
chmod +x "$CONFIG_DIR/sandboxed-shell.sh"
echo "[✓] Copied sandboxed-shell.sh → $CONFIG_DIR/ (executable)"
echo ""

# ── Create it2mcp config (if not present) ────────────────────────
mkdir -p "$IT2MCP_CONFIG_DIR"

if [[ -f "$IT2MCP_CONFIG_DIR/config.yaml" ]]; then
    echo "[~] it2mcp config already exists at $IT2MCP_CONFIG_DIR/config.yaml — skipping"
else
    cp "$SCRIPT_DIR/config/example-config.yaml" "$IT2MCP_CONFIG_DIR/config.yaml"
    echo "[✓] Created it2mcp config → $IT2MCP_CONFIG_DIR/config.yaml"
fi

if [[ -f "$IT2MCP_CONFIG_DIR/env-passthrough.conf" ]]; then
    echo "[~] env-passthrough.conf already exists — skipping"
else
    cp "$SCRIPT_DIR/config/env-passthrough.conf" "$IT2MCP_CONFIG_DIR/env-passthrough.conf"
    echo "[✓] Created env-passthrough.conf → $IT2MCP_CONFIG_DIR/"
fi
echo ""

# ── Create iTerm2 "MCP Sandboxed" profile ────────────────────────
DYNAMIC_PROFILES_DIR="$HOME/Library/Application Support/iTerm2/DynamicProfiles"
PROFILE_FILE="$DYNAMIC_PROFILES_DIR/it2mcp-sandbox.plist"

mkdir -p "$DYNAMIC_PROFILES_DIR"

if [[ -f "$PROFILE_FILE" ]]; then
    echo "[~] iTerm2 profile \"$PROFILE_NAME\" already exists — skipping (manual changes preserved)"
else
    cat > "$PROFILE_FILE" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Profiles</key>
    <array>
        <dict>
            <key>Name</key>
            <string>${PROFILE_NAME}</string>
            <key>Guid</key>
            <string>it2mcp-sandbox-profile-001</string>
            <key>Custom Command</key>
            <string>Yes</string>
            <key>Command</key>
            <string>${SHELL_PATH}</string>
            <key>Title Components</key>
            <integer>2</integer>
            <key>Badge Text</key>
            <string>🔒 Sandboxed</string>
        </dict>
    </array>
</dict>
</plist>
PLIST
    echo "[✓] Created iTerm2 dynamic profile: \"$PROFILE_NAME\""
    echo "    Location: $PROFILE_FILE"
fi
echo ""

# ── Verify sandbox works ─────────────────────────────────────────
echo "── Testing sandbox..."
if sandbox-exec -f "$CONFIG_DIR/iterm-sandbox.sb" /bin/zsh --no-rcs -c "echo sandbox_ok" 2>/dev/null | grep -q "sandbox_ok"; then
    echo "[✓] Sandbox profile loads and zsh starts successfully"
else
    echo "[✗] Sandbox test failed. Check $CONFIG_DIR/iterm-sandbox.sb for syntax errors."
    exit 1
fi
echo ""

# ── Done ─────────────────────────────────────────────────────────
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo ""
echo "  1. Restart iTerm2 to pick up the new profile"
echo ""
echo "  2. Add it2mcp to Claude Desktop's MCP config."
echo "     Edit: ~/Library/Application Support/Claude/claude_desktop_config.json"
echo ""
echo "     Add this to the \"mcpServers\" section:"
echo ""
echo "     {"
echo "       \"mcpServers\": {"
echo "         \"it2mcp\": {"
echo "           \"command\": \"$UV_PATH\","
echo "           \"args\": [\"run\", \"--directory\", \"${SCRIPT_DIR}\", \"it2mcp\"]"
echo "         }"
echo "       }"
echo "     }"
echo ""
echo "  3. Restart Claude Desktop to connect the MCP server"
echo ""
echo "  4. Customize your allow/deny command lists:"
echo "     Edit: $IT2MCP_CONFIG_DIR/config.yaml"
echo ""
echo "  5. Move this repo out of Claude's reach."
echo "     The sandbox source should not be readable or writable by"
echo "     sandboxed sessions or MCP tools."
echo ""
echo "To uninstall:"
echo "  rm $CONFIG_DIR/iterm-sandbox.sb"
echo "  rm $CONFIG_DIR/sandboxed-shell.sh"
echo "  rm \"$PROFILE_FILE\""
echo "  rm -rf $IT2MCP_CONFIG_DIR"
