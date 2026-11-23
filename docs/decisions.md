# Design Decisions: Final Project

Recorded Nov 16, 2026. Final project due Dec 4, 2026 (target submission Dec 3).
Items marked **proposed** differ from the original choice or are awaiting confirmation.

## Core architecture

| Area | Decision | Reason |
|---|---|---|
| Storage | Azure SQL Database | Recommended by the requirements; gives database performance metrics for the dashboard |
| SQL access | **Proposed:** Function App managed identity (Entra auth), no database password | Removes a secret; fits the Key Vault and least-privilege story |
| Record ID | UUID primary key, preserved from the midterm | Stable identifier; professor feedback |
| Compute | Existing midterm Function App and resource group | Fewer moving parts |
| Secrets | Azure Key Vault (`kv-videogames-dev-001`, secret `api-key`), Azure RBAC | Easier to explain least privilege than access policies |
| Key retrieval (API) | `DefaultAzureCredential` with a short cache | Rotated key takes effect without redeploying |
| Key retrieval (workflow) | Logic App managed identity, "Key Vault Secrets User" role | Required; least privilege |

## API

| Area | Decision |
|---|---|
| Endpoints | `GET/POST /api/games`, `GET/PUT/DELETE /api/games/{id}`, `PATCH /api/games/validate` |
| Auth header | `x-api-key` on every endpoint |
| Date handling | `releaseDate` validated as a real `YYYY-MM-DD` date |

### Schema

`id` (UUID, PK), `title`, `developer`, `releaseDate`, `price` (decimal), `upcoming` (bool, default false), `isFree` (bool, default false), `validatedOn` (nullable UTC timestamp), `imageUrl` (nullable)

### Validation rules

1. `releaseDate` after today sets `upcoming = true`.
2. `price == 0` sets `isFree = true`.

- **Proposed:** flags are set both ways (true when the condition holds, false otherwise) so they cannot go stale.
- `updatedCount` counts only records whose stored values actually changed, so a second run returns 0.
- `validatedOn` is set on every record evaluated.
- Response: `{ "updatedCount": n, "timestamp": "<UTC ISO 8601 with Z>" }`

## Automation and monitoring

| Area | Decision |
|---|---|
| Logic App trigger | Manual |
| Logic App plan | **Proposed:** Consumption (original choice was Standard; Standard has a fixed hosting cost and nothing in the requirements needs it) |
| Notification | Outlook email, sent on both success and failure paths |
| Secrets in run history | Secure Inputs/Outputs on the Key Vault and HTTP actions |
| Custom events | `ValidationTriggered`, `ValidationCompleted`, `GameCreated`, **proposed:** `GameMarkedUpcoming`, `GameMarkedFree` (replace `GameArchived`) |
| Event granularity | One event per record changed, with game ID and rule name as properties |
| Logging | Structured key-value properties via `logging`, sent to Application Insights |
| Alert | Failed requests above a threshold in a 5-minute window |

## Dashboard: `FinalProject-{YourName}`

| Category | Tile |
|---|---|
| API Health | Request volume, failures, and response time |
| Storage | Azure SQL CPU % |
| Security | Key Vault service API hits |
| Automation | Logic App runs succeeded vs. failed |
| Custom | KQL chart of custom events and recent failures |

## Governance features (for the report)

1. API key management: rotation without editing the workflow.
2. Diagnostic logging: tracing a failed validation run.

## Extras

| Extra | Status | Decide by |
|---|---|---|
| OpenAPI spec | Committed | Nov 16 |
| Azure Policy (audit-only: required tags, allowed regions) | Committed | Nov 16 |
| Frontend with game images (`imageUrl` only) | Stretch, only if on schedule | Nov 22 |
| Cost Management budget and tile | Stretch | Nov 25 |
| Defender for Cloud | Feasibility check only; drop if not free and quick | Nov 25 |

Hard cutoff for any unfinished extra: Nov 29.

## Repository and deliverables

- Same GitHub repo, work on the `final-project` branch, merged before submission. The midterm is preserved at tag `midterm-submission`.
- Azure DevOps used for work items; commits reference them as `AB#<id>`.
- Deployment artifacts: Bicep files.
- Report written in Google Docs, exported to Word or PDF for submission.
- Slides due the same day as the project.

## Update: Nov 22, 2026

### Implemented
- Azure SQL with managed-identity access (no database password), verified on Azure. Item is no longer "proposed".
- UUIDs stored as UNIQUEIDENTIFIER and returned lowercase. `GET /api/games/{id}` added.

### Behavior decisions
- A non-UUID id returns 404, the same as an unknown id (midterm contract preserved).
- Database unreachable returns 503; any other unexpected error returns a generic 500 (details only in logs).
- PUT: `imageUrl` is optional (omit = keep, null = clear). `upcoming`, `isFree` and `validatedOn` are server-managed.
- Validation: strict YYYY-MM-DD dates; price at most 2 decimal places and at most 99,999,999.99.

### Extras
- Frontend: GO as a scoped stretch (imageUrl only, no Blob uploads), build window Nov 29, hard cutoff Nov 29.
- Azure Policy: audit-only assignments for required tags and allowed regions.

### Still proposed (confirm before building)
- Logic App on the Consumption plan; two-way `upcoming`/`isFree` fla- Logic App on the Consumptipcoming` and `GameMarkedFree`.
