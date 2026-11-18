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
  # KEEP_WORK=1 leaves the test's files in place, to look at after a failure.
  if [[ -n "${KEEP_WORK:-}" ]]; then echo "Kept $WORK"; else rm -rf "$WORK"; fi
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
tops = [source['metadata'][0]['name'] for source in json.load(sys.stdin)['sources'] if source['metadata']]
sys.exit(0 if sys.argv[1] in tops else 1)" "$2"
}

# The prompt that reached the model (the stand-in repeats it back).
model_prompt() {
  ask "$1" | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
}

BASE="http://127.0.0.1:$WEB_PORT"
COLLEAGUE_EMAIL="desert-fox@mirah.local"   # an invented sign-up, as users are asked to make
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

# approve_user <email> <password> <name>: the admin lets a new sign-up in.
approve_user() {
  local admin_token user_id
  admin_token="$(login "$ADMIN_EMAIL" "$ADMIN_PASSWORD")"
  user_id="$(login "$1" "$2" id)"
  post_json "/api/v1/users/$user_id/update" \
    "{\"role\":\"user\",\"name\":\"$3\",\"email\":\"$1\",\"profile_image_url\":\"/user.png\"}" "$admin_token" | field role
}
approve_colleague() { approve_user "$COLLEAGUE_EMAIL" "$COLLEAGUE_PASSWORD" "Colleague"; }
colleague_token()   { login "$COLLEAGUE_EMAIL" "$COLLEAGUE_PASSWORD"; }

# say <token> <text>: what MIRAH (or the consent gate) sends back. Never fails.
say() {
  curl -s -X POST "$BASE/api/chat/completions" -H "Authorization: Bearer $1" -H "Content-Type: application/json" \
    -d "{\"model\":\"assistant\",\"stream\":false,\"messages\":[{\"role\":\"user\",\"content\":\"$2\"}]}"
}
# upload <token> <file> <knowledge id file>: prints the HTTP status.
upload() {
  curl -s -o "$WORK/upload.json" -w '%{http_code}' -X POST "$BASE/api/v1/files/" -H "Authorization: Bearer $1" \
    -F "file=@$2" -F "metadata={\"knowledge_id\":\"$(cat "$APP/run/$3")\"}"
}
admin_token() { cat "$APP/run/api-key"; }
# replies <pattern> <token> <text>: true if the reply contains the pattern. Shows the reply if not.
replies() { say "$2" "$3" > "$WORK/reply.json"; grep -q -- "$1" "$WORK/reply.json" || { cut -c1-700 "$WORK/reply.json"; return 1; }; }
# lacks <pattern> <token> <text>: true if the reply does not contain the pattern.
lacks()   { say "$2" "$3" > "$WORK/reply.json"; ! grep -q -- "$1" "$WORK/reply.json"; }

# --- Arrange: a private copy of the project, test documents, the stand-in ----
mkdir -p "$APP" "$DOCS/policies"
cp -R "$SOURCE_ROOT/privatellm" "$SOURCE_ROOT/config" "$SOURCE_ROOT/scripts" "$SOURCE_ROOT/sync" "$SOURCE_ROOT/branding" "$SOURCE_ROOT/skills" "$SOURCE_ROOT/functions" "$APP/"
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
"$APP/privatellm" start >"$WORK/start.log" 2>&1
check "starts"                         grep -q "Open WebUI: running" "$WORK/start.log"
check "start preloads the chat model"  grep -q "into memory" "$WORK/start.log"
check "no missing-model warning"       bash -c "! grep -q 'does not have' '$WORK/start.log'"
check "closed to network before setup" grep -q "Other devices are blocked" <("$APP/privatellm" status)
check "configure creates everything"   "$APP/privatellm" configure
check "open to network after setup"    grep -q "From other devices" <("$APP/privatellm" status)
check "configure can be run again"     "$APP/privatellm" configure
check "api key file is private"        test "$(stat -c %a "$APP/run/api-key" 2>/dev/null || stat -f %Lp "$APP/run/api-key")" = "600"

# Nobody, the admin included, gets an answer before agreeing to the notice.
check "a question waits for agreement" replies "Before you use MIRAH" "$(admin_token)" "When does the Zanzibar office open?"
check "typing I agree is recorded"     replies "Your agreement was recorded" "$(admin_token)" "I agree"

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
check "re-index runs"                  "$APP/privatellm" reindex
check "restart works"                  "$APP/privatellm" restart
check "still answers after restart"    finds 'When does the Zanzibar office open?' "handbook.md"

curl -fsS -o "$WORK/served-logo.png" "$BASE/static/favicon.png"
check "brand logo is served"           cmp "$WORK/served-logo.png" "$APP/branding/static/favicon.png"
check "brand colours are served"       grep -qi "161a24" <(curl -fsS "$BASE/static/custom.css")
check "sign-in asks for a UserID"     grep -q "UserID" <(curl -fsS "$BASE/static/loader.js")
check "wordmark typeface is served"    curl -fsS -o /dev/null "$BASE/static/brand/Michroma-Regular.ttf"
check "partner logos are served"     curl -fsS -o /dev/null "$BASE/static/brand/partner-logos.png"
check "background photos are served"   bash -c "curl -fsS -o /dev/null '$BASE/static/brand/gateway.webp' && curl -fsS -o /dev/null '$BASE/static/brand/coast.webp'"
check "brand name is shown exactly"    test "$(curl -fsS "$BASE/api/config" | field name)" = "MIRAH | The Oracle"
mv "$APP/branding" "$APP/branding-off"
"$APP/privatellm" restart >/dev/null 2>&1 || true
check "removing branding restores it"  test "$(curl -fsS "$BASE/static/custom.css" | wc -c | tr -d ' ')" = "0"
check "and the standard sign-in form"  bash -c "! grep -q UserID <(curl -fsS '$BASE/static/loader.js')"
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
check "approved user must agree first" test "$(colleague_ask_status)" = "400"
say "$(colleague_token)" "I AGREE." >/dev/null
check "approved user gets an answer"   test "$(colleague_ask_status)" = "200"
check "their answer uses the document" grep -q "09:15" "$WORK/colleague.json"

# --- A forgotten password can be reset on the host machine ---------------------
RESET_EMAIL="$COLLEAGUE_EMAIL" RESET_PASSWORD="Brand-new-pass-789" "$APP/privatellm" reset-password >"$WORK/reset.log" 2>&1 || true
check "reset lists the accounts"       grep -q "$ADMIN_EMAIL" "$WORK/reset.log"
check "new password signs in"          test "$(login "$COLLEAGUE_EMAIL" "Brand-new-pass-789" role)" = "user"
check "old password no longer works"   test "$(login "$COLLEAGUE_EMAIL" "$COLLEAGUE_PASSWORD" role)" = "None"
COLLEAGUE_PASSWORD="Brand-new-pass-789"
RESET_EMAIL="nobody@example.test" RESET_PASSWORD="Whatever-pass-1" "$APP/privatellm" reset-password >"$WORK/reset2.log" 2>&1 || true
check "unknown email changes nothing"  grep -q "No account uses" "$WORK/reset2.log"
curl -fsS -H "Authorization: Bearer $(login "$ADMIN_EMAIL" "$ADMIN_PASSWORD")" "$BASE/api/models" > "$WORK/models.json"
check "the three stages are offered"   bash -c "grep -q 'MIRAH · Inspire' '$WORK/models.json' && grep -q 'MIRAH · Imagine' '$WORK/models.json' && grep -q 'MIRAH · Activate' '$WORK/models.json'"
check "admin cannot open others' chats" test "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(login "$ADMIN_EMAIL" "$ADMIN_PASSWORD")" "$BASE/api/v1/chats/list/user/$(login "$COLLEAGUE_EMAIL" "$COLLEAGUE_PASSWORD" id)")" = "401"
check "assistant is named MIRAH"       grep -q '"name":"MIRAH"' <(curl -fsS -H "Authorization: Bearer $(login "$ADMIN_EMAIL" "$ADMIN_PASSWORD")" "$BASE/api/models")

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

# A whole repository: every SKILL.md, two folders with the same name kept apart.
mkdir -p "$WORK/skill-repo/one/brief" "$WORK/skill-repo/two/brief" "$WORK/skill-repo/three/memo"
printf -- '---\nname: brief-one\ndescription: First.\n---\n\nWrite a brief.\n' > "$WORK/skill-repo/one/brief/SKILL.md"
printf -- '---\nname: brief-two\ndescription: Second.\n---\n\nWrite a shorter brief.\n' > "$WORK/skill-repo/two/brief/SKILL.md"
python3 -c "print('word ' * 1200)" > "$WORK/skill-repo/three/memo/SKILL.md"
git -C "$WORK/skill-repo" init -q && git -C "$WORK/skill-repo" add -A \
  && git -C "$WORK/skill-repo" -c user.name=t -c user.email=t@t commit -qm skills
"$APP/privatellm" skills --repo "$WORK/skill-repo" >"$WORK/skills-repo.log" 2>&1 || true
check "a repository's skills are found" grep -q "Found 3 skill(s)" "$WORK/skills-repo.log"
check "same-named skills both added"   test "$(grep -c "brief: added" "$WORK/skills-repo.log")" = "2"
check "long ones in it are skipped"    grep -q "memo: skipped (1200 words" "$WORK/skills-repo.log"
check "the run is summarised"          grep -q "3 skill(s) processed: 2 added, 1 skipped" "$WORK/skills-repo.log"

# Signing in is rate-limited, so each person signs in once here and the session is reused.
COLLEAGUE_TOKEN="$(colleague_token)"
# --- Side routes to the model, which would skip the consent gate, are closed --------
side_route() { curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE$1" -H "Authorization: Bearer $COLLEAGUE_TOKEN" -H "Content-Type: application/json" -d "$2"; }
check "Ollama pass-through is closed"  test "$(side_route /ollama/api/chat '{"model":"test-chat","stream":false,"messages":[{"role":"user","content":"hi"}]}')" = "403"
check "numbered pass-through is closed" test "$(side_route /ollama/api/chat/0 '{"model":"test-chat","stream":false,"messages":[{"role":"user","content":"hi"}]}')" = "403"
check "helper endpoints are closed"    test "$(side_route /api/v1/tasks/emoji/completions '{"model":"assistant","prompt":"hi"}')$(side_route /api/v1/tasks/moa/completions '{"model":"assistant","prompt":"hi","responses":["a"]}')" = "403403"
post_json /api/v1/auths/signup '{"name":"Newcomer","email":"new-comer@mirah.local","password":"Newcomer-passw0rd-1!"}' >/dev/null
approve_user "new-comer@mirah.local" "Newcomer-passw0rd-1!" "Newcomer" >/dev/null
NEWCOMER_TOKEN="$(login "new-comer@mirah.local" "Newcomer-passw0rd-1!")"
curl -s -o "$WORK/base.json" -X POST "$BASE/api/chat/completions" -H "Authorization: Bearer $NEWCOMER_TOKEN" -H "Content-Type: application/json" \
  -d '{"model":"test-chat","stream":false,"messages":[{"role":"user","content":"hi"}]}'
check "the hidden base model is gated too" grep -q "Before you use MIRAH" "$WORK/base.json"

# --- Access levels: one MIRAH, different libraries per person -----------------------
printf 'The facilitator budget code is TANGERINE-77.\n' > "$WORK/facilitator-note.txt"
printf 'The Lab lead succession plan is codenamed MARIGOLD-12.\n' > "$WORK/lead-note.txt"
upload "$(admin_token)" "$WORK/facilitator-note.txt" facilitators-knowledge-id >/dev/null
upload "$(admin_token)" "$WORK/lead-note.txt" leads-knowledge-id >/dev/null
sleep 8
BUDGET='What is the facilitator budget code?'
PLAN='What is the Lab lead succession plan codenamed?'
check "open level: no facilitator text" lacks TANGERINE "$COLLEAGUE_TOKEN" "$BUDGET"
check "access command sets a level"    grep -q "'facilitators' access level" <("$APP/privatellm" access "$COLLEAGUE_EMAIL" facilitators)
check "facilitator sees facilitator text" replies TANGERINE "$COLLEAGUE_TOKEN" "$BUDGET"
check "facilitator sees no Lab lead text" lacks MARIGOLD "$COLLEAGUE_TOKEN" "$PLAN"
"$APP/privatellm" access "$COLLEAGUE_EMAIL" leads >/dev/null
check "Lab lead sees facilitator text" replies TANGERINE "$COLLEAGUE_TOKEN" "$BUDGET"
check "Lab lead sees Lab lead text"    replies MARIGOLD "$COLLEAGUE_TOKEN" "$PLAN"
"$APP/privatellm" access "$COLLEAGUE_EMAIL" open >/dev/null
check "back to open: no facilitator text" lacks TANGERINE "$COLLEAGUE_TOKEN" "$BUDGET"
check "back to open: no Lab lead text" lacks MARIGOLD "$COLLEAGUE_TOKEN" "$PLAN"

# --- Curator approval: a submission is not searchable until approved -----------------
WRITER_EMAIL="quiet-heron@mirah.local"; WRITER_PASSWORD="Writer-passw0rd-321!"
post_json /api/v1/auths/signup "{\"name\":\"Writer\",\"email\":\"$WRITER_EMAIL\",\"password\":\"$WRITER_PASSWORD\"}" >/dev/null
approve_user "$WRITER_EMAIL" "$WRITER_PASSWORD" "Writer" >/dev/null
WRITER_TOKEN="$(login "$WRITER_EMAIL" "$WRITER_PASSWORD")"
WRITER_ID="$(curl -fsS -H "Authorization: Bearer $WRITER_TOKEN" "$BASE/api/v1/auths/" | field id)"
printf 'The workshop mascot is a QUOKKA named Pebble.\n' > "$WORK/submission.txt"
check "non-contributor cannot submit"  bash -c "[[ '$(upload "$WRITER_TOKEN" "$WORK/submission.txt" submissions-knowledge-id)' != 200 ]] || ! grep -q submission.txt <('$APP/privatellm' library pending)"
"$APP/privatellm" contributor "$WRITER_EMAIL" yes >/dev/null
check "contributor can submit"         test "$(upload "$WRITER_TOKEN" "$WORK/submission.txt" submissions-knowledge-id)" = "200"
sleep 8
"$APP/privatellm" library pending > "$WORK/pending.log" 2>&1 || true
check "it waits in the queue"          grep -q "submission.txt" "$WORK/pending.log"
SUBMISSION_ID="$(grep submission.txt "$WORK/pending.log" | tail -n 1 | cut -d' ' -f1)"
MASCOT='What is the workshop mascot?'
check "a curator can read it first"    grep -q "QUOKKA" <("$APP/privatellm" library show "$SUBMISSION_ID")
check "unapproved text is not used"    lacks QUOKKA "$COLLEAGUE_TOKEN" "$MASCOT"
check "approval needs a named curator" bash -c "! '$APP/privatellm' library approve '$SUBMISSION_ID' >/dev/null 2>&1"
"$APP/privatellm" library approve "$SUBMISSION_ID" --level open --by "Test Curator" > "$WORK/approve.log" 2>&1 || true
check "a curator approves it"          grep -q "Approved into" "$WORK/approve.log"
APPROVED_ID="$(grep "Approved into" "$WORK/approve.log" | sed 's/.* as \([^.]*\)\..*/\1/')"
sleep 8
check "the submitter's own copy is gone" test "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(admin_token)" "$BASE/api/v1/files/$SUBMISSION_ID")" = "404"
check "the submitter cannot change it" bash -c "[[ '$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/v1/files/$APPROVED_ID/data/content/update" -H "Authorization: Bearer $WRITER_TOKEN" -H "Content-Type: application/json" -d '{"content":"tampered"}')' != 200 ]]"
check "approved text is used at once"  replies QUOKKA "$COLLEAGUE_TOKEN" "$MASCOT"
check "the queue is empty again"       grep -q "Nothing is waiting" <("$APP/privatellm" library pending)
check "a curator removes it"           grep -q "no longer answers" <("$APP/privatellm" library remove "$APPROVED_ID" --by "Test Curator")
check "removed text is gone"           lacks QUOKKA "$COLLEAGUE_TOKEN" "$MASCOT"
printf 'A rejected note about ZEPPELIN parking.\n' > "$WORK/reject-me.txt"
upload "$WRITER_TOKEN" "$WORK/reject-me.txt" submissions-knowledge-id >/dev/null
sleep 5
REJECT_ID="$("$APP/privatellm" library pending | grep reject-me.txt | cut -d' ' -f1)"
check "a curator rejects one"          grep -q "Rejected" <("$APP/privatellm" library reject "$REJECT_ID" --by "Test Curator")
check "rejected file is deleted"       test "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $(admin_token)" "$BASE/api/v1/files/$REJECT_ID")" = "404"

# --- Training examples: opt-in, scrubbed, reviewed, and a gated training run --------
say "$COLLEAGUE_TOKEN" "Summarise the parking policy" >/dev/null
check "no opt-in, nothing is collected" grep -q "^0 example" <("$APP/privatellm" training list)
check "training opt-in is recorded"    replies "may be used to improve" "$COLLEAGUE_TOKEN" "I agree to training"
say "$COLLEAGUE_TOKEN" "Write to jo@example.org about the Colleague parking permit" >/dev/null
"$APP/privatellm" training list > "$WORK/examples.log" 2>&1 || true
check "an example is collected"        grep -q "^1 example" "$WORK/examples.log"
"$APP/privatellm" access "$COLLEAGUE_EMAIL" facilitators >/dev/null
say "$COLLEAGUE_TOKEN" "What is the facilitator budget code?" >/dev/null
check "nothing is collected from a facilitator" grep -q "^1 example" <("$APP/privatellm" training list)
"$APP/privatellm" access "$COLLEAGUE_EMAIL" open >/dev/null
say "$(admin_token)" "I agree to training" >/dev/null; say "$(admin_token)" "What is the Lab lead succession plan codenamed?" >/dev/null
check "nothing is collected from the admin" grep -q "^1 example" <("$APP/privatellm" training list)
check "its email address is removed"   bash -c "grep -q '\[EMAIL\]' '$WORK/examples.log' && ! grep -q 'jo@example.org' '$WORK/examples.log'"
check "the person's own name is removed" grep -q "\[NAME\] parking" "$WORK/examples.log"
check "no document text is copied in"  bash -c "! grep -q 'Respond to the user query' '$WORK/examples.log'"
check "it starts unreviewed"           grep -q "pending" "$WORK/examples.log"
check "review needs a named reviewer"  bash -c "! '$APP/privatellm' training approve 1 >/dev/null 2>&1"
check "a reviewer approves it"         grep -q "Example 1: approved" <("$APP/privatellm" training approve 1 --by "Test Reviewer")
check "the training set is built"      grep -q "Wrote 1 approved" <("$APP/privatellm" training build)
check "training set holds the example" grep -q '"role": "assistant"' "$APP/data/training/train.jsonl"
check "too few examples: no training"  grep -q "at least 500" <("$APP/privatellm" training run --by "Test Approver" 2>&1)
check "no trainer set: no training"    grep -q "TRAIN_COMMAND is not set" <(TRAINING_MIN_EXAMPLES=1 "$APP/privatellm" training run --by "Test Approver" 2>&1)
check "training needs a named approver" bash -c "! TRAINING_MIN_EXAMPLES=1 '$APP/privatellm' training run >/dev/null 2>&1"
printf '#!/bin/sh\nwc -l < "$MIRAH_TRAINING_DIR/train.jsonl" > "$1"\n' > "$WORK/trainer.sh"
TRAINING_MIN_EXAMPLES=1 TRAIN_COMMAND="sh $WORK/trainer.sh $WORK/trained.txt" "$APP/privatellm" training run --by "Test Approver" > "$WORK/train.log" 2>&1 || true
check "the trainer is handed the set"  test "$(tr -d ' ' < "$WORK/trained.txt")" = "1"
check "withdrawing deletes the examples" replies "1 example(s) collected from you were deleted" "$COLLEAGUE_TOKEN" "Withdraw training"
check "and the built training set"     test ! -e "$APP/data/training/train.jsonl"

# --- Export, deletion and the audit trail ---------------------------------------------
# Questions sent straight to the API are not kept; the browser saves each conversation like this.
check "a conversation is saved"        test "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/v1/chats/new" -H "Authorization: Bearer $COLLEAGUE_TOKEN" -H "Content-Type: application/json" \
  -d '{"chat":{"title":"Office hours","messages":[{"role":"user","content":"When does the Zanzibar office open?"}]}}')" = "200"
"$APP/privatellm" export-user "$COLLEAGUE_EMAIL" > "$WORK/export.log" 2>&1 || true
EXPORT_FILE="$(ls "$APP"/exports/*.json 2>/dev/null | head -n 1)"
check "export holds their conversations" grep -q "Zanzibar" "$EXPORT_FILE"
check "export holds their other records" grep -q '"other_records"' "$EXPORT_FILE"
check "export holds their consent"     grep -q '"purpose": "training"' "$EXPORT_FILE"
check "export file is private"         test "$(stat -c %a "$EXPORT_FILE" 2>/dev/null || stat -f %Lp "$EXPORT_FILE")" = "600"
check "the admin cannot be deleted"    grep -q "cannot be deleted" <("$APP/privatellm" delete-user "$ADMIN_EMAIL" --yes 2>&1)
check "deletion asks first"            grep -q "Nothing was deleted" <(echo no | "$APP/privatellm" delete-user "$WRITER_EMAIL" 2>&1)
COLLEAGUE_ID="$(curl -fsS -H "Authorization: Bearer $COLLEAGUE_TOKEN" "$BASE/api/v1/auths/" | field id)"
curl -s -o /dev/null -X POST "$BASE/api/v1/auths/api_key" -H "Authorization: Bearer $COLLEAGUE_TOKEN"
"$APP/privatellm" delete-user "$COLLEAGUE_EMAIL" --yes > "$WORK/delete.log" 2>&1 || true
check "no row anywhere still names them" test "$(python3 -c "
import sqlite3, sys
db = sqlite3.connect(sys.argv[1]); total = 0
for (table,) in db.execute(\"select name from sqlite_master where type='table'\").fetchall():
    if any(c[1] == 'user_id' for c in db.execute(f'pragma table_info(\"{table}\")')):
        total += db.execute(f'select count(*) from \"{table}\" where user_id = ?', (sys.argv[2],)).fetchone()[0]
print(total + db.execute('select count(*) from user where id = ?', (sys.argv[2],)).fetchone()[0] + db.execute('select count(*) from auth where id = ?', (sys.argv[2],)).fetchone()[0])" "$APP/data/webui.db" "$COLLEAGUE_ID")" = "0"
check "deletion reports what went"     grep -q "consent record(s)" "$WORK/delete.log"
check "a deleted person cannot sign in" test "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/api/v1/auths/signin" -H "Content-Type: application/json" -d "{\"email\":\"$COLLEAGUE_EMAIL\",\"password\":\"$COLLEAGUE_PASSWORD\"}")" = "400"
check "their old session stops working" test "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $COLLEAGUE_TOKEN" "$BASE/api/v1/chats/")" = "401"
check "their conversations are gone"   test "$(python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select count(*) from chat c left join user u on u.id=c.user_id where u.id is null').fetchone()[0])" "$APP/data/webui.db")" = "0"
check "their consent records are gone" test "$(python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('select count(*) from consent where user_id not in (?, ?)', sys.argv[2:4]).fetchone()[0])" "$APP/data/mirah.db" "$(login "$ADMIN_EMAIL" "$ADMIN_PASSWORD" id)" "$WRITER_ID")" = "0"
"$APP/privatellm" audit > "$WORK/audit.log" 2>&1 || true
check "audit shows consent"            grep -q "consent.granted.use" "$WORK/audit.log"
check "audit shows the approval"       grep -q "Test Curator  library.approved" "$WORK/audit.log"
check "audit shows the deletion"       grep -q "user.deleted" "$WORK/audit.log"
check "audit holds no email address"   bash -c "! grep -q '@' <(grep -v 'audit.log' '$WORK/audit.log')"
check "browser actions are logged too" test -s "$APP/data/audit.log"

# --- A new version of the notice asks everyone again ---------------------------------
say "$WRITER_TOKEN" "I agree" >/dev/null
check "writer can ask after agreeing"  replies '"choices"' "$WRITER_TOKEN" "Hello"
sed -i.bak '1s/.*/Version: 2/' "$APP/config/consent-notice.txt"
check "a new notice version asks again" replies "Before you use MIRAH" "$WRITER_TOKEN" "Hello"

echo
if (( failures == 0 )); then
  echo "All checks passed."
else
  echo "$failures check(s) failed. Last lines of the server log:"
  tail -n 20 "$APP/logs/webui.log" | cut -c1-300
fi
exit "$failures"
