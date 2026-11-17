#!/usr/bin/env bash
# Checks the model that setup.sh picks for each memory size.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/setup.sh"

failures=0
expect() {
  local gb="$1" want="$2" got
  got="$(pick_model "$gb")"
  if [[ "$got" == "$want" ]]; then
    echo "ok   ${gb} GB -> $got"
  else
    echo "FAIL ${gb} GB -> got '$got', want '$want'"
    failures=$(( failures + 1 ))
  fi
}

expect 8   "llama3.2:3b 8192 none"
expect 15  "llama3.2:3b 8192 none"
expect 16  "gemma4:12b 8192 false"
expect 23  "gemma4:12b 8192 false"
expect 24  "gpt-oss:20b 8192 medium"
expect 32  "gpt-oss:20b 16384 medium"
expect 63  "gpt-oss:20b 16384 medium"
expect 64  "llama3.3:70b 16384 none"
expect 95  "llama3.3:70b 16384 none"
expect 96  "gpt-oss:120b 32768 medium"
expect 512 "gpt-oss:120b 32768 medium"

# No model from a Chinese maker may be chosen at any size.
for gb in 4 8 16 24 32 48 64 96 128 256 512; do
  case "$(pick_model "$gb")" in
    qwen*|deepseek*|glm*|minimax*|kimi*|yi*|baichuan*)
      echo "FAIL ${gb} GB picks a Chinese-origin model"; failures=$(( failures + 1 )) ;;
  esac
done
case "$EMBED_MODEL_DEFAULT" in
  qwen*|bge*) echo "FAIL search model is Chinese-origin"; failures=$(( failures + 1 )) ;;
  *) echo "ok   search model is $EMBED_MODEL_DEFAULT" ;;
esac

gb="$(memory_gb)"
if [[ "$gb" =~ ^[0-9]+$ ]] && (( gb > 0 )); then
  echo "ok   memory_gb reports ${gb} GB on this machine"
else
  echo "FAIL memory_gb returned '$gb'"
  failures=$(( failures + 1 ))
fi

exit "$failures"
