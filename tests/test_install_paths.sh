#!/usr/bin/env bash
# Checks that setup.sh installs its software under the project folder (so an
# install on an external drive stays on that drive). Needs internet: it really
# installs uv and the small sync tool into a temporary copy of the project.
# The Ollama step uses a made-up download with the same layout as the real one.
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
failures=0

mkdir -p "$WORK/app"
cp -R "$SOURCE_ROOT/setup.sh" "$SOURCE_ROOT/scripts" "$WORK/app/"
# shellcheck disable=SC1091
source "$WORK/app/setup.sh"   # defines the functions; ROOT is now $WORK/app
mkdir -p "$APPS_DIR" "$BIN_DIR"

expect() {
  local label="$1" got="$2" want="$3"
  if [[ "$got" == "$want" ]]; then
    echo "ok   $label"
  else
    echo "FAIL $label: got '$got', want '$want'"
    failures=$(( failures + 1 ))
  fi
}

# --- Ollama: unpacked into apps/, command linked into bin/ --------------------
python3 - "$WORK/fake-ollama.zip" <<'PY'
import sys, zipfile
entry = zipfile.ZipInfo("Ollama.app/Contents/Resources/ollama")
entry.external_attr = 0o755 << 16
with zipfile.ZipFile(sys.argv[1], "w") as archive:
    archive.writestr(entry, "#!/bin/sh\necho fake-ollama-ran\n")
PY
OLLAMA_DOWNLOAD_URL="file://$WORK/fake-ollama.zip"
uname() { echo Darwin; }      # take the Mac branch of install_ollama
install_ollama >/dev/null 2>&1
unset -f uname
expect "ollama is unpacked under apps/" "$(test -x "$APPS_DIR/Ollama.app/Contents/Resources/ollama" && echo yes)" "yes"
expect "ollama command in bin/ runs it" "$("$BIN_DIR/ollama")" "fake-ollama-ran"
expect "the download is cleaned up" "$(test -e "$APPS_DIR/Ollama-darwin.zip" && echo left || echo gone)" "gone"

# --- uv: installed into bin/ when the machine has none -------------------------
( PATH="$BIN_DIR:/usr/bin:/bin"; install_uv ) >/dev/null 2>&1 || true
expect "uv is installed into bin/" "$(test -x "$BIN_DIR/uv" && echo yes)" "yes"

# --- A Python tool: program in bin/, its files under apps/ ---------------------
install_tool "oikb==$OIKB_VERSION" >/dev/null 2>&1 || true
expect "tool command is in bin/" "$(test -x "$BIN_DIR/oikb" && echo yes)" "yes"
expect "tool files are under apps/" "$(test -d "$APPS_DIR/uv-tools/oikb" && echo yes)" "yes"
expect "tool runs from there" "$("$BIN_DIR/oikb" --help >/dev/null 2>&1 && echo yes)" "yes"
expect "download cache is under apps/" "$(test -d "$APPS_DIR/uv-cache" && echo yes)" "yes"

exit "$failures"
