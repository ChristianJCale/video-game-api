#!/usr/bin/env bash
#
# Validation test run for PATCH /api/games/validate (upcoming / free / normal records).
#
# Usage (from the repo root):
#   export BASE="https://<your-function-app-domain>/api"
#   read -rs -p "API key: " KEY; export KEY; echo
#   bash scripts/validate_tests.sh
#
# The API key is never printed, so the output is safe to screenshot.
# The script creates four "VT ..." test games and deletes them at the end.
# Every game in the database is evaluated by a validation run, so the script first
# runs validation once to bring existing games up to date; after that the
# updatedCount values below depend only on the four test games.

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
IDS=()

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
  printf '\nV%02d  %s\n' "$N" "$1"
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

eq() {  # eq A B -> 1 if equal and not empty
  [ -n "$1" ] && [ "$1" = "$2" ] && echo 1 || echo 0
}

is_utc_stamp() {
  [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] && echo 1 || echo 0
}

summary() {
  printf '\n=============================================\n'
  printf 'Passed: %d   Failed: %d   Total: %d\n' "$PASS" "$FAIL" "$((PASS + FAIL))"
  printf '=============================================\n'
}

cleanup() {
  printf '\nCleanup: deleting the test games\n'
  for id in "${IDS[@]:-}"; do
    [ -n "$id" ] || continue
    call DELETE "/games/$id"
    printf '  DELETE %s -> HTTP %s\n' "$id" "$STATUS"
  done
}

create() {  # create TITLE RELEASE_DATE PRICE  -> sets NEW_ID
  call POST /games "{\"title\":\"$1\",\"developer\":\"Validation Test\",\"releaseDate\":\"$2\",\"price\":$3}"
  NEW_ID="$(jget "$RESPONSE" id)"
  [ -n "$NEW_ID" ] && IDS+=("$NEW_ID")
  printf '  Created %-12s %s  date=%s price=%s -> HTTP %s\n' "$1" "$NEW_ID" "$2" "$3" "$STATUS"
}

# Dates are relative to today (UTC) so the test keeps working after today
FUTURE="$(python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).date() + d.timedelta(days=400))')"
PAST="2020-03-12"

printf 'Video Game API - validation tests\n'
printf 'Target : %s\n' "$BASE"
printf 'Run at : %s (UTC)\n' "$(date -u '+%Y-%m-%d %H:%M:%S')"
printf 'Dates  : future=%s  past=%s\n' "$FUTURE" "$PAST"
printf '(The first request can take up to a minute if the database was idle.)\n'

# --- Security ---
test_case "Validate without an API key is rejected" PATCH /games/validate 401 "" ""
verdict
test_case "Validate with a wrong API key is rejected" PATCH /games/validate 401 "" "wrong-key"
verdict

# --- Setup ---
printf '\nSetup: bring existing games up to date, then create four test games\n'
call PATCH /games/validate
printf '  Baseline validation -> HTTP %s  %s\n' "$STATUS" "$RESPONSE"
[ "$STATUS" = "200" ] || { printf 'Baseline validation failed; stopping.\n'; summary; exit 1; }

create "VT Upcoming" "$FUTURE" 59.99; UP_ID="$NEW_ID"
create "VT Free"     "$PAST"   0;     FREE_ID="$NEW_ID"
create "VT Both"     "$FUTURE" 0;     BOTH_ID="$NEW_ID"
create "VT Normal"   "$PAST"   19.99; NORMAL_ID="$NEW_ID"
if [ -z "$UP_ID" ] || [ -z "$FREE_ID" ] || [ -z "$BOTH_ID" ] || [ -z "$NORMAL_ID" ]; then
  printf '\nCould not create all test games, so the tests cannot run.\n'
  cleanup; summary; exit 1
fi

# --- Before validation ---
test_case "New game starts with default flags and no validatedOn" GET "/games/$UP_ID" 200
verdict "$([ "$(has '"upcoming": false')$(has '"isFree": false')$(has '"validatedOn": null')" = 111 ] && echo 1 || echo 0)" \
  "upcoming=false, isFree=false, validatedOn=null"

# --- First validation run ---
test_case "Validate: three of the four test games change" PATCH /games/validate 200
UPDATED="$(jget "$RESPONSE" updatedCount)"
TS1="$(jget "$RESPONSE" timestamp)"
verdict "$(eq "$UPDATED" 3)" "updatedCount is 3 (Upcoming, Free, Both; Normal unchanged)"
printf '  Timestamp: %s\n' "$TS1"

test_case "Timestamp is UTC ISO 8601 ending in Z" GET "/games/$UP_ID" 200
verdict "$(is_utc_stamp "$TS1")" "run timestamp matches YYYY-MM-DDTHH:MM:SSZ"

test_case "Upcoming game: future date, paid" GET "/games/$UP_ID" 200
verdict "$([ "$(has '"upcoming": true')$(has '"isFree": false')" = 11 ] && echo 1 || echo 0)" "upcoming=true, isFree=false"

test_case "Free game: past date, price 0" GET "/games/$FREE_ID" 200
verdict "$([ "$(has '"upcoming": false')$(has '"isFree": true')" = 11 ] && echo 1 || echo 0)" "upcoming=false, isFree=true"

test_case "Both game: future date and price 0" GET "/games/$BOTH_ID" 200
verdict "$([ "$(has '"upcoming": true')$(has '"isFree": true')" = 11 ] && echo 1 || echo 0)" "upcoming=true, isFree=true"

test_case "Normal game: past date, paid" GET "/games/$NORMAL_ID" 200
verdict "$([ "$(has '"upcoming": false')$(has '"isFree": false')" = 11 ] && echo 1 || echo 0)" "both flags false"
verdict "$(has "\"validatedOn\": \"$TS1\"")" "validatedOn equals the run timestamp even though nothing changed"

# --- Second run changes nothing ---
test_case "Validate again: nothing left to change" PATCH /games/validate 200
UPDATED2="$(jget "$RESPONSE" updatedCount)"
TS2="$(jget "$RESPONSE" timestamp)"
verdict "$(eq "$UPDATED2" 0)" "updatedCount is 0"

test_case "validatedOn is refreshed on every run" GET "/games/$NORMAL_ID" 200
verdict "$(has "\"validatedOn\": \"$TS2\"")" "validatedOn equals the second run timestamp"

# --- Flags go both ways, and only refresh when validation runs ---
test_case "Edit the upcoming game's date to the past" PUT "/games/$UP_ID" 200 \
  "{\"title\":\"VT Upcoming\",\"developer\":\"Validation Test\",\"releaseDate\":\"$PAST\",\"price\":59.99}"
verdict "$(has '"upcoming": true')" "flag is still true until validation runs"

test_case "Validate: the upcoming flag is cleared" PATCH /games/validate 200
verdict "$(eq "$(jget "$RESPONSE" updatedCount)" 1)" "updatedCount is 1"
test_case "Read back the edited game" GET "/games/$UP_ID" 200
verdict "$(has '"upcoming": false')" "upcoming is now false"

test_case "Edit the normal game's price to 0" PUT "/games/$NORMAL_ID" 200 \
  "{\"title\":\"VT Normal\",\"developer\":\"Validation Test\",\"releaseDate\":\"$PAST\",\"price\":0}"
verdict
test_case "Validate: the free flag is set" PATCH /games/validate 200
verdict "$(eq "$(jget "$RESPONSE" updatedCount)" 1)" "updatedCount is 1"
test_case "Read back the repriced game" GET "/games/$NORMAL_ID" 200
verdict "$(has '"isFree": true')" "isFree is now true"

cleanup
summary
[ "$FAIL" -eq 0 ]
