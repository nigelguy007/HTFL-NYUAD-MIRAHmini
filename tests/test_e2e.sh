#!/usr/bin/env bash
# End-to-end check of the whole setup, using a stand-in for the model.
# Needs open-webui and oikb installed (setup.sh installs them). Takes a minute.
#
# It proves: the launcher starts and restarts cleanly, configure is repeatable,
# documents sync in, a question retrieves the right document, the document text
# reaches the model's prompt, and outside connections are switched off.
# It does not prove answer quality: that needs the real model on your Mac.
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
APP="$WORK/app"
DOCS="$WORK/docs"
WEB_PORT=18080
MODEL_PORT=21434
export OLLAMA_URL="http://127.0.0.1:$MODEL_PORT"
export ADMIN_NAME="Test Admin" ADMIN_EMAIL="admin@example.test" ADMIN_PASSWORD="Test-passw0rd-123!"

failures=0
fake_pid=""

cleanup() {
  [[ -x "$APP/privatellm" ]] && "$APP/privatellm" stop >/dev/null 2>&1 || true
  [[ -n "$fake_pid" ]] && kill "$fake_pid" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

check() {
  local label="$1"
  shift
  if "$@" >"$WORK/check.log" 2>&1; then
    echo "ok   $label"
  else
    echo "FAIL $label"
    sed 's/^/       /' "$WORK/check.log" | tail -n 15
    failures=$(( failures + 1 ))
  fi
}

ask() {
  curl -fsS -X POST "http://127.0.0.1:$WEB_PORT/api/chat/completions" \
    -H "Authorization: Bearer $(cat "$APP/run/api-key")" -H "Content-Type: application/json" \
    -d "{\"model\":\"assistant\",\"stream\":false,\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}]}"
}

# finds <question> <file name>: true if that file is the best match in one of
# the Assistant's knowledge bases (hand-uploaded or synced).
finds() {
  ask "$1" | python3 -c "
import json, sys
tops = [source['metadata'][0]['name'] for source in json.load(sys.stdin)['sources']]
sys.exit(0 if sys.argv[1] in tops else 1)" "$2"
}

# The prompt that reached the model (the stand-in repeats it back).
model_prompt() {
  ask "$1" | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
}

BASE="http://127.0.0.1:$WEB_PORT"
COLLEAGUE_EMAIL="colleague@example.test"
COLLEAGUE_PASSWORD="Another-passw0rd-456!"

post_json() { curl -sS -X POST "$BASE$1" -H "Content-Type: application/json" ${3:+-H "Authorization: Bearer $3"} -d "$2"; }
field()     { python3 -c "import json,sys; print(json.load(sys.stdin).get('$1'))"; }
login()     { post_json /api/v1/auths/signin "{\"email\":\"$1\",\"password\":\"$2\"}" | field "${3:-token}"; }

# A feature switch as the server reports it to a logged-in user: "True" or "False".
setting() {
  curl -fsS -H "Authorization: Bearer $(login "$ADMIN_EMAIL" "$ADMIN_PASSWORD")" "$BASE/api/config" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['features']['$1'])"
}

# HTTP status a colleague gets when asking the Assistant a question.
colleague_ask_status() {
  curl -s -o "$WORK/colleague.json" -w '%{http_code}' -X POST "$BASE/api/chat/completions" \
    -H "Authorization: Bearer $(login "$COLLEAGUE_EMAIL" "$COLLEAGUE_PASSWORD")" -H "Content-Type: application/json" \
    -d '{"model":"assistant","stream":false,"messages":[{"role":"user","content":"When does the Zanzibar office open?"}]}'
}

approve_colleague() {
  local admin_token colleague_id
  admin_token="$(login "$ADMIN_EMAIL" "$ADMIN_PASSWORD")"
  colleague_id="$(login "$COLLEAGUE_EMAIL" "$COLLEAGUE_PASSWORD" id)"
  post_json "/api/v1/users/$colleague_id/update" \
    "{\"role\":\"user\",\"name\":\"Colleague\",\"email\":\"$COLLEAGUE_EMAIL\",\"profile_image_url\":\"/user.png\"}" "$admin_token" | field role
}

# --- Arrange: a private copy of the project, test documents, the stand-in ----
mkdir -p "$APP" "$DOCS/policies"
cp -R "$SOURCE_ROOT/privatellm" "$SOURCE_ROOT/config" "$SOURCE_ROOT/scripts" "$SOURCE_ROOT/sync" "$SOURCE_ROOT/branding" "$SOURCE_ROOT/skills" "$APP/"
cat > "$APP/settings.env" <<EOF
CHAT_MODEL=test-chat
EMBED_MODEL=test-embed
CONTEXT_LENGTH=8192
PORT=$WEB_PORT
BIND_ADDRESS=0.0.0.0
WEBUI_SECRET_KEY=$(openssl rand -hex 32)
EOF
printf '# Office handbook\n\nThe Zanzibar office opens at 09:15 on weekdays.\n' > "$DOCS/handbook.md"
printf 'Parking policy: visitor permits are purple and expire after 3 days.\n' > "$DOCS/policies/parking.txt"
printf 'order_id,customer,amount\n1001,Acme,250\n1002,Globex,410\n' > "$DOCS/orders.csv"
cat > "$APP/sync/sources.yaml" <<EOF
sources:
  - name: documents
    source: $DOCS
    kb-id: __KNOWLEDGE_ID__
EOF
python3 "$SOURCE_ROOT/tests/fake_ollama.py" "$MODEL_PORT" test-chat test-embed &
fake_pid=$!
sleep 1

# --- Act and assert -----------------------------------------------------------
check "starts"                         "$APP/privatellm" start
check "closed to network before setup" grep -q "Other devices are blocked" <("$APP/privatellm" status)
check "configure creates everything"   "$APP/privatellm" configure
check "open to network after setup"    grep -q "From other devices" <("$APP/privatellm" status)
check "configure can be run again"     "$APP/privatellm" configure
check "api key file is private"        test "$(stat -c %a "$APP/run/api-key" 2>/dev/null || stat -f %Lp "$APP/run/api-key")" = "600"

# A document uploaded by hand must survive every sync.
printf 'The hand-uploaded note says the spare key is in the blue tin.\n' > "$WORK/hand-note.txt"
curl -fsS -X POST "$BASE/api/v1/files/" -H "Authorization: Bearer $(cat "$APP/run/api-key")" \
  -F "file=@$WORK/hand-note.txt" -F "metadata={\"knowledge_id\":\"$(cat "$APP/run/knowledge-id")\"}" >/dev/null
sleep 5
"$APP/privatellm" sync >"$WORK/sync1.log" 2>&1 || true
check "sync adds the three documents"  grep -q "3 added" "$WORK/sync1.log"
sleep 10   # indexing happens in the background after upload
"$APP/privatellm" sync >"$WORK/sync2.log" 2>&1 || true
check "second sync changes nothing"    grep -q "3 unchanged" "$WORK/sync2.log"
check "hand-uploaded document survives" grep -q "hand-note.txt" <(curl -fsS -H "Authorization: Bearer $(cat "$APP/run/api-key")" "$BASE/api/v1/knowledge/$(cat "$APP/run/knowledge-id")/files")
check "it is still found by a question" finds 'Where is the spare key kept?' "hand-note.txt"

check "office question finds handbook" finds 'When does the Zanzibar office open?' "handbook.md"
check "parking question finds policy"  finds 'What colour are visitor parking permits?' "parking.txt"
check "order question finds the sheet" finds 'Which customer placed order 1002?' "orders.csv"
model_prompt 'When does the Zanzibar office open?' >"$WORK/prompt.txt"
check "document text reaches model"    grep -q "09:15" "$WORK/prompt.txt"
check "system prompt reaches model"    grep -q "private assistant for this team" "$WORK/prompt.txt"

echo 999999 > "$APP/run/ollama.pid"   # a leftover pidfile, as after a reboot
check "stale pidfile is ignored"       "$APP/privatellm" start
check "stale pidfile is removed"       test ! -e "$APP/run/ollama.pid"
check "data folder is private"         test "$(stat -c %a "$APP/data" 2>/dev/null || stat -f %Lp "$APP/data")" = "700"
curl -fsS "http://127.0.0.1:$MODEL_PORT/__requests" > "$WORK/model-requests.json"
check "no extra model call per question" python3 -c "
import json, sys
chats = [r['body'] for r in json.load(open(sys.argv[1])) if r['path'] == '/api/chat']
sys.exit(1 if any('<chat_history>' in str(c.get('messages')) for c in chats) or not chats else 0)" "$WORK/model-requests.json"
check "model is told not to think first" python3 -c "
import json, sys
chats = [r['body'] for r in json.load(open(sys.argv[1])) if r['path'] == '/api/chat']
sys.exit(0 if chats and all(c.get('think') is False for c in chats) else 1)" "$WORK/model-requests.json"
check "restart works"                  "$APP/privatellm" restart
check "still answers after restart"    finds 'When does the Zanzibar office open?' "handbook.md"

curl -fsS -o "$WORK/served-logo.png" "$BASE/static/favicon.png"
check "brand logo is served"           cmp "$WORK/served-logo.png" "$APP/branding/static/favicon.png"
check "brand colours are served"       grep -qi "161a24" <(curl -fsS "$BASE/static/custom.css")
check "brand name is shown exactly"    test "$(curl -fsS "$BASE/api/config" | field name)" = "MIRAH | The Oracle"
mv "$APP/branding" "$APP/branding-off"
"$APP/privatellm" restart >/dev/null 2>&1 || true
check "removing branding restores it"  test "$(curl -fsS "$BASE/static/custom.css" | wc -c | tr -d ' ')" = "0"
check "and restores the standard name" test "$(curl -fsS "$BASE/api/config" | field name)" = "Open WebUI"
mv "$APP/branding-off" "$APP/branding"
"$APP/privatellm" restart >/dev/null 2>&1 || true

check "web search is off"              test "$(setting enable_web_search)" = "False"
check "community sharing is off"       test "$(setting enable_community_sharing)" = "False"
check "direct connections are off"     test "$(setting enable_direct_connections)" = "False"
check "image generation is off"        test "$(setting enable_image_generation)" = "False"
check "update check is off"            test "$(setting enable_version_update_check)" = "False"
check "cloud drive pickers are off"    test "$(setting enable_google_drive_integration)$(setting enable_onedrive_integration)" = "FalseFalse"
check "OpenAI connection is off"       test "$(curl -fsS -H "Authorization: Bearer $(login "$ADMIN_EMAIL" "$ADMIN_PASSWORD")" "$BASE/openai/config" | field ENABLE_OPENAI_API)" = "False"

signup_role="$(post_json /api/v1/auths/signup "{\"name\":\"Colleague\",\"email\":\"$COLLEAGUE_EMAIL\",\"password\":\"$COLLEAGUE_PASSWORD\"}" | field role)"
check "new signup waits for approval"  test "$signup_role" = "pending"
check "unapproved user is locked out"  test "$(colleague_ask_status)" = "401"
check "admin can approve"              test "$(approve_colleague)" = "user"
check "approved user gets an answer"   test "$(colleague_ask_status)" = "200"
check "their answer uses the document" grep -q "09:15" "$WORK/colleague.json"

# --- Skills: copied from a library, switched on per chat -----------------------
mkdir -p "$WORK/library/pack/short-skill" "$WORK/library/pack/long-skill"
printf -- '---\nname: short-skill\ndescription: A test skill.\n---\n\nAlways mention the purple heron about $ARGUMENTS.\n' > "$WORK/library/pack/short-skill/SKILL.md"
python3 -c "print('word ' * 1200)" > "$WORK/library/pack/long-skill/SKILL.md"
printf 'pack/short-skill\npack/long-skill\n' > "$APP/skills/selected.txt"
export SKILLS_LIBRARY_URL="file://$WORK/library"
"$APP/privatellm" skills >"$WORK/skills1.log" 2>&1 || true
check "a short skill is added"         grep -q "short-skill: added" "$WORK/skills1.log"
check "an over-long skill is skipped"  grep -q "long-skill: skipped (1200 words" "$WORK/skills1.log"
"$APP/privatellm" skills >"$WORK/skills2.log" 2>&1 || true
check "running again changes nothing"  grep -q "short-skill: unchanged" "$WORK/skills2.log"
printf -- '---\nname: short-skill\ndescription: A test skill.\n---\n\nAlways mention the green heron.\n' > "$WORK/library/pack/short-skill/SKILL.md"
"$APP/privatellm" skills >"$WORK/skills3.log" 2>&1 || true
check "a changed skill is updated"     grep -q "short-skill: updated" "$WORK/skills3.log"
curl -s -o "$WORK/skill-chat.json" -X POST "$BASE/api/chat/completions" \
  -H "Authorization: Bearer $(login "$COLLEAGUE_EMAIL" "$COLLEAGUE_PASSWORD")" -H "Content-Type: application/json" \
  -d '{"model":"assistant","stream":false,"skill_ids":["short-skill"],"messages":[{"role":"user","content":"Hello"}]}'
check "a colleague can switch it on"   grep -q "green heron" "$WORK/skill-chat.json"
curl -s -o "$WORK/no-skill-chat.json" -X POST "$BASE/api/chat/completions" \
  -H "Authorization: Bearer $(login "$COLLEAGUE_EMAIL" "$COLLEAGUE_PASSWORD")" -H "Content-Type: application/json" \
  -d '{"model":"assistant","stream":false,"messages":[{"role":"user","content":"Hello"}]}'
check "it stays out of other chats"    bash -c "! grep -q 'green heron' '$WORK/no-skill-chat.json'"

echo
if (( failures == 0 )); then
  echo "All checks passed."
else
  echo "$failures check(s) failed. Last lines of the server log:"
  tail -n 20 "$APP/logs/webui.log" | cut -c1-300
fi
exit "$failures"
