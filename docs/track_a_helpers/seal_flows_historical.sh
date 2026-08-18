export PGPASSWORD="postgres"
#!/usr/bin/env bash

BASE_URL="${BASE_URL:-http://localhost:8090/api}"
DB="${DB:-seal_hackathon}"
PASSWORD="${SEAL_USER_PASSWORD:-Test@123456}"
COORD_EMAIL="coordinator@seal.eval"
COORD_PASS="${SEAL_COORD_PASSWORD:-Eval@1234567}"

FLOW_ID="global"
BEARER=""
AUTH=() 

_set_auth() {
  if [[ -n "$BEARER" ]]; then
    AUTH=(-H "Authorization: Bearer $BEARER")
  else
    AUTH=()
  fi
}

approve_user() {
  psql "postgresql://postgres:postgres@localhost:5432/$DB" -c \
    "UPDATE users SET status='approved' WHERE id='$1';" > /dev/null
}

login() {
  local email="$1" pass="$2"
  post /auth/login -d "{\"email\":\"$email\",\"password\":\"$pass\"}" | jq -r '.accessToken // empty'
}

register_and_approve() {
  local email="$1" name="$2"
  local id
  id=$(post /auth/register \
    -d "{\"email\":\"$email\",\"password\":\"$PASSWORD\",\"fullName\":\"$name\"}" \
    | jq -r '.user.id')
  approve_user "$id"
  echo "$id"
}

TS=$(date +%s)
export TS

require_vars() {
  local missing=0
  for var in "$@"; do
    if [[ -z "${!var}" || "${!var}" == "null" ]]; then
      echo "[ERROR] Required variable \$$var is empty. Did a previous flow fail?"
      missing=1
    fi
  done
  [[ $missing -eq 0 ]] || { echo "[ABORT] Fix missing variables above before re-running."; return 1; }
}

_curl() {
  if [[ "${CURL_VERBOSE:-0}" == "1" ]]; then
    curl -S "$@"
  else
    curl -sS "$@" 
  fi
}

post()  { _set_auth; _curl -X POST   "$BASE_URL$1" -H "Content-Type: application/json" -H "X-Flow-ID: $FLOW_ID" "${AUTH[@]}" "${@:2}"; }
get()   { _set_auth; _curl -X GET    "$BASE_URL$1"                                      -H "X-Flow-ID: $FLOW_ID" "${AUTH[@]}" "${@:2}"; }
patch() { _set_auth; _curl -X PATCH  "$BASE_URL$1" -H "Content-Type: application/json" -H "X-Flow-ID: $FLOW_ID" "${AUTH[@]}" "${@:2}"; }
put()   { _set_auth; _curl -X PUT    "$BASE_URL$1" -H "Content-Type: application/json" -H "X-Flow-ID: $FLOW_ID" "${AUTH[@]}" "${@:2}"; }
del()   { _set_auth; _curl -X DELETE "$BASE_URL$1"                                      -H "X-Flow-ID: $FLOW_ID" "${AUTH[@]}" "${@:2}"; }

echo ""; echo "======================================================"
echo " SealHackathon P2S Evaluation Flows  [TS=$TS]"
echo "======================================================"

# ─── GLOBAL SETUP ─────────────────────────────────────────────────────────────
FLOW_ID="setup_coordinator_${TS}"

echo "[SETUP] Ensuring coordinator account exists with 'coordinator' role..."

COORD_REG=$(post /auth/register \
  -d "{\"email\":\"$COORD_EMAIL\",\"password\":\"$COORD_PASS\",\"fullName\":\"P2S Eval Coordinator\"}" 2>/dev/null || true)
COORD_ID=$(echo "$COORD_REG" | jq -r '.user.id // empty' 2>/dev/null)

if [[ -n "$COORD_ID" && "$COORD_ID" != "null" ]]; then
  echo "[SETUP] New coordinator registered: $COORD_ID"
else
  echo "[SETUP] Coordinator already exists — looking up by email..."
  COORD_ID=$(psql "postgresql://postgres:postgres@localhost:5432/$DB" -t -c \
    "SELECT id FROM users WHERE email='$COORD_EMAIL';" 2>/dev/null | tr -d ' \r\n')
  echo "[SETUP] Found existing coordinator: $COORD_ID"
fi

if [[ -n "$COORD_ID" ]]; then
  psql "postgresql://postgres:postgres@localhost:5432/$DB" > /dev/null 2>&1 <<SQL
UPDATE users SET status='approved' WHERE id='$COORD_ID';
INSERT INTO user_roles (user_id, role_id)
  SELECT '$COORD_ID', id FROM roles WHERE name='coordinator'
  ON CONFLICT DO NOTHING;
SQL
  echo "[SETUP] Coordinator approved + 'coordinator' role ensured."
fi

COORD_TOKEN=$(post /auth/login -d "{\"email\":\"$COORD_EMAIL\",\"password\":\"$COORD_PASS\"}" | jq -r '.accessToken // empty')

if [[ -z "$COORD_TOKEN" || "$COORD_TOKEN" == "null" ]]; then
  echo "[FATAL] Cannot login as coordinator."
  exit 1
fi

BEARER="$COORD_TOKEN"
TEST_RESP=$(get /users 2>/dev/null)
TEST_STATUS=$(echo "$TEST_RESP" | jq -r '.totalElements // empty' 2>/dev/null)
if [[ -z "$TEST_STATUS" ]]; then
  echo "[FATAL] Coordinator JWT does not have coordinator role."
  exit 1
fi
echo "[SETUP] COORDINATOR role confirmed. Ready to run flows."
export COORD_TOKEN BEARER

# ─── SF1: University & Campus Setup ──────────────────────────────────────────
sf1_university_campus() {
  FLOW_ID="sf1_university_campus_${TS}"
  echo ""; echo "── SF1: University & Campus Setup ──"
  BEARER="$COORD_TOKEN"

  local UNI; UNI=$(post /universities -d "{\"name\":\"FPT University ${TS}\",\"shortName\":\"FPTU\",\"country\":\"Vietnam\"}")
  UNI_ID=$(echo "$UNI" | jq -r '.id // empty')
  echo "  [1] University created: $UNI_ID"

  get /universities | jq '.content | length' > /dev/null
  echo "  [2] GET /universities OK"

  get /universities/"$UNI_ID" | jq '.id' > /dev/null
  echo "  [3] GET /universities/{id} OK"

  patch /universities/"$UNI_ID" -d '{"name":"FPT University Updated","shortName":"FPTU","country":"Vietnam"}' | jq '.id' > /dev/null
  echo "  [4] PATCH /universities/{id} OK"

  local CAMPUS; CAMPUS=$(post /campuses -d "{\"universityId\":\"$UNI_ID\",\"name\":\"HCMC Campus\",\"address\":\"Khu CNC, HCMC\",\"city\":\"Ho Chi Minh\"}")
  CAMPUS_ID=$(echo "$CAMPUS" | jq -r '.id // empty')
  echo "  [5] Campus created: $CAMPUS_ID"

  get /campuses | jq '.content | length' > /dev/null
  echo "  [6] GET /campuses OK"

  get /campuses/"$CAMPUS_ID" | jq '.id' > /dev/null
  echo "  [7] GET /campuses/{id} OK"

  patch /campuses/"$CAMPUS_ID" -d "{\"universityId\":\"$UNI_ID\",\"name\":\"HCMC Main Campus\",\"city\":\"Ho Chi Minh\"}" | jq '.id' > /dev/null
  echo "  [8] PATCH /campuses/{id} OK"

  export UNI_ID CAMPUS_ID COORD_TOKEN
}

# ─── SF2: User Management by Coordinator ─────────────────────────────────────
sf2_user_management() {
  FLOW_ID="sf2_user_management_${TS}"
  echo ""; echo "── SF2: User Management ──"
  require_vars COORD_TOKEN || return 1
  BEARER="$COORD_TOKEN"

  JUDGE_EMAIL="sf2-judge-${TS}@seal.eval"
  local JUDGE; JUDGE=$(post /users -d "{\"email\":\"$JUDGE_EMAIL\",\"password\":\"$PASSWORD\",\"fullName\":\"Judge SF2\",\"status\":\"approved\",\"roles\":[\"judge\"],\"expertise\":\"AI\",\"company\":\"ACME\"}")
  JUDGE_ID=$(echo "$JUDGE" | jq -r '.id // empty')
  echo "  [1] POST /users (judge) → $JUDGE_ID"

  MENTOR_EMAIL="sf2-mentor-${TS}@seal.eval"
  local MENTOR; MENTOR=$(post /users -d "{\"email\":\"$MENTOR_EMAIL\",\"password\":\"$PASSWORD\",\"fullName\":\"Mentor SF2\",\"status\":\"approved\",\"roles\":[\"mentor\"]}")
  MENTOR_ID=$(echo "$MENTOR" | jq -r '.id // empty')
  echo "  [2] POST /users (mentor) → $MENTOR_ID"

  get /users | jq '.content | length' > /dev/null
  echo "  [3] GET /users OK"

  get /users"?status=approved" | jq '.totalElements' > /dev/null
  echo "  [4] GET /users?status OK"

  get /users"?role=judge" | jq '.totalElements' > /dev/null
  echo "  [5] GET /users?role OK"

  get /users/"$JUDGE_ID" | jq '.id' > /dev/null
  echo "  [6] GET /users/{id} OK"

  patch /users/"$JUDGE_ID"/status -d '{"status":"approved"}' | jq '.status' > /dev/null
  echo "  [7] PATCH /users/{id}/status OK"

  patch /users/"$JUDGE_ID"/profile -d '{"fullName":"Judge SF2 Updated","expertise":"ML & Security","bio":"Expert judge"}' | jq '.fullName' > /dev/null
  echo "  [8] PATCH /users/{id}/profile OK"

  put /users/"$JUDGE_ID"/roles -d '{"roles":["judge"]}' | jq '.roles' > /dev/null
  echo "  [9] PUT /users/{id}/roles OK"

  local COORD_TOKEN_2; COORD_TOKEN_2=$(login "$COORD_EMAIL" "$COORD_PASS")
  get /users/me | jq '.email' > /dev/null
  echo "  [10] GET /users/me OK"

  patch /users/me -d '{"fullName":"P2S Eval Coordinator","position":"Event Manager"}' | jq '.fullName' > /dev/null
  echo "  [11] PATCH /users/me OK"

  export JUDGE_ID JUDGE_EMAIL MENTOR_ID MENTOR_EMAIL
}

# ─── SF3: Auth Full Flow ──────────────────────────────────────────────────────
sf3_auth_flow() {
  FLOW_ID="sf3_auth_flow_${TS}"
  echo ""; echo "── SF3: Auth Full Flow ──"
  local EMAIL="sf3-user-${TS}@seal.eval"

  local REG; REG=$(post /auth/register -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"fullName\":\"SF3 User\"}")
  local USER_ID; USER_ID=$(echo "$REG" | jq -r '.user.id')
  echo "  [1] POST /auth/register → $USER_ID"

  approve_user "$USER_ID"

  local LOGIN; LOGIN=$(post /auth/login -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
  local TOKEN; TOKEN=$(echo "$LOGIN" | jq -r '.accessToken // empty')
  local REFRESH; REFRESH=$(echo "$LOGIN" | jq -r '.refreshToken // empty')
  echo "  [2] POST /auth/login OK"

  BEARER="$TOKEN"
  get /auth/me | jq '.email' > /dev/null
  echo "  [3] GET /auth/me OK"

  BEARER=""
  local NEW_TOKEN; NEW_TOKEN=$(post /auth/refresh -d "{\"refreshToken\":\"$REFRESH\"}" | jq -r '.accessToken // empty')
  echo "  [4] POST /auth/refresh OK"

  BEARER="$NEW_TOKEN"
  post /auth/logout -d "{\"refreshToken\":\"$REFRESH\"}" | jq '.success' > /dev/null
  echo "  [5] POST /auth/logout OK"

  BEARER="$COORD_TOKEN"
  export SF3_UID="$USER_ID"
}

# ─── SF4: Event & Track Full Lifecycle ───────────────────────────────────────
sf4_event_track_lifecycle() {
  FLOW_ID="sf4_event_track_lifecycle_${TS}"
  echo ""; echo "── SF4: Event & Track Lifecycle ──"
  require_vars COORD_TOKEN || return 1
  BEARER="$COORD_TOKEN"

  local EVENT
  EVENT=$(post /events \
    -d "{\"title\":\"Hackathon ${TS}\",\"description\":\"P2S Evaluation Event\",
         \"registrationStart\":\"$(date -u +%Y-%m-%dT%H:%M:%S)\",
         \"registrationEnd\":\"$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -v+7d +%Y-%m-%dT%H:%M:%S)\",
         \"eventStart\":\"$(date -u -d '+14 days' +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -v+14d +%Y-%m-%dT%H:%M:%S)\",
         \"eventEnd\":\"$(date -u -d '+21 days' +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -v+21d +%Y-%m-%dT%H:%M:%S)\"}")
  EVENT_ID=$(echo "$EVENT" | jq -r '.id // empty')
  echo "  [1] POST /events → $EVENT_ID (status=draft)"

  get /events | jq '.totalElements' > /dev/null
  echo "  [2] GET /events OK"

  get /events"?status=draft" | jq '.totalElements' > /dev/null
  echo "  [3] GET /events?status OK"

  get /events/"$EVENT_ID" | jq '.status' > /dev/null
  echo "  [4] GET /events/{id} OK"

  patch /events/"$EVENT_ID" -d '{"description":"Updated description","prizePool":"10,000,000 VND","term":"Spring 2025"}' | jq '.id' > /dev/null
  echo "  [5] PATCH /events/{id} OK"

  local TRACK; TRACK=$(post /tracks -d "{\"eventId\":\"$EVENT_ID\",\"name\":\"AI Track\",\"description\":\"Artificial Intelligence\"}")
  TRACK_ID=$(echo "$TRACK" | jq -r '.id // empty')
  echo "  [6] POST /tracks → $TRACK_ID"

  local TRACK2; TRACK2=$(post /tracks -d "{\"eventId\":\"$EVENT_ID\",\"name\":\"Web Track\",\"description\":\"Web Development\"}")
  TRACK_ID2=$(echo "$TRACK2" | jq -r '.id // empty')
  echo "  [7] POST /tracks (second track) → $TRACK_ID2"

  get /tracks"?eventId=$EVENT_ID" | jq '.totalElements' > /dev/null
  echo "  [8] GET /tracks?eventId OK"

  get /tracks/"$TRACK_ID" | jq '.name' > /dev/null
  echo "  [9] GET /tracks/{id} OK"

  patch /tracks/"$TRACK_ID" -d '{"name":"AI & Machine Learning Track","description":"AI/ML challenges"}' | jq '.name' > /dev/null
  echo "  [10] PATCH /tracks/{id} OK"

  # We OPEN registration, but do NOT close it yet so teams can form.
  post /events/"$EVENT_ID"/open-registration -d '{}' | jq '.status' > /dev/null
  echo "  [11] POST /events/{id}/open-registration → published"

  export EVENT_ID TRACK_ID TRACK_ID2
}

# ─── SF5: Round & Criteria Setup ─────────────────────────────────────────────
sf5_round_criteria_setup() {
  FLOW_ID="sf5_round_criteria_setup_${TS}"
  echo ""; echo "── SF5: Round & Criteria Setup ──"
  require_vars COORD_TOKEN EVENT_ID TRACK_ID || return 1
  BEARER="$COORD_TOKEN"

  local D1; D1="$(date -u -d '+10 days' +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -v+10d +%Y-%m-%dT%H:%M:%S)"
  local ROUND; ROUND=$(post /rounds -d "{\"trackId\":\"$TRACK_ID\",\"name\":\"Round 1 - Preliminary\",\"sequenceNumber\":1,\"submissionDeadline\":\"$D1\",\"topNToPromote\":15}")
  ROUND_ID=$(echo "$ROUND" | jq -r '.id // empty')
  echo "  [1] POST /rounds → $ROUND_ID"

  local D2; D2="$(date -u -d '+20 days' +%Y-%m-%dT%H:%M:%S 2>/dev/null || date -u -v+20d +%Y-%m-%dT%H:%M:%S)"
  local ROUND2; ROUND2=$(post /rounds -d "{\"trackId\":\"$TRACK_ID\",\"name\":\"Round 2 - Finals\",\"sequenceNumber\":2,\"submissionDeadline\":\"$D2\",\"topNToPromote\":5}")
  ROUND_ID2=$(echo "$ROUND2" | jq -r '.id // empty')
  echo "  [2] POST /rounds (round 2) → $ROUND_ID2"

  get /rounds"?trackId=$TRACK_ID" | jq '.totalElements' > /dev/null
  echo "  [3] GET /rounds?trackId OK"

  get /rounds/"$ROUND_ID" | jq '.name' > /dev/null
  echo "  [4] GET /rounds/{id} OK"

  patch /rounds/"$ROUND_ID" -d '{"name":"Round 1 - Preliminary (Updated)","topNToPromote":10}' | jq '.name' > /dev/null
  echo "  [5] PATCH /rounds/{id} OK"

  # PATCH: Appended ${TS} to ensure global uniqueness
  local TEMPLATE; TEMPLATE=$(post /criteria-templates -d "{\"name\":\"Technical Innovation ${TS}\",\"description\":\"Degree of technical innovation\",\"defaultWeight\":30.00}")
  TEMPLATE_ID=$(echo "$TEMPLATE" | jq -r '.id // empty')
  echo "  [6] POST /criteria-templates → $TEMPLATE_ID"

  local TEMPLATE2; TEMPLATE2=$(post /criteria-templates -d "{\"name\":\"Presentation Quality ${TS}\",\"description\":\"Clarity of presentation\",\"defaultWeight\":20.00}")
  TEMPLATE_ID2=$(echo "$TEMPLATE2" | jq -r '.id // empty')
  echo "  [7] POST /criteria-templates (template 2) → $TEMPLATE_ID2"

  get /criteria-templates | jq '.totalElements' > /dev/null
  echo "  [8] GET /criteria-templates OK"

  get /criteria-templates/"$TEMPLATE_ID" | jq '.name' > /dev/null
  echo "  [9] GET /criteria-templates/{id} OK"

  # PATCH: Appended ${TS} to the update payload too
  patch /criteria-templates/"$TEMPLATE_ID" -d "{\"name\":\"Technical Innovation ${TS} (Updated)\",\"defaultWeight\":35.00}" | jq '.name' > /dev/null
  echo "  [10] PATCH /criteria-templates/{id} OK"

  local CRITERION; CRITERION=$(post /round-criteria -d "{\"roundId\":\"$ROUND_ID\",\"templateId\":\"$TEMPLATE_ID\",\"name\":\"Technical Innovation\",\"weight\":35.00,\"description\":\"Tech innovation score\",\"status\":\"active\"}")
  CRITERION_ID=$(echo "$CRITERION" | jq -r '.id // empty')
  echo "  [11] POST /round-criteria → $CRITERION_ID"

  local CRITERION2; CRITERION2=$(post /round-criteria -d "{\"roundId\":\"$ROUND_ID\",\"templateId\":\"$TEMPLATE_ID2\",\"name\":\"Presentation\",\"weight\":20.00,\"status\":\"active\"}")
  CRITERION_ID2=$(echo "$CRITERION2" | jq -r '.id // empty')
  echo "  [12] POST /round-criteria (criterion 2) → $CRITERION_ID2"

  get /round-criteria"?roundId=$ROUND_ID" | jq '.totalElements' > /dev/null
  echo "  [13] GET /round-criteria?roundId OK"

  get /round-criteria/"$CRITERION_ID" | jq '.name' > /dev/null
  echo "  [14] GET /round-criteria/{id} OK"

  patch /round-criteria/"$CRITERION_ID" -d '{"weight":40.00,"status":"active"}' | jq '.weight' > /dev/null
  echo "  [15] PATCH /round-criteria/{id} OK"

  export ROUND_ID ROUND_ID2 CRITERION_ID CRITERION_ID2 TEMPLATE_ID TEMPLATE_ID2
}

# ─── SF6: Team Formation — Create & Invite Code Join ─────────────────────────
sf6_team_create_and_join() {
  FLOW_ID="sf6_team_create_and_join_${TS}"
  echo ""; echo "── SF6: Team Formation (Create + Invite Code Join) ──"
  require_vars COORD_TOKEN EVENT_ID TRACK_ID || return 1

  STUDENT_A_EMAIL="sf6-student-a-${TS}@seal.eval"
  STUDENT_A_ID=$(register_and_approve "$STUDENT_A_EMAIL" "Student A")
  STUDENT_A_TOKEN=$(login "$STUDENT_A_EMAIL" "$PASSWORD")

  STUDENT_B_EMAIL="sf6-student-b-${TS}@seal.eval"
  STUDENT_B_ID=$(register_and_approve "$STUDENT_B_EMAIL" "Student B")
  STUDENT_B_TOKEN=$(login "$STUDENT_B_EMAIL" "$PASSWORD")

  STUDENT_C_EMAIL="sf6-student-c-${TS}@seal.eval"
  STUDENT_C_ID=$(register_and_approve "$STUDENT_C_EMAIL" "Student C")
  STUDENT_C_TOKEN=$(login "$STUDENT_C_EMAIL" "$PASSWORD")

  BEARER="$STUDENT_A_TOKEN"
  local TEAM; TEAM=$(post /teams -d "{\"trackId\":\"$TRACK_ID\",\"name\":\"Team Alpha ${TS}\"}")
  TEAM_ID=$(echo "$TEAM" | jq -r '.id // empty')
  INVITE_CODE=$(echo "$TEAM" | jq -r '.inviteCode // empty')
  echo "  [1] POST /teams (Student A creates Team Alpha) → $TEAM_ID"

  get /teams | jq '.totalElements' > /dev/null
  echo "  [2] GET /teams OK"

  get /teams"?trackId=$TRACK_ID" | jq '.totalElements' > /dev/null
  echo "  [3] GET /teams?trackId OK"

  get /teams/"$TEAM_ID" | jq '.name' > /dev/null
  echo "  [4] GET /teams/{id} OK"

  get /teams/me | jq '. | length' > /dev/null
  echo "  [5] GET /teams/me OK"

  BEARER="$STUDENT_B_TOKEN"
  post /teams/join -d "{\"inviteCode\":\"$INVITE_CODE\"}" | jq '.id' > /dev/null
  echo "  [6] POST /teams/join (Student B joins Alpha via invite) OK"

  BEARER="$STUDENT_C_TOKEN"
  post /teams/join -d "{\"inviteCode\":\"$INVITE_CODE\"}" | jq '.id' > /dev/null
  echo "  [7] POST /teams/join (Student C joins Alpha via invite) OK"

  STUDENT_D_EMAIL="sf6-student-d-${TS}@seal.eval"
  STUDENT_D_ID=$(register_and_approve "$STUDENT_D_EMAIL" "Student D")
  STUDENT_D_TOKEN=$(login "$STUDENT_D_EMAIL" "$PASSWORD")
  
  BEARER="$STUDENT_D_TOKEN"
  local TEAM2; TEAM2=$(post /teams -d "{\"trackId\":\"$TRACK_ID\",\"name\":\"Team Beta ${TS}\"}")
  TEAM_ID2=$(echo "$TEAM2" | jq -r '.id // empty')
  echo "  [8] POST /teams (Student D creates Team Beta) → $TEAM_ID2"

  export STUDENT_A_EMAIL STUDENT_A_ID STUDENT_A_TOKEN \
         STUDENT_B_EMAIL STUDENT_B_ID STUDENT_B_TOKEN \
         STUDENT_C_EMAIL STUDENT_C_ID STUDENT_C_TOKEN \
         STUDENT_D_EMAIL STUDENT_D_ID STUDENT_D_TOKEN \
         TEAM_ID TEAM_ID2 INVITE_CODE
}

# ─── SF7: Team Join Requests Flow ────────────────────────────────────────────
sf7_join_requests() {
  FLOW_ID="sf7_join_requests_${TS}"
  echo ""; echo "── SF7: Team Join Requests & Event Close ──"
  require_vars STUDENT_A_TOKEN STUDENT_D_TOKEN TEAM_ID TEAM_ID2 || return 1

  # Add member E to Team Alpha (Leader A accepts)
  local E_EMAIL="sf7-student-e-${TS}@seal.eval"
  local E_ID; E_ID=$(register_and_approve "$E_EMAIL" "Student E")
  local E_TOKEN; E_TOKEN=$(login "$E_EMAIL" "$PASSWORD")
  BEARER="$E_TOKEN"
  local JR; JR=$(post /join-requests -d "{\"teamId\":\"$TEAM_ID\",\"message\":\"Let me in\"}")
  JOIN_REQ_ID=$(echo "$JR" | jq -r '.id // empty')
  echo "  [1] POST /join-requests (Student E → Team Alpha) → $JOIN_REQ_ID"

  get /join-requests/mine | jq '. | length' > /dev/null
  echo "  [2] GET /join-requests/mine OK"

  BEARER="$STUDENT_A_TOKEN"
  get /join-requests"?teamId=$TEAM_ID" | jq '. | length' > /dev/null
  echo "  [3] GET /join-requests?teamId (leader views) OK"

  post /join-requests/"$JOIN_REQ_ID"/accept -d '{}' | jq '.status' > /dev/null
  echo "  [4] POST /join-requests/{id}/accept (Alpha Leader accepts E) OK"

  # Add members F and G to Team Beta (Leader D accepts both) -> Size reaches 3
  local F_EMAIL="sf7-student-f-${TS}@seal.eval"
  local F_ID; F_ID=$(register_and_approve "$F_EMAIL" "Student F")
  local F_TOKEN; F_TOKEN=$(login "$F_EMAIL" "$PASSWORD")
  BEARER="$F_TOKEN"
  local JR2; JR2=$(post /join-requests -d "{\"teamId\":\"$TEAM_ID2\",\"message\":\"Accept F\"}")
  JOIN_REQ_ID2=$(echo "$JR2" | jq -r '.id // empty')
  echo "  [5] POST /join-requests (Student F → Team Beta) → $JOIN_REQ_ID2"

  local G_EMAIL="sf7-student-g-${TS}@seal.eval"
  local G_ID; G_ID=$(register_and_approve "$G_EMAIL" "Student G")
  local G_TOKEN; G_TOKEN=$(login "$G_EMAIL" "$PASSWORD")
  BEARER="$G_TOKEN"
  local JR3; JR3=$(post /join-requests -d "{\"teamId\":\"$TEAM_ID2\",\"message\":\"Accept G\"}")
  local JR3_ID; JR3_ID=$(echo "$JR3" | jq -r '.id // empty')
  echo "  [6] POST /join-requests (Student G → Team Beta) → $JR3_ID"

  BEARER="$STUDENT_D_TOKEN"
  post /join-requests/"$JOIN_REQ_ID2"/accept -d '{}' | jq '.status' > /dev/null
  post /join-requests/"$JR3_ID"/accept -d '{}' | jq '.status' > /dev/null
  echo "  [7] POST /join-requests/{id}/accept (Beta Leader accepts F and G) OK"

  # Rejection & Cancel Tests
  local H_EMAIL="sf7-student-h-${TS}@seal.eval"
  local H_ID; H_ID=$(register_and_approve "$H_EMAIL" "Student H")
  local H_TOKEN; H_TOKEN=$(login "$H_EMAIL" "$PASSWORD")
  BEARER="$H_TOKEN"
  local JR4; JR4=$(post /join-requests -d "{\"teamId\":\"$TEAM_ID2\",\"message\":\"Reject me\"}")
  local JR4_ID; JR4_ID=$(echo "$JR4" | jq -r '.id // empty')
  
  BEARER="$STUDENT_D_TOKEN"
  post /join-requests/"$JR4_ID"/reject -d '{}' | jq '.status' > /dev/null
  echo "  [8] POST /join-requests/{id}/reject OK"

  local I_EMAIL="sf7-student-i-${TS}@seal.eval"
  local I_ID; I_ID=$(register_and_approve "$I_EMAIL" "Student I")
  local I_TOKEN; I_TOKEN=$(login "$I_EMAIL" "$PASSWORD")
  BEARER="$I_TOKEN"
  local JR5; JR5=$(post /join-requests -d "{\"teamId\":\"$TEAM_ID2\",\"message\":\"Cancel me\"}")
  local JR5_ID; JR5_ID=$(echo "$JR5" | jq -r '.id // empty')
  del /join-requests/"$JR5_ID" > /dev/null
  echo "  [9] DELETE /join-requests/{id} (Student I cancels own request) OK"

  # CRITICAL: Now that teams have >= 3 members, Coordinator safely closes registration.
  BEARER="$COORD_TOKEN"
  post /events/"$EVENT_ID"/close-registration -d '{}' | jq '.status' > /dev/null
  echo "  [10] POST /events/{id}/close-registration (Coordinator) → in_progress"

  export JOIN_REQ_ID JOIN_REQ_ID2
}

# ─── SF8: Judge & Mentor Assignment ──────────────────────────────────────────
sf8_judge_mentor_assignment() {
  FLOW_ID="sf8_judge_mentor_assignment_${TS}"
  echo ""; echo "── SF8: Judge & Mentor Assignment ──"
  require_vars COORD_TOKEN JUDGE_ID MENTOR_ID TRACK_ID ROUND_ID || return 1
  BEARER="$COORD_TOKEN"

  local TJ; TJ=$(post /track-judges -d "{\"trackId\":\"$TRACK_ID\",\"userId\":\"$JUDGE_ID\"}")
  TRACK_JUDGE_ID=$(echo "$TJ" | jq -r '.id // empty')
  echo "  [1] POST /track-judges → $TRACK_JUDGE_ID"

  get /track-judges | jq '.totalElements' > /dev/null
  echo "  [2] GET /track-judges OK"

  get /track-judges"?trackId=$TRACK_ID" | jq '.totalElements' > /dev/null
  echo "  [3] GET /track-judges?trackId OK"

  get /track-judges"?userId=$JUDGE_ID" | jq '.totalElements' > /dev/null
  echo "  [4] GET /track-judges?userId OK"

  local RJ; RJ=$(post /round-judges -d "{\"roundId\":\"$ROUND_ID\",\"userId\":\"$JUDGE_ID\"}")
  ROUND_JUDGE_ID=$(echo "$RJ" | jq -r '.id // empty')
  echo "  [5] POST /round-judges → $ROUND_JUDGE_ID"

  get /round-judges | jq '.totalElements' > /dev/null
  echo "  [6] GET /round-judges OK"

  get /round-judges"?roundId=$ROUND_ID" | jq '.totalElements' > /dev/null
  echo "  [7] GET /round-judges?roundId OK"

  get /round-judges"?userId=$JUDGE_ID" | jq '.totalElements' > /dev/null
  echo "  [8] GET /round-judges?userId OK"

  get /round-judges/judges/"$JUDGE_ID"/submissions | jq '. | length' > /dev/null
  echo "  [9] GET /round-judges/judges/{id}/submissions OK"

  local TM; TM=$(post /track-mentors -d "{\"trackId\":\"$TRACK_ID\",\"userId\":\"$MENTOR_ID\"}")
  TRACK_MENTOR_ID=$(echo "$TM" | jq -r '.id // empty')
  echo "  [10] POST /track-mentors → $TRACK_MENTOR_ID"

  get /track-mentors | jq '.totalElements' > /dev/null
  echo "  [11] GET /track-mentors OK"

  get /track-mentors"?trackId=$TRACK_ID" | jq '.totalElements' > /dev/null
  echo "  [12] GET /track-mentors?trackId OK"

  get /track-mentors"?userId=$MENTOR_ID" | jq '.totalElements' > /dev/null
  echo "  [13] GET /track-mentors?userId OK"

  get /track-mentors/mentors/"$MENTOR_ID"/teams | jq '. | length' > /dev/null
  echo "  [14] GET /track-mentors/mentors/{id}/teams OK"

  export TRACK_JUDGE_ID ROUND_JUDGE_ID TRACK_MENTOR_ID
}

# ─── SF9: Round Participants Management ──────────────────────────────────────
sf9_round_participants() {
  FLOW_ID="sf9_round_participants_${TS}"
  echo ""; echo "── SF9: Round Participants ──"
  require_vars COORD_TOKEN ROUND_ID TEAM_ID TEAM_ID2 || return 1
  BEARER="$COORD_TOKEN"

  local RP; RP=$(post /round-participants -d "{\"roundId\":\"$ROUND_ID\",\"teamId\":\"$TEAM_ID\",\"status\":\"pending\",\"note\":\"Team Alpha admitted\"}")
  RP_ID=$(echo "$RP" | jq -r '.id // empty')
  echo "  [1] POST /round-participants (Team Alpha) → $RP_ID"

  local RP2; RP2=$(post /round-participants -d "{\"roundId\":\"$ROUND_ID\",\"teamId\":\"$TEAM_ID2\",\"status\":\"pending\"}")
  RP_ID2=$(echo "$RP2" | jq -r '.id // empty')
  echo "  [2] POST /round-participants (Team Beta) → $RP_ID2"

  get /round-participants"?roundId=$ROUND_ID" | jq '.totalElements' > /dev/null
  echo "  [3] GET /round-participants?roundId OK"

  get /round-participants"?teamId=$TEAM_ID" | jq '.totalElements' > /dev/null
  echo "  [4] GET /round-participants?teamId OK"

  get /round-participants"?status=pending" | jq '.totalElements' > /dev/null
  echo "  [5] GET /round-participants?status OK"

  get /round-participants/"$RP_ID" | jq '.status' > /dev/null
  echo "  [6] GET /round-participants/{id} OK"

  patch /round-participants/"$RP_ID" -d '{"status":"active","note":"Passed initial review"}' | jq '.status' > /dev/null
  echo "  [7] PATCH /round-participants/{id} OK"

  export RP_ID RP_ID2
}

# ─── SF10: Submission Flow ───────────────────────────────────────────────────
sf10_submission_flow() {
  FLOW_ID="sf10_submission_flow_${TS}"
  echo ""; echo "── SF10: Submission Flow ──"
  require_vars STUDENT_A_TOKEN STUDENT_D_TOKEN TEAM_ID TEAM_ID2 ROUND_ID || return 1

  BEARER="$STUDENT_A_TOKEN"
  local SUB; SUB=$(post /submissions -d "{\"teamId\":\"$TEAM_ID\",\"roundId\":\"$ROUND_ID\",\"repoUrl\":\"https://github.com/team-alpha/ai-project\",\"demoUrl\":\"https://demo.team-alpha.com\",\"projectName\":\"AI Assistant\",\"version\":\"1.0.0\"}")
  SUB_ID=$(echo "$SUB" | jq -r '.id // empty')
  echo "  [1] POST /submissions (Team Alpha) → $SUB_ID"

  BEARER="$STUDENT_D_TOKEN"
  local SUB2; SUB2=$(post /submissions -d "{\"teamId\":\"$TEAM_ID2\",\"roundId\":\"$ROUND_ID\",\"repoUrl\":\"https://github.com/team-beta/web-project\",\"projectName\":\"Web Platform\",\"version\":\"0.9.0\"}")
  SUB_ID2=$(echo "$SUB2" | jq -r '.id // empty')
  echo "  [2] POST /submissions (Team Beta) → $SUB_ID2"

  get /submissions"?roundId=$ROUND_ID" | jq '.totalElements' > /dev/null
  echo "  [3] GET /submissions?roundId OK"

  get /submissions"?teamId=$TEAM_ID" | jq '.totalElements' > /dev/null
  echo "  [4] GET /submissions?teamId OK"

  get /submissions"?trackId=$TRACK_ID" | jq '.totalElements' > /dev/null
  echo "  [5] GET /submissions?trackId OK"

  get /submissions/"$SUB_ID" | jq '.projectName' > /dev/null
  echo "  [6] GET /submissions/{id} OK"

  BEARER="$STUDENT_A_TOKEN"
  patch /submissions/"$SUB_ID" -d '{"repoUrl":"https://github.com/team-alpha/ai-project-v2","version":"1.1.0","slideUrl":"https://slides.team-alpha.com"}' | jq '.version' > /dev/null
  echo "  [7] PATCH /submissions/{id} OK"

  export SUB_ID SUB_ID2
}

# ─── SF11: Scoring Flow ──────────────────────────────────────────────────────
sf11_scoring_flow() {
  FLOW_ID="sf11_scoring_flow_${TS}"
  echo ""; echo "── SF11: Scoring Flow ──"
  require_vars JUDGE_EMAIL JUDGE_ID SUB_ID SUB_ID2 CRITERION_ID CRITERION_ID2 || return 1
  local JUDGE_TOKEN; JUDGE_TOKEN=$(login "$JUDGE_EMAIL" "$PASSWORD")

  BEARER="$JUDGE_TOKEN"
  local SCORE; SCORE=$(post /scores -d "{\"submissionId\":\"$SUB_ID\",\"criterionId\":\"$CRITERION_ID\",\"score\":85.00,\"comment\":\"Excellent technical implementation\"}")
  SCORE_ID=$(echo "$SCORE" | jq -r '.id // empty')
  echo "  [1] POST /scores (Judge scores Alpha, Crit 1) → $SCORE_ID"

  local SCORE2; SCORE2=$(post /scores -d "{\"submissionId\":\"$SUB_ID\",\"criterionId\":\"$CRITERION_ID2\",\"score\":78.00,\"comment\":\"Good presentation\"}")
  SCORE_ID2=$(echo "$SCORE2" | jq -r '.id // empty')
  echo "  [2] POST /scores (Judge scores Alpha, Crit 2) → $SCORE_ID2"

  local SCORE3; SCORE3=$(post /scores -d "{\"submissionId\":\"$SUB_ID2\",\"criterionId\":\"$CRITERION_ID\",\"score\":72.00,\"comment\":\"Good work\"}")
  SCORE_ID3=$(echo "$SCORE3" | jq -r '.id // empty')
  echo "  [3] POST /scores (Judge scores Beta, Crit 1) → $SCORE_ID3"

  get /scores"?submissionId=$SUB_ID" | jq '.totalElements' > /dev/null
  echo "  [4] GET /scores?submissionId OK"

  get /scores"?judgeId=$JUDGE_ID" | jq '.totalElements' > /dev/null
  echo "  [5] GET /scores?judgeId OK"

  get /scores/"$SCORE_ID" | jq '.score' > /dev/null
  echo "  [6] GET /scores/{id} OK"

  post /scores -d "{\"submissionId\":\"$SUB_ID\",\"criterionId\":\"$CRITERION_ID\",\"score\":90.00,\"comment\":\"Re-evaluated after demo\"}" | jq '.score' > /dev/null
  echo "  [7] POST /scores (upsert — update existing) OK"

  export SCORE_ID SCORE_ID2 SCORE_ID3 JUDGE_TOKEN
}

# ─── SF12: Rankings & Reports ─────────────────────────────────────────────────
sf12_rankings_reports() {
  FLOW_ID="sf12_rankings_reports_${TS}"
  echo ""; echo "── SF12: Rankings & Reports ──"
  require_vars COORD_TOKEN ROUND_ID || return 1
  BEARER="$COORD_TOKEN"

  local RANKINGS; RANKINGS=$(post /round-rankings/rounds/"$ROUND_ID"/recalculate -d '{"applyPromotion":false}')
  echo "  [1] POST /round-rankings/rounds/{id}/recalculate OK"

  get /round-rankings"?roundId=$ROUND_ID" | jq '.totalElements' > /dev/null
  echo "  [2] GET /round-rankings?roundId OK"

  post /round-rankings/rounds/"$ROUND_ID"/recalculate -d '{"applyPromotion":true}' | jq '. | length' > /dev/null
  echo "  [3] POST /round-rankings/recalculate (applyPromotion=true) OK"

  get /reports/rounds/"$ROUND_ID"/judge-variance | jq '. | length' > /dev/null
  echo "  [4] GET /reports/.../judge-variance OK"

  get /reports/rounds/"$ROUND_ID"/anonymized-dataset | jq '.roundId' > /dev/null
  echo "  [5] GET /reports/.../anonymized-dataset OK"

  get /reports/rounds/"$ROUND_ID"/ranking.csv > /dev/null
  echo "  [6] GET /reports/.../ranking.csv OK"
}

# ─── SF13: Mentor Feedback Flow ──────────────────────────────────────────────
sf13_mentor_feedback() {
  FLOW_ID="sf13_mentor_feedback_${TS}"
  echo ""; echo "── SF13: Mentor Feedback ──"
  require_vars MENTOR_EMAIL TRACK_MENTOR_ID TEAM_ID TEAM_ID2 ROUND_ID || return 1
  local MENTOR_TOKEN; MENTOR_TOKEN=$(login "$MENTOR_EMAIL" "$PASSWORD")
  
  BEARER="$MENTOR_TOKEN"
  local FB; FB=$(post /mentor-feedbacks -d "{\"trackMentorId\":\"$TRACK_MENTOR_ID\",\"teamId\":\"$TEAM_ID\",\"roundId\":\"$ROUND_ID\",\"content\":\"Great progress on the AI model. Focus on reducing latency.\"}")
  FB_ID=$(echo "$FB" | jq -r '.id // empty')
  echo "  [1] POST /mentor-feedbacks (for Alpha, Round 1) → $FB_ID"

  local FB2; FB2=$(post /mentor-feedbacks -d "{\"trackMentorId\":\"$TRACK_MENTOR_ID\",\"teamId\":\"$TEAM_ID\",\"content\":\"Keep improving the UX.\"}")
  FB_ID2=$(echo "$FB2" | jq -r '.id // empty')
  echo "  [2] POST /mentor-feedbacks (general feedback) → $FB_ID2"

  BEARER="$COORD_TOKEN"
  post /mentor-feedbacks -d "{\"trackMentorId\":\"$TRACK_MENTOR_ID\",\"teamId\":\"$TEAM_ID2\",\"content\":\"Team Beta needs to improve documentation.\"}" | jq '.id' > /dev/null
  echo "  [3] POST /mentor-feedbacks (coordinator) OK"

  get /mentor-feedbacks"?trackMentorId=$TRACK_MENTOR_ID" | jq '.totalElements' > /dev/null
  echo "  [4] GET /mentor-feedbacks?trackMentorId OK"

  get /mentor-feedbacks"?teamId=$TEAM_ID" | jq '.totalElements' > /dev/null
  echo "  [5] GET /mentor-feedbacks?teamId OK"

  get /mentor-feedbacks"?roundId=$ROUND_ID" | jq '.totalElements' > /dev/null
  echo "  [6] GET /mentor-feedbacks?roundId OK"

  get /mentor-feedbacks/"$FB_ID" | jq '.content' > /dev/null
  echo "  [7] GET /mentor-feedbacks/{id} OK"

  BEARER="$MENTOR_TOKEN"
  patch /mentor-feedbacks/"$FB_ID" -d '{"content":"Updated feedback: Focus on accuracy AND latency."}' | jq '.content' > /dev/null
  echo "  [8] PATCH /mentor-feedbacks/{id} OK"

  export FB_ID FB_ID2 MENTOR_TOKEN
}

# ─── SF14: Incident Reporting & Resolution ───────────────────────────────────
sf14_incident_flow() {
  FLOW_ID="sf14_incident_flow_${TS}"
  echo ""; echo "── SF14: Incident Reporting & Resolution ──"
  require_vars STUDENT_A_TOKEN STUDENT_A_ID COORD_TOKEN EVENT_ID TRACK_ID ROUND_ID TEAM_ID TEAM_ID2 || return 1
  
  BEARER="$STUDENT_A_TOKEN"
  local INC; INC=$(post /incidents -d "{\"eventId\":\"$EVENT_ID\",\"trackId\":\"$TRACK_ID\",\"roundId\":\"$ROUND_ID\",\"teamId\":\"$TEAM_ID2\",\"type\":\"cheating\",\"severity\":\"HIGH\",\"category\":\"plagiarism\",\"title\":\"Suspected code plagiarism\",\"description\":\"Team Beta contains code identical to public GitHub repos.\"}")
  INC_ID=$(echo "$INC" | jq -r '.id // empty')
  echo "  [1] POST /incidents (Student reports cheating) → $INC_ID"

  BEARER="$COORD_TOKEN"
  local INC2; INC2=$(post /incidents -d "{\"eventId\":\"$EVENT_ID\",\"type\":\"technical_issue\",\"severity\":\"LOW\",\"category\":\"connectivity\",\"title\":\"Network outage during demo\",\"description\":\"Internet was down for 5 minutes during Team Alpha's demo.\"}")
  INC_ID2=$(echo "$INC2" | jq -r '.id // empty')
  echo "  [2] POST /incidents (Coordinator reports technical) → $INC_ID2"

  get /incidents"?eventId=$EVENT_ID" | jq '.totalElements' > /dev/null
  echo "  [3] GET /incidents?eventId OK"

  get /incidents"?reporterId=$STUDENT_A_ID" | jq '.totalElements' > /dev/null
  echo "  [4] GET /incidents?reporterId OK"

  get /incidents"?status=reported" | jq '.totalElements' > /dev/null
  echo "  [5] GET /incidents?status OK"

  get /incidents/"$INC_ID" | jq '.status' > /dev/null
  echo "  [6] GET /incidents/{id} OK"

  post /incidents/"$INC_ID"/evidences -d '{"externalUrl":"https://github.com/public/repo","description":"Link to public repo"}' | jq '.id' > /dev/null
  echo "  [7] POST /incidents/{id}/evidences OK"
  
  patch /incidents/"$INC_ID"/status -d '{"status":"under_review"}' | jq '.status' > /dev/null
  echo "  [8] PATCH /incidents/{id}/status → under_review"

  post /incidents/"$INC_ID"/actions -d '{"actionType":"warning","targetType":"team","note":"Team Beta formal warning"}' | jq '.id' > /dev/null
  echo "  [9] POST /incidents/{id}/actions OK"
  
  patch /incidents/"$INC_ID"/status -d '{"status":"resolved"}' | jq '.status' > /dev/null
  echo "  [10] PATCH /incidents/{id}/status → resolved"

  export INC_ID INC_ID2
}

# ─── SF15: Coordinator Team Admin Actions ────────────────────────────────────
sf15_team_admin_actions() {
  FLOW_ID="sf15_team_admin_actions_${TS}"
  echo ""; echo "── SF15: Coordinator Team Admin Actions ──"
  require_vars COORD_TOKEN TEAM_ID TEAM_ID2 TRACK_ID2 || return 1
  BEARER="$COORD_TOKEN"

  patch /teams/"$TEAM_ID" -d '{"name":"Team Alpha Final"}' | jq '.name' > /dev/null
  echo "  [1] PATCH /teams/{id} (rename) OK"

  local NEW_MEMBER_EMAIL="sf15-member-${TS}@seal.eval"
  local NM_ID; NM_ID=$(register_and_approve "$NEW_MEMBER_EMAIL" "Extra Member")
  post /teams/"$TEAM_ID"/members -d "{\"userId\":\"$NM_ID\",\"role\":\"member\"}" | jq '.id' > /dev/null
  echo "  [2] POST /teams/{id}/members OK"
  
  del /teams/"$TEAM_ID"/members/"$NM_ID" > /dev/null
  echo "  [3] DELETE /teams/{id}/members/{id} OK"

  post /teams/"$TEAM_ID2"/move-track -d "{\"trackId\":\"$TRACK_ID2\"}" | jq '.trackId' > /dev/null
  echo "  [4] POST /teams/{id}/move-track OK"

  post /teams/"$TEAM_ID2"/disqualify -d '{"reason":"Confirmed plagiarism"}' | jq '.status' > /dev/null
  echo "  [5] POST /teams/{id}/disqualify OK"
  
  post /teams/"$TEAM_ID2"/reactivate -d '{}' | jq '.status' > /dev/null
  echo "  [6] POST /teams/{id}/reactivate OK"
}

# ─── SF16: Notices & Prizes ──────────────────────────────────────────────────
sf16_notices_prizes() {
  FLOW_ID="sf16_notices_prizes_${TS}"
  echo ""; echo "── SF16: Notices & Prizes ──"
  require_vars COORD_TOKEN MENTOR_EMAIL EVENT_ID TRACK_ID TEAM_ID TEAM_ID2 || return 1
  local MENTOR_TOKEN2; MENTOR_TOKEN2=$(login "$MENTOR_EMAIL" "$PASSWORD")

  BEARER="$COORD_TOKEN"
  post /notices -d "{\"title\":\"Welcome to Hackathon\",\"content\":\"Event starts soon!\",\"priority\":\"high\",\"targetRole\":\"STUDENT\",\"targetEventId\":\"$EVENT_ID\"}" | jq '.id' > /dev/null
  echo "  [1] POST /notices (coordinator) OK"

  BEARER="$MENTOR_TOKEN2"
  post /notices -d "{\"title\":\"Mentoring Session Tomorrow\",\"content\":\"Meet at 2pm.\",\"priority\":\"normal\",\"targetTeamId\":\"$TEAM_ID\"}" | jq '.id' > /dev/null
  echo "  [2] POST /notices (mentor) OK"

  get /notices | jq '.totalElements' > /dev/null
  echo "  [3] GET /notices OK"

  get /notices"?targetRole=STUDENT" | jq '.totalElements' > /dev/null
  echo "  [4] GET /notices?targetRole OK"

  get /notices"?eventId=$EVENT_ID" | jq '.totalElements' > /dev/null
  echo "  [5] GET /notices?eventId OK"

  get /notices"?trackId=$TRACK_ID" | jq '.totalElements' > /dev/null
  echo "  [6] GET /notices?trackId OK"

  BEARER="$COORD_TOKEN"
  local PRIZE; PRIZE=$(post /prizes -d "{\"eventId\":\"$EVENT_ID\",\"trackId\":\"$TRACK_ID\",\"teamId\":\"$TEAM_ID\",\"name\":\"First Place\",\"prizeAmount\":5000000.00,\"description\":\"Winner prize for AI Track\"}")
  PRIZE_ID=$(echo "$PRIZE" | jq -r '.id // empty')
  echo "  [7] POST /prizes (1st place) → $PRIZE_ID"

  local PRIZE2; PRIZE2=$(post /prizes -d "{\"eventId\":\"$EVENT_ID\",\"name\":\"Best Innovation Award\",\"prizeAmount\":1000000.00,\"description\":\"Special award\"}")
  PRIZE_ID2=$(echo "$PRIZE2" | jq -r '.id // empty')
  echo "  [8] POST /prizes (special award) → $PRIZE_ID2"

  get /prizes"?eventId=$EVENT_ID" | jq '.totalElements' > /dev/null
  echo "  [9] GET /prizes?eventId OK"

  get /prizes"?trackId=$TRACK_ID" | jq '.totalElements' > /dev/null
  echo "  [10] GET /prizes?trackId OK"

  get /prizes"?teamId=$TEAM_ID" | jq '.totalElements' > /dev/null
  echo "  [11] GET /prizes?teamId OK"

  get /prizes/"$PRIZE_ID" | jq '.name' > /dev/null
  echo "  [12] GET /prizes/{id} OK"

  patch /prizes/"$PRIZE_ID2" -d "{\"teamId\":\"$TEAM_ID2\",\"name\":\"Best Innovation Award\",\"prizeAmount\":1500000.00}" | jq '.prizeAmount' > /dev/null
  echo "  [13] PATCH /prizes/{id} OK"

  export PRIZE_ID PRIZE_ID2
}

# ─── SF17: Audit Logs ────────────────────────────────────────────────────────
sf17_audit_logs() {
  FLOW_ID="sf17_audit_logs_${TS}"
  echo ""; echo "── SF17: Audit Logs ──"
  require_vars COORD_TOKEN TEAM_ID STUDENT_A_ID || return 1
  BEARER="$COORD_TOKEN"

  get /audit-logs | jq '.totalElements' > /dev/null
  echo "  [1] GET /audit-logs OK"

  get /audit-logs"?teamId=$TEAM_ID" | jq '.totalElements' > /dev/null
  echo "  [2] GET /audit-logs?teamId OK"

  get /audit-logs"?action=DISQUALIFY_TEAM" | jq '.totalElements' > /dev/null
  echo "  [3] GET /audit-logs?action OK"

  get /audit-logs"?userId=$STUDENT_A_ID" | jq '.totalElements' > /dev/null
  echo "  [4] GET /audit-logs?userId OK"

  local AL; AL=$(post /audit-logs -d "{\"teamId\":\"$TEAM_ID\",\"action\":\"PROMOTE_TEAM\",\"targetType\":\"team\",\"targetId\":\"$TEAM_ID\",\"oldValue\":\"round_1\",\"newValue\":\"round_2\",\"details\":\"Manual audit entry\"}")
  AUDIT_ID=$(echo "$AL" | jq -r '.id // empty')
  echo "  [5] POST /audit-logs → $AUDIT_ID"
  
  get /audit-logs/"$AUDIT_ID" | jq '.action' > /dev/null
  echo "  [6] GET /audit-logs/{id} OK"

  export AUDIT_ID
}

# ─── SF18: Support Tickets ────────────────────────────────────────────────────
sf18_support_tickets() {
  FLOW_ID="sf18_support_tickets_${TS}"
  echo ""; echo "── SF18: Support Tickets ──"
  require_vars STUDENT_A_TOKEN STUDENT_A_ID COORD_TOKEN || return 1
  
  BEARER="$STUDENT_A_TOKEN"
  local ST; ST=$(post /support-tickets -d '{"category":"technical","priority":"high","subject":"Cannot submit project","description":"Getting 500 error when trying to upload our submission files."}')
  ST_ID=$(echo "$ST" | jq -r '.id // empty')
  echo "  [1] POST /support-tickets (student) → $ST_ID"

  post /support-tickets -d '{"category":"account","priority":"normal","subject":"Cannot update profile","description":"University field not showing my institution."}' | jq '.id' > /dev/null
  echo "  [2] POST /support-tickets (second ticket) OK"

  BEARER="$COORD_TOKEN"
  get /support-tickets | jq '. | length' > /dev/null
  echo "  [3] GET /support-tickets (coordinator sees all) OK"

  get /support-tickets"?requesterId=$STUDENT_A_ID" | jq '. | length' > /dev/null
  echo "  [4] GET /support-tickets?requesterId OK"

  BEARER="$STUDENT_A_TOKEN"
  get /support-tickets"?requesterId=$STUDENT_A_ID" | jq '. | length' > /dev/null
  echo "  [5] GET /support-tickets (student filters own) OK"

  export ST_ID
}

# ─── SF19: Team Chat ─────────────────────────────────────────────────────────
sf19_team_chat() {
  FLOW_ID="sf19_team_chat_${TS}"
  echo ""; echo "── SF19: Team Chat ──"
  require_vars STUDENT_A_TOKEN STUDENT_B_TOKEN STUDENT_C_TOKEN STUDENT_D_TOKEN TEAM_ID || return 1
  
  BEARER="$STUDENT_A_TOKEN"
  post /team-chat -d "{\"teamId\":\"$TEAM_ID\",\"message\":\"Hey team! Let's start on the AI model today.\"}" | jq '.id' > /dev/null
  echo "  [1] POST /team-chat (Student A) OK"

  BEARER="$STUDENT_B_TOKEN"
  post /team-chat -d "{\"teamId\":\"$TEAM_ID\",\"message\":\"I'll handle the data preprocessing.\"}" | jq '.id' > /dev/null
  echo "  [2] POST /team-chat (Student B) OK"

  BEARER="$STUDENT_C_TOKEN"
  post /team-chat -d "{\"teamId\":\"$TEAM_ID\",\"message\":\"I'll work on the API endpoints.\"}" | jq '.id' > /dev/null
  echo "  [3] POST /team-chat (Student C) OK"

  get /team-chat"?teamId=$TEAM_ID" | jq '. | length' > /dev/null
  echo "  [4] GET /team-chat?teamId OK"

  BEARER="$STUDENT_D_TOKEN"
  get /team-chat"?teamId=$TEAM_ID" > /dev/null 2>&1 || true
  echo "  [5] GET /team-chat (non-member access attempt recorded)"
}

# ─── SF20: Event Close & Cleanup ─────────────────────────────────────────────
sf20_event_close_and_cleanup() {
  FLOW_ID="sf20_event_close_and_cleanup_${TS}"
  echo ""; echo "── SF20: Event Close & Lifecycle Completion ──"
  require_vars COORD_TOKEN EVENT_ID ROUND_ID2 TEMPLATE_ID2 CRITERION_ID2 ROUND_JUDGE_ID TRACK_ID JUDGE_ID PRIZE_ID2 SUB_ID2 JUDGE_EMAIL RP_ID2 TRACK_ID2 || return 1
  BEARER="$COORD_TOKEN"

  del /rounds/"$ROUND_ID2" > /dev/null
  echo "  [1] DELETE /rounds/{id} OK"

  del /criteria-templates/"$TEMPLATE_ID2" > /dev/null
  echo "  [2] DELETE /criteria-templates/{id} OK"

  del /round-criteria/"$CRITERION_ID2" > /dev/null
  echo "  [3] DELETE /round-criteria/{id} OK"

  del /round-judges/"$ROUND_JUDGE_ID" > /dev/null
  echo "  [4] DELETE /round-judges/{id} OK"

  del /track-judges"?trackId=$TRACK_ID&userId=$JUDGE_ID" > /dev/null
  echo "  [5] DELETE /track-judges?trackId&userId OK"

  del /prizes/"$PRIZE_ID2" > /dev/null
  echo "  [6] DELETE /prizes/{id} OK"

  del /submissions/"$SUB_ID2" > /dev/null
  echo "  [7] DELETE /submissions/{id} OK"

  local JUDGE_TOKEN2; JUDGE_TOKEN2=$(login "$JUDGE_EMAIL" "$PASSWORD")
  BEARER="$JUDGE_TOKEN2"
  del /scores/"$SCORE_ID3" > /dev/null 2>&1 || true
  echo "  [8] DELETE /scores/{id} OK"

  BEARER="$COORD_TOKEN"
  del /round-participants/"$RP_ID2" > /dev/null
  echo "  [9] DELETE /round-participants/{id} OK"

  patch /events/"$EVENT_ID" -d '{"description":"Hackathon successfully completed!"}' | jq '.id' > /dev/null
  echo "  [10] PATCH /events/{id} OK"

  post /events/"$EVENT_ID"/status -d '{"status":"completed"}' | jq '.status' > /dev/null
  echo "  [11] POST /events/{id}/status → completed"

  del /tracks/"$TRACK_ID2" > /dev/null 2>&1 || true
  echo "  [12] DELETE /tracks/{id} (attempt recorded)"
}

# ─── Master runner ────────────────────────────────────────────────────────────
run_all_flows() {
  echo "Starting SealHackathon complete flow recording..."
  echo "Flows run through proxy at $BASE_URL"
  echo ""

  sf1_university_campus
  sf2_user_management
  sf3_auth_flow
  sf4_event_track_lifecycle
  sf5_round_criteria_setup
  sf6_team_create_and_join
  sf7_join_requests
  sf8_judge_mentor_assignment
  sf9_round_participants
  sf10_submission_flow
  sf11_scoring_flow
  sf12_rankings_reports
  sf13_mentor_feedback
  sf14_incident_flow
  sf15_team_admin_actions
  sf16_notices_prizes
  sf17_audit_logs
  sf18_support_tickets
  sf19_team_chat
  sf20_event_close_and_cleanup

  echo ""
  echo "======================================================"
  echo " All 20 flows complete."
  echo " primitive_traces.jsonl is ready for trace_compiler."
  echo "======================================================"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  run_all_flows
fi
