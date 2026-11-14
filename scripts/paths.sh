# Sourced by setup.sh and privatellm. Expects ROOT to be the project folder.
#
# Everything setup.sh installs goes under the project folder, so an install on
# an external drive keeps the software on that drive, not on the Mac's own disk.

APPS_DIR="$ROOT/apps"
BIN_DIR="$ROOT/bin"

# Where uv puts Open WebUI and the sync tool, its download cache, and Python.
export UV_TOOL_DIR="$APPS_DIR/uv-tools"
export UV_TOOL_BIN_DIR="$BIN_DIR"
export UV_CACHE_DIR="$APPS_DIR/uv-cache"
export UV_PYTHON_INSTALL_DIR="$APPS_DIR/python"

# The project's own programs first; the rest covers an Ollama or uv that was
# already installed on the Mac, which a fresh shell may not have on PATH.
export PATH="$BIN_DIR:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
