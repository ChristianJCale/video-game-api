#!/usr/bin/env bash
#
# CRUD test run for the Video Game API.
#
# Usage (from the repo root):
#   export BASE="https://<your-function-app-domain>/api"
#   read -rs -p "API key: " KEY; export KEY; echo
#   bash scripts/azure_crud_tests.sh
#
# The API key is never printed, so the output is safe to screenshot.
# Each test prints: request, expected status, actual status, response, result.

set -u

: "${BASE:?Set BASE to your API address, e.g. https://<app>.azurewebsites.net/api}"
: "${KEY:?Set KEY to your API key}"
BASE="${BASE%/}"

PASS=0
FAIL=0
N=0
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

STATUS=""
RESPONSE=""
CASE_OK=1

# call METHOD PATH [BODY] [KEY]   (pass "" as KEY to send no key header)
call() {
  local method="$1" path="$2" body="${3-}" key="${4-$KEY}"
  local args=(-sS --max-time 180 -X "$method" -o "$TMP" -w '%{http_code}')
  [ -n "$key" ] && args+=(-H "x-api-key: $key")
  [ -n "$body" ] && args+=(-H "Content-Type: application/json" -d "$body")
  STATUS="$(curl "${args[@]}" "$BASE$path")" || STATUS="000"
  RESPONSE="$(cat "$TMP")"
}

# test_case TITLE METHOD PATH EXPECTED_STATUS [BODY] [KEY]
test_case() {
  N=$((N + 1))
  call "$2" "$3" "${5-}" "${6-$KEY}"
  CASE_OK=1
  [ "$STATUS" = "$4" ] || CASE_OK=0
  local shown="$RESPONSE"
  [ "${#shown}" -gt 400 ] && shown="${shown:0:400}..."
  printf '\nT%02d  %s\n' "$N" "$1"
  printf '  Request : %s %s%s\n' "$2" "$BASE" "$3"
  printf '  Expected: HTTP %s\n' "$4"
  printf '  Actual  : HTTP %s\n' "$STATUS"
  printf '  Response: %s\n' "$shown"
}

# verdict [EXTRA_OK 1|0] [WHAT_WAS_CHECKED]
verdict() {
  local extra="${1-1}" what="${2-}" result="PASS"
  if [ -n "$what" ]; then
    printf '  Checked : %s -> %s\n' "$what" "$([ "$extra" = 1 ] && echo yes || echo NO)"
  fi
  if [ "$CASE_OK" = 1 ] && [ "$extra" = 1 ]; then
    PASS=$((PASS + 1))
  else
    result="FAIL"
    FAIL=$((FAIL + 1))
  fi
  printf '  Result  : %s\n' "$result"
}

has() {  # has SUBSTRING -> 1 if the last response contains it
  case "$RESPONSE" in *"$1"*) echo 1 ;; *) echo 0 ;; esac
}

jget() {  # jget JSON FIELD
  python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get(sys.argv[2], ""))' "$1" "$2" 2>/dev/null
}

is_uuid() {
  [[ "$1" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] && echo 1 || echo 0
}

summary() {
  printf '\n=============================================\n'
  printf 'Passed: %d   Failed: %d   Total: %d\n' "$PASS" "$FAIL" "$((PASS + FAIL))"
  printf '=============================================\n'
}

GOOD='{"title":"Test Game Azure","developer":"Test Studio","releaseDate":"2024-05-01","price":19.99,"imageUrl":"https://example.com/test-game.jpg"}'
UPDATED='{"title":"Test Game Azure (Updated)","developer":"Test Studio","releaseDate":"2024-05-01","price":9.99}'
MISSING_ID="00000000-0000-4000-8000-000000000000"

printf 'Video Game API - CRUD tests\n'
printf 'Target : %s\n' "$BASE"
printf 'Run at : %s (UTC)\n' "$(date -u '+%Y-%m-%d %H:%M:%S')"
printf '(The first request can take up to a minute if the database was idle.)\n'

# --- Security ---
test_case "Request without an API key is rejected" GET /games 401 "" ""
verdict
test_case "Request with a wrong API key is rejected" GET /games 401 "" "wrong-key"
verdict

# --- Create / Read ---
test_case "Create a game (valid body)" POST /games 201 "$GOOD"
GAME_ID="$(jget "$RESPONSE" id)"
verdict "$(is_uuid "$GAME_ID")" "id is a lowercase UUID"
if [ -z "$GAME_ID" ]; then
  printf '\nCreate failed, so the remaining tests cannot run.\n'
  summary
  exit 1
fi

test_case "Get the game by id" GET "/games/$GAME_ID" 200
verdict "$(has "\"id\": \"$GAME_ID\"")" "response contains the same id"

test_case "List games includes the new game" GET /games 200
verdict "$(has "$GAME_ID")" "list contains the new id"

# --- Update ---
test_case "Update the game" PUT "/games/$GAME_ID" 200 "$UPDATED"
verdict "$(has "(Updated)")" "title changed"

test_case "Update is persisted (read it back)" GET "/games/$GAME_ID" 200
verdict "$(has "(Updated)")" "read-back shows the new title"

# --- Validation errors ---
test_case "Create with an impossible date is rejected" POST /games 400 \
  '{"title":"Bad Date","developer":"X","releaseDate":"2026-13-45","price":10}'
verdict
test_case "Create with a negative price is rejected" POST /games 400 \
  '{"title":"Bad Price","developer":"X","releaseDate":"2024-05-01","price":-5}'
verdict
test_case "Create with a missing title is rejected" POST /games 400 \
  '{"developer":"X","releaseDate":"2024-05-01","price":10}'
verdict

# --- Not found ---
test_case "Get an id that does not exist" GET "/games/$MISSING_ID" 404
verdict
test_case "Get an id that is not a UUID" GET /games/not-a-uuid 404
verdict
test_case "Update an id that does not exist" PUT "/games/$MISSING_ID" 404 "$GOOD"
verdict

# --- Delete ---
test_case "Delete the game" DELETE "/games/$GAME_ID" 200
verdict "$(has "$GAME_ID")" "response confirms the deleted id"
test_case "Delete the same game again" DELETE "/games/$GAME_ID" 404
verdict
test_case "Get the deleted game" GET "/games/$GAME_ID" 404
verdict

summary
[ "$FAIL" -eq 0 ]
