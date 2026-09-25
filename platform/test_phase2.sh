#!/usr/bin/env bash
set -u

API="${API:-http://localhost:8000}"
TOKEN="${STREAM_WEBHOOK_TOKEN:-test-token-123}"
PASSED=0; FAILED=0; SKIPPED=0
ok() { PASSED=$((PASSED+1)); echo "  PASS: $1"; }
bad() { FAILED=$((FAILED+1)); echo "  FAIL: $1"; }
skip() { SKIPPED=$((SKIPPED+1)); echo "  SKIP: $1"; }

echo "=== 1. Pages load ==="
HTML=$(curl -sf "$API/play/some-video-id" 2>/dev/null)
echo "$HTML" | grep -q "Video Tutor" && ok "player page served" || bad "player page missing"
UPLOAD_HTML=$(curl -sf "$API/upload" 2>/dev/null)
echo "$UPLOAD_HTML" | grep -q "Upload a new lesson" && ok "upload page served" || bad "upload page missing"

echo "=== 2. Register a lesson ==="
VID=$(curl -sf -X POST "$API/v1/videos" -H "Content-Type: application/json" \
  -d '{"title":"Phase 2 check"}' |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["video_id"])' 2>/dev/null)
if [ -n "$VID" ]; then ok "video created: $VID"; else bad "could not create video"; exit 1; fi

echo "=== 3. Upload ticket endpoint ==="
TICKET=$(curl -s -X POST "$API/v1/videos/$VID/upload-url")
if echo "$TICKET" | grep -q "upload_url"; then
  ok "upload ticket issued"
elif echo "$TICKET" | grep -qi "not configured"; then
  skip "Cloudflare keys not set"
else
  bad "unexpected ticket response: $TICKET"
fi

echo "=== 4. Webhook rejects strangers ==="
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$API/v1/webhooks/stream?token=WRONG" -H "Content-Type: application/json" \
  -d '{"uid":"x","status":"ready"}')
if [ "$CODE" = "401" ] || [ "$CODE" = "403" ]; then ok "wrong token rejected ($CODE)"; else bad "wrong token got $CODE"; fi

echo "=== 5. Webhook marks a video playable ==="
PSQL="docker compose exec -T postgres psql -U arcnet -d arcnet"
$PSQL -q -c "INSERT INTO videos (title, provider, provider_video_id, upload_status)
  VALUES ('webhook check', 'cloudflare', 'fake-uid-001', 'pending')
  ON CONFLICT DO NOTHING;" 2>/dev/null
FAKE_ID=$($PSQL -tA -q -c "SELECT id FROM videos WHERE provider_video_id = 'fake-uid-001';" 2>/dev/null | head -1)
if [ -z "$FAKE_ID" ]; then
  skip "cannot reach db to seed row"
else
  curl -sf -X POST "$API/v1/webhooks/stream?token=$TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"uid":"fake-uid-001","status":"ready","result":{"duration":62.0}}' >/dev/null
  STATUS=$(curl -sf "$API/v1/videos/$FAKE_ID/player-info" 2>/dev/null |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["upload_status"])' 2>/dev/null)
  [ "$STATUS" = "playable" ] && ok "webhook marked video playable" || bad "upload_status is '$STATUS'"
fi

echo
echo "RESULT: $PASSED passed, $FAILED failed, $SKIPPED skipped"
[ "$FAILED" = "0" ]