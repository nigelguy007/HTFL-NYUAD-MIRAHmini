#!/usr/bin/env bash
# Checks that the launcher tells Ollama to keep model files in the project's
# models folder (or MODELS_DIR), not in the home folder on the Mac's own disk.
# Uses a stub "ollama" command that records the folder it was told to use.
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
MODEL_PORT=21435
export OLLAMA_URL="http://127.0.0.1:$MODEL_PORT"
failures=0

cleanup() {
  local app
  for app in "$WORK"/app-*; do
    [[ -x "$app/privatellm" ]] && "$app/privatellm" stop >/dev/null 2>&1 || true
  done
  rm -rf "$WORK"
}
trap cleanup EXIT

mkdir -p "$WORK/bin"
{
  echo '#!/usr/bin/env bash'
  echo "printf '%s' \"\${OLLAMA_MODELS:-unset}\" > \"$WORK/recorded\""
  echo "exec python3 \"$SOURCE_ROOT/tests/fake_ollama.py\" $MODEL_PORT test-chat"
} > "$WORK/bin/ollama"
chmod +x "$WORK/bin/ollama"
export PATH="$WORK/bin:$PATH"

# make_app <name> <extra settings line>: prints the new app folder.
make_app() {
  local app="$WORK/app-$1"
  mkdir -p "$app"
  cp -R "$SOURCE_ROOT/privatellm" "$SOURCE_ROOT/config" "$SOURCE_ROOT/scripts" "$app/"
  printf 'CHAT_MODEL=test-chat\nEMBED_MODEL=test-embed\nCONTEXT_LENGTH=8192\nPORT=18081\nBIND_ADDRESS=127.0.0.1\nWEBUI_SECRET_KEY=x\n%s\n' "$2" > "$app/settings.env"
  echo "$app"
}

expect() {
  local label="$1" got="$2" want="$3"
  if [[ "$got" == "$want" ]]; then
    echo "ok   $label"
  else
    echo "FAIL $label: got '$got', want '$want'"
    failures=$(( failures + 1 ))
  fi
}

app="$(make_app default "")"
"$app/privatellm" start-ollama >/dev/null
expect "default is the project's models folder" "$(cat "$WORK/recorded")" "$app/models"
expect "the folder is created" "$(test -d "$app/models" && echo yes)" "yes"
expect "status says where the model is" "$("$app/privatellm" status | grep -c "stored in $app/models")" "1"
"$app/privatellm" stop >/dev/null

app="$(make_app custom "MODELS_DIR=$WORK/drive/models")"
"$app/privatellm" start-ollama >/dev/null
expect "MODELS_DIR in settings is used" "$(cat "$WORK/recorded")" "$WORK/drive/models"
"$app/privatellm" stop >/dev/null

app="$(make_app missing "MODELS_DIR=/proc/no-such-drive/models")"
output="$("$app/privatellm" start-ollama 2>&1 || true)"
expect "a missing drive gives a clear error" "$(grep -c "Is the drive plugged in" <<<"$output")" "1"

exit "$failures"
