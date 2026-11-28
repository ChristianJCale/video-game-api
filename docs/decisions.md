# Design Decisions: Final Project

Recorded Nov 16, 2026. Last updated Nov 27, 2026. Final project due Dec 4, 2026 (target submission Dec 3).
No decisions are still marked **proposed**. The tables below show the current state; the dated updates at the end record how each decision was made and what was built.

## Core architecture

| Area | Decision | Reason |
|---|---|---|
| Storage | Azure SQL Database | Recommended by the requirements; gives database performance metrics for the dashboard |
| SQL access | Function App managed identity (Entra auth), no database password | Removes a secret; fits the Key Vault and least-privilege story. Verified on Azure Nov 22 |
| Record ID | UUID primary key, preserved from the midterm | Stable identifier; professor feedback |
| Compute | Existing midterm Function App (Flex Consumption) and resource group | Fewer moving parts |
| Secrets | Azure Key Vault (`kv-videogames-cc-001`, secret `api-key`), Azure RBAC | Easier to explain least privilege than access policies |
| Key retrieval (API) | `DefaultAzureCredential` with a 60-second cache | Rotated key takes effect without redeploying |
| Key retrieval (workflow) | Logic App system-assigned managed identity, "Key Vault Secrets User" role | Required; least privilege |

## API

| Area | Decision |
|---|---|
| Endpoints | `GET/POST /api/games`, `GET/PUT/DELETE /api/games/{id}`, `PATCH /api/games/validate` |
| Auth header | `x-api-key` on every endpoint |
| Date handling | `releaseDate` validated as a real `YYYY-MM-DD` date |
| Error responses | 401 missing or wrong key; 404 unknown or non-UUID id; 503 database unavailable; generic 500 for anything else |

### Schema

`id` (UUID, PK), `title`, `developer`, `releaseDate`, `price` (decimal), `upcoming` (bool, default false), `isFree` (bool, default false), `validatedOn` (nullable UTC timestamp), `imageUrl` (nullable)

### Validation rules

1. `releaseDate` after today (UTC) sets `upcoming = true`.
2. `price == 0` sets `isFree = true`.

- Flags are set both ways (true when the condition holds, false otherwise) so they cannot go stale.
- `updatedCount` counts only games whose stored flag values actually changed, so a second run returns 0.
- `validatedOn` is set on every game evaluated.
- Response: `{ "updatedCount": n, "timestamp": "<UTC ISO 8601 with Z>" }`

## Automation and monitoring

| Area | Decision |
|---|---|
| Logic App trigger | Manual ("When an HTTP request is received", started with Run trigger) |
| Logic App plan | Consumption (confirmed Nov 25). Standard has a fixed hosting cost and nothing in the requirements needs it |
| Workflow | Trigger, Key Vault "Get secret", HTTP `PATCH /api/games/validate` with the secret as `x-api-key`, then two parallel branches: a success email, and a failure email followed by a Terminate action |
| Notification | Office 365 Outlook "Send an email (V2)" using the school account. Success email carries `updatedCount` and `timestamp`; failure email carries the run ID and UTC time, never the HTTP response |
| Failure handling | The failure branch runs after the HTTP action has failed or timed out, and ends with Terminate (status Failed, code `ValidationFailed`) so a handled failure still counts as a failed run |
| Secrets in run history | Secure Inputs and Secure Outputs on the Get secret and HTTP actions |
| Custom events | `ValidationTriggered`, `ValidationCompleted`, `GameCreated`, `GameMarkedUpcoming`, `GameMarkedFree` (replace `GameArchived`) |
| Event granularity | One event per record changed, with game ID and rule name as properties |
| Logging | Structured key-value properties via `logging`, sent to Application Insights |
| Alert | Failed requests above a threshold in a 5-minute window |

## Dashboard: `FinalProject-ChristianCale`

A new dashboard separate from the earlier `Cloud Cost Monitor` dashboard, which belongs to a previous lab and points at resources that no longer exist.

| Category | Tile |
|---|---|
| API Health | Request volume, failures, and response time |
| Storage | Azure SQL CPU % |
| Security | Key Vault service API hits |
| Automation | Logic App runs succeeded vs. failed |
| Cost | Cost analysis view scoped to `rg-videogames-dev` |
| Custom | KQL chart of custom events and recent failures |

## Governance features (for the report)

1. API key management: rotation without editing the workflow. Tested Nov 27 (see below).
2. Diagnostic logging: tracing a failed validation run. Tested Nov 27 with a forced failure (see below).

## Extras

| Extra | Status | Decided |
|---|---|---|
| OpenAPI spec | Committed; includes `PATCH /games/validate` and the 503 response | Nov 16 |
| Azure Policy (audit-only: required tags, allowed regions) | Committed | Nov 16 |
| Frontend with game images (`imageUrl` only) | Stretch, build window Nov 29 | Nov 22 |
| Cost Management budget and tile | **Committed** | Nov 25 |
| Defender for Cloud | **Dropped** (free tier on, no recommendations on the project's resources) | Nov 25 |

Hard cutoff for any unfinished extra: Nov 29.

## Repository and deliverables

- Same GitHub repo, work on the `final-project` branch, merged before submission. The midterm is preserved at tag `midterm-submission`.
- Azure DevOps used for work items; commits reference them as `AB#<id>`.
- Deployment artifacts: Bicep files.
- Report written in Google Docs, exported to Word or PDF for submission.
- Slides due the same day as the project.

## Update: Nov 22, 2026

### Implemented
- Azure SQL with managed-identity access (no database password), verified on Azure.
- UUIDs stored as UNIQUEIDENTIFIER and returned lowercase. `GET /api/games/{id}` added.

### Behavior decisions
- A non-UUID id returns 404, the same as an unknown id (midterm contract preserved).
- Database unreachable returns 503; any other unexpected error returns a generic 500 (details only in logs).
- PUT: `imageUrl` is optional (omit = keep, null = clear). `upcoming`, `isFree` and `validatedOn` are server-managed.
- Validation: strict YYYY-MM-DD dates; price at most 2 decimal places and at most 99,999,999.99.

### Extras
- Frontend: GO as a scoped stretch (imageUrl only, no Blob uploads), build window Nov 29, hard cutoff Nov 29.
- Azure Policy: audit-only assignments for required tags and allowed regions.

## Update: Nov 24, 2026

### Confirmed
- Flags are set both ways, so `upcoming` and `isFree` cannot go stale.
- Custom events `GameMarkedUpcoming` and `GameMarkedFree` replace `GameArchived`.

### Implemented: `PATCH /api/games/validate`
- One atomic `UPDATE ... OUTPUT` statement evaluates every game; the OUTPUT clause returns old and new flag values so changes are detected without a second query.
- "Today" is the UTC date. A game released today is not upcoming.
- `updatedCount` counts games, not flags: a game that gains both flags in one run counts once.
- `validatedOn` is `DATETIME2(0)`, so the run time is truncated to whole seconds, and the stored value equals the `timestamp` in the response.
- Flags only refresh when validation runs. Editing a price or release date with PUT leaves the old flags until the next run.
- Auth runs first; an unauthenticated request never reaches the database.

### Telemetry
- Application Insights through OpenTelemetry (`telemetryMode: OpenTelemetry` in host.json, `azure-monitor-opentelemetry`, and the events extension). The `logging.applicationInsights` block was removed from host.json because it does not apply in this mode.
- Custom events: `ValidationTriggered`, `ValidationCompleted` (evaluated, updatedCount, timestamp), `GameCreated`, and one `GameMarkedUpcoming` or `GameMarkedFree` per game when a flag turns on (properties: gameId, rule).
- A flag turning off is logged (`game_flag_changed ... flagValue=False`) but does not raise an event.
- Structured logs: `validation_triggered`, `game_flag_changed`, `validation_completed`, `game_created`, written as key=value text with the same keys as custom dimensions.
- Database calls run inside a client span (`db.system = mssql`) so they can appear as SQL dependencies.
- Failure evidence comes from the failed request (503 or 500) plus the logged exception; no separate failure event.

## Update: Nov 25, 2026 (decision day)

### Correction
- The Key Vault name in the original decision table was wrong. The vault is `kv-videogames-cc-001`, matching the README and the Function App's `KEY_VAULT_URL` setting.

### Implemented: database connection reliability
- A paused serverless database rejects the first connection with error 40613 ("not currently available"). The original retry only caught `pyodbc.OperationalError`, but this error arrives as the base `pyodbc.Error`, so nothing retried and the API returned a 500.
- `db.py` now retries on `pyodbc.Error` when the message carries a known transient code (40613, 40197, 40501, 49918, 49919, 49920): up to 4 attempts, 15 seconds apart.
- `repository._transaction` now turns any connection failure into `DatabaseUnavailableError`, so the API answers 503 instead of 500. A firewall block (40615) also returns 503; the log shows which cause it was.
- Known limit: a cold first request can take several minutes in the worst case. Wake the database before demos and Logic App runs.

### Implemented: deployment
- The first deploy of the validate code from the VS Code zip left the host unable to read `host.json` ("Permission denied" at `/home/site/wwwroot/host.json`), so every request returned 503 "Function host is not running". The deploy log had warned "Zip permission validation failed".
- Fixed by making the files readable (`chmod 644`) and publishing with `func azure functionapp publish func-videogames-dev-001`, which also prints the full build log.
- `.funcignore` now keeps `__pycache__/`, `*.pyc`, `scripts/` and `validate_tests.sh` out of the deploy package.
- `scripts/validate_tests.sh` (18 checks) tests `PATCH /games/validate` against the deployed API, next to `scripts/azure_crud_tests.sh`.

### Implemented: Logic App (Consumption plan, confirmed)
- Name `logic-videogames-validate-001`, in `rg-videogames-dev`, tagged like the other resources.
- System-assigned managed identity with the **Key Vault Secrets User** role on `kv-videogames-cc-001`.
- Workflow: manual HTTP trigger, then Key Vault **Get secret** (`api-key`, managed identity connection), then **HTTP** `PATCH` to `/api/games/validate` with header `x-api-key` set to the secret's Value, then **Send an email (V2)** with `updatedCount` and `timestamp` from the response.
- Secure Inputs and Secure Outputs are on for Get secret and HTTP, so the key never appears in run history.
- Email connector: **Office 365 Outlook**, not Outlook.com. The Outlook.com connector signs in at `login.live.com`, which only accepts personal Microsoft accounts and rejects the school address.
- Draft test runs succeeded (3:56 PM and 3:58 PM); the workflow was published at 4:01 PM.
- The trigger's callback URL is treated as a secret and kept out of screenshots and the repository.
- Known limit: outbound HTTP calls from a Consumption Logic App time out at about 2 minutes, which a cold database can exceed. The database is woken first.

### Decision: Cost Management committed
- Budget on `rg-videogames-dev`, monthly, with an email alert to the school address at 80% of actual cost. Email recipients only; no action group.
- A cost analysis view scoped to `rg-videogames-dev` is pinned to the dashboard.
- The existing subscription-level `CostLabBudget1` is left alone. It is a leftover from an earlier lab: it covers the whole subscription, has no alert recipients, and its 80% alert points at an action group that does not exist.
- Cost data lags 8 to 24 hours, so the tile may look empty at first.

### Decision: Defender for Cloud dropped
- Checked in Environment settings: the free **Foundational CSPM** plan is on and covers the subscription. Defender CSPM, Servers, App Service and the other paid plans are off and stay off.
- Recommendations showed no findings (0 critical, high, medium and low) at the time of the check, and no filters were hiding results.
- Per the ten-minute rule, the extra is dropped. It is recorded as a feasibility finding for the report. Revisit only if a recommendation appears before Nov 29.

### Dashboard
- New dashboard `FinalProject-ChristianCale`. The older `Cloud Cost Monitor` dashboard is left unchanged and not used.
- Tiles are pinned from each resource's own Metrics or Logs page so each keeps the right scope.

## Update: Nov 27, 2026

### Implemented: Logic App failure path
- The failure email is a parallel branch after the HTTP action, not a step after the success email, so each outcome has its own path.
- Run after is set to **has failed** and **has timed out** only. It never runs when the HTTP call succeeds.
- Email subject `Video Game API validation FAILED`. The body holds the run ID (`workflow()['run']['name']`), the UTC time (`utcNow()`) and a pointer to the run history and Application Insights. It does not include the HTTP response: Secure Outputs hides it, and a failed call should not be mailed around.
- A **Terminate** action follows the failure email (status Failed, code `ValidationFailed`, message `PATCH /games/validate failed`). Without it the run ends as Succeeded because the failure was handled, and the dashboard's "Runs Failed" tile would miss it.
- The HTTP action retries 5xx responses by default, so the failure email arrives a few minutes after the failure, not immediately.

### Tested: key rotation (governance feature 1)
- Rotated the `api-key` secret in Key Vault by creating a new secret version. No code, app setting or Logic App change, and no redeploy.
- After the 60-second cache window, the old key was rejected with 401 and the new key was accepted with 200.
- The published Logic App ran again with no edits and still reached the API, because Get secret reads the current secret version on every run.
- The `api_key_refreshed secretVersion=...` log line in Application Insights shows the version change. It logs the version ID, never the value.
- The person rotating the key needs a data-plane role that can write secrets (Key Vault Secrets Officer). The Function App and Logic App identities keep read-only Secrets User.
- Neither key was printed: values were held in shell variables and `az ... --query id` was used instead of echoing the secret.

### Tested: forced failure (governance feature 2)
- Method: set the Function App's `SQL_DATABASE` setting to a database name that does not exist, then call `PATCH /games/validate` directly and through the Logic App.
- Chosen over a wrong API key because a bad key only produces a 401 with nothing behind it. A bad database name produces a 503, a logged exception and a failed SQL dependency, so one failure can be traced end to end.
- Restored `SQL_DATABASE=sqldb-videogames` straight afterwards, confirmed with a `GET /games` returning 200, and ran the Logic App once more for a green published run.
- Changing app settings with `az` is done with `-o none`: without it the command prints every app setting, including the storage connection string.

### Evidence captured in Application Insights
- **Live Metrics** while `validate_tests.sh` ran, showing request rate and sample telemetry.
- **Custom event:** `customEvents` rows for `ValidationTriggered`, `ValidationCompleted` and the per-game `GameMarked...` events, with their custom dimensions.
- **Failed request:** `requests` filtered to `success == false`, then the whole operation joined by `operation_Id` across requests, dependencies, exceptions and traces, which traces one failed validation run from request to database error.
- **SQL dependency:** `dependencies` rows for the `azure-sql` client span (`db.system = mssql`), successful during normal runs and failed during the forced failure.
- **Logic App:** the failed run (HTTP red, failure email green, Terminate shows Failed), the failure email, and a later green published run.

### Still open
- Pin the remaining dashboard tiles and the cost view to `FinalProject-ChristianCale`; confirm the resource-group budget has its email recipient.
- Confirm the README covers `PATCH /games/validate`, the new fields, the 503 response and telemetry.
- Frontend stretch: build window Nov 29, hard cutoff Nov 29.
- Open a pull request from `final-project` before Dec 3 and merge it, so the linked work items close.
- Report and slides.
