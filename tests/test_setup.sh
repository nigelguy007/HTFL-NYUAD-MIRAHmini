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

expect 8   "qwen3.5:4b 8192"
expect 15  "qwen3.5:4b 8192"
expect 16  "qwen3.5:9b 8192"
expect 18  "qwen3.5:9b 8192"
expect 24  "qwen3.5:9b 16384"
expect 32  "qwen3.5:27b 16384"
expect 36  "qwen3.5:27b 16384"
expect 48  "qwen3.5:35b 32768"
expect 128 "qwen3.5:35b 32768"

gb="$(memory_gb)"
if [[ "$gb" =~ ^[0-9]+$ ]] && (( gb > 0 )); then
  echo "ok   memory_gb reports ${gb} GB on this machine"
else
  echo "FAIL memory_gb returned '$gb'"
  failures=$(( failures + 1 ))
fi

exit "$failures"
