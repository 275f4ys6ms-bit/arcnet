#!/usr/bin/env bash
# ============================================================
# Smoke test for the Phase 1 platform.
# Run from inside the platform/ folder, with the services up:
#   docker compose up --build     (terminal 1, leave running)
#   bash smoke.sh                 (terminal 2)
#
# At the end it prints a score. Paste the output to your
# review session if anything fails.
# ============================================================
set -u

API="${API:-http://localhost:8000}"
SRT_FILE="${SRT_FILE:-sample.srt}"
FREE_DAILY="${FREE_DAILY:-5}"

PASSED=0
FAILED=0

ok()   { PASSED=$((PASSED+1)); echo "  PASS: $1"; }
bad()  { FAILED=$((FAILED+1)); echo "  FAIL: $1"; }

# --- helper: make JSON safely from the sample lesson -------------------
json_body() {  # $1=title -> prints {"title": ..., "srt": ...}
  python3 -c '
import json, sys
print(json.dumps({"title": sys.argv[1], "srt": open(sys.argv[2], encoding="utf-8").read()}))
' "$1" "$SRT_FILE"
}

echo "=== 1. Waiting for the API to wake up ==="
ALIVE=0
for i in $(seq 1 60); do
  if curl -sf "$API/docs" >/dev/null 2>&1; then ALIVE=1; break; fi
  sleep 5
done
[ "$ALIVE" = "1" ] && ok "API is up at $API" || { bad "API never came up — check: docker compose logs tutor"; exit 1; }

echo "=== 2. Registering the sample lesson ==="
VIDEO_JSON=$(curl -sf -X POST "$API/v1/videos" -H "Content-Type: application/json" \
  -d "$(json_body "Smoke test lesson")")
VID=$(echo "$VIDEO_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["video_id"])')
[ -n "$VID" ] && ok "video registered: $VID" || { bad "could not register video"; exit 1; }

echo "=== 3. Waiting for the pack maker to finish ==="
READY=0
for i in $(seq 1 24); do
  STATUS=$(curl -sf "$API/v1/videos/$VID" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' 2>/dev/null)
  if [ "$STATUS" = "ready" ]; then READY=1; break; fi
  if [ "$STATUS" = "failed" ]; then break; fi
  sleep 5
done
[ "$READY" = "1" ] && ok "video is ready (cards filed)" || bad "video status is '$STATUS' — check: docker compose logs ingestor"

echo "=== 4. Opening a tutoring session ==="
SID=$(curl -sf -X POST "$API/v1/sessions" -H "Content-Type: application/json" \
  -d "{\"user_id\": \"smoke-learner\", \"video_id\": \"$VID\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
[ -n "$SID" ] && ok "session opened: $SID" || { bad "could not open session"; exit 1; }

echo "=== 5. Asking questions (answers should stream, with moments) ==="
ask() {  # $1=question $2=request-id $3=watch-time
  curl -sN -X POST "$API/v1/sessions/$SID/question" \
    -H "Content-Type: application/json" \
    -d "{\"question\": \"$1\", \"watch_time\": $3, \"client_request_id\": \"$2\"}"
}
Q1=$(ask "why should I rinse the rice?" smoke-q1 20)
echo "$Q1" | grep -q '"type": "done"'        && ok "Q1 answered"            || bad "Q1 no 'done' event — raw: $(echo "$Q1" | tail -1)"
echo "$Q1" | grep -q '"type": "citations"'   && ok "Q1 came with moments"   || bad "Q1 missing moments"
echo "$Q1" | grep -qi "starch"               && ok "Q1 answer mentions starch (correct topic)" || bad "Q1 off-topic answer: $(echo "$Q1" | tail -1)"

ask "how much water for brown rice?" smoke-q2 110 >/dev/null && ok "Q2 answered" || bad "Q2 failed"
ask "what is the capital of France?" smoke-q3 30 > /tmp/smoke_q3.txt
grep -qi "outside" /tmp/smoke_q3.txt && ok "Q3 honestly says 'outside the lesson'" || bad "Q3 should have said outside-the-lesson"

echo "=== 6. Daily free limit (default: $FREE_DAILY) ==="
LIMIT_SEEN=0
for n in 4 5 6 7 8; do
  OUT=$(ask "recap the recipe please" smoke-q$n 200)
  echo "$OUT" | grep -q '"type": "limit_reached"' && { LIMIT_SEEN=1; break; }
done
[ "$LIMIT_SEEN" = "1" ] && ok "limit message appears after $FREE_DAILY free questions" \
                        || bad "limit never triggered — quota may not be enforced"

echo "=== 7. Retries are free (no double-charging) ==="
RETRY=$(ask "why should I rinse the rice?" smoke-q1 20)
echo "$RETRY" | grep -q '"cached": true' && ok "retry returned the saved answer (free)" || bad "retry was not served from cache"

echo "=== 8. History is recorded ==="
HIST=$(curl -sf "$API/v1/sessions/$SID/history")
echo "$HIST" | grep -q "rinse" && ok "history contains the questions" || bad "history missing questions"

echo
echo "============================================"
echo "  RESULT: $PASSED passed, $FAILED failed"
echo "============================================"
[ "$FAILED" = "0" ] && exit 0 || exit 1
