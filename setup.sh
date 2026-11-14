#!/usr/bin/env bash
# One-time setup: installs Ollama, Open WebUI and the sync tool, picks a model
# that fits this machine's memory, downloads it, and writes settings.env.
# Safe to run again: it skips what is already there.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS="$ROOT/settings.env"
# The versions tests/test_e2e.sh was run against. Newer ones may rename settings.
OPEN_WEBUI_VERSION="${OPEN_WEBUI_VERSION:-0.13.3}"
OIKB_VERSION="${OIKB_VERSION:-0.6.0}"
EMBED_MODEL_DEFAULT="qwen3-embedding:0.6b"

say()  { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

memory_gb() {
  case "$(uname -s)" in
    Darwin) echo $(( $(sysctl -n hw.memsize) / 1073741824 )) ;;
    Linux)  awk '/MemTotal/ { printf "%d\n", ($2 + 524288) / 1048576 }' /proc/meminfo ;;
    *)      fail "Unsupported system: $(uname -s)" ;;
  esac
}

# Prints "<chat model> <context length>" for a machine with $1 GB of memory.
# The model must leave room for macOS, the embedding model and the context.
pick_model() {
  local gb="$1"
  if   (( gb >= 48 )); then echo "qwen3.5:35b 32768"
  elif (( gb >= 32 )); then echo "qwen3.5:27b 16384"
  elif (( gb >= 24 )); then echo "qwen3.5:9b 16384"
  elif (( gb >= 16 )); then echo "qwen3.5:9b 8192"
  else                      echo "qwen3.5:4b 8192"
  fi
}

install_tools() {
  if ! command -v ollama >/dev/null 2>&1; then
    [[ "$(uname -s)" == "Darwin" ]] || fail "Install Ollama first: https://ollama.com/download"
    command -v brew >/dev/null 2>&1 || fail "Homebrew is needed to install Ollama. Install it from https://brew.sh and run this again."
    say "Installing Ollama"
    brew install ollama
  fi
  if ! command -v uv >/dev/null 2>&1; then
    say "Installing uv (Python tool runner)"
    if command -v brew >/dev/null 2>&1; then brew install uv; else fail "Install uv first: https://docs.astral.sh/uv/"; fi
  fi
  say "Installing Open WebUI (several GB of downloads the first time)"
  uv tool install --python 3.12 "open-webui==$OPEN_WEBUI_VERSION"
  say "Installing the knowledge sync tool"
  uv tool install --python 3.12 "oikb[all]==$OIKB_VERSION"
}

write_settings() {
  local chat_model="$1" context="$2"
  if [[ -f "$SETTINGS" ]]; then
    say "Keeping existing $SETTINGS"
    return
  fi
  umask 077
  cat > "$SETTINGS" <<EOF
# Written by setup.sh. Edit and run ./privatellm restart to apply.
CHAT_MODEL=$chat_model
EMBED_MODEL=$EMBED_MODEL_DEFAULT
CONTEXT_LENGTH=$context
# Where the model files (5 to 25 GB) are kept. Default: the models folder next
# to this file, so they sit on whichever drive this project is on.
# MODELS_DIR=/Volumes/YourDrive/models
# Port people open in their browser.
PORT=8080
# 0.0.0.0 lets other computers on your network connect. 127.0.0.1 = this Mac only.
BIND_ADDRESS=0.0.0.0
# Signs login sessions. Keep private; changing it logs everyone out.
WEBUI_SECRET_KEY=$(openssl rand -hex 32)
EOF
  say "Wrote $SETTINGS"
}

pull_models() {
  # shellcheck disable=SC1090
  source "$SETTINGS"
  "$ROOT/privatellm" start-ollama
  # Only an Ollama started by the launcher stores models in the project folder.
  [[ -f "$ROOT/run/ollama.pid" ]] || fail "Another Ollama is already running. Quit the Ollama app (menu bar icon, Quit), then run ./setup.sh again."
  say "Downloading $CHAT_MODEL and $EMBED_MODEL (this is the slow part)"
  ollama pull "$CHAT_MODEL"
  ollama pull "$EMBED_MODEL"
}

main() {
  if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" != "arm64" ]]; then
    fail "This setup is for Apple Silicon Macs. Intel Macs are too slow for this."
  fi
  local gb chat_model context
  gb="$(memory_gb)"
  read -r chat_model context <<<"$(pick_model "$gb")"
  say "This machine has ${gb} GB of memory -> ${chat_model}, context ${context} tokens"
  if (( gb < 16 )); then
    echo "    Warning: under 16 GB only a small model fits. Expect weak answers."
  fi
  install_tools
  write_settings "$chat_model" "$context"
  pull_models
  say "Setup finished. Next:"
  echo "    ./privatellm start       # start the assistant"
  echo "    ./privatellm configure   # create your admin login and the knowledge base"
}

# Allow tests to source this file for its functions without running it.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
