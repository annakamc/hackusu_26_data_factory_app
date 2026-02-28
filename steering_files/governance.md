# Governance Steering: Data App Factory

This file defines the governance framework the AI IDE must implement and enforce.
Every feature, query, and data interaction must be designed with these policies in mind.

---

## 1. Data Governance

### Data Discovery
- Users may only access datasets listed in `governance/data_catalog.yaml`
- The catalog must record: table name, Unity Catalog path, owner, sensitivity level, allowed roles
- Sensitivity levels: `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`
- The app's data selection UI must only surface `PUBLIC` and `INTERNAL` datasets to `viewer` roles

### Data Lineage
- Every dashboard and visualization must display the Unity Catalog source table path
- Format: `catalog.schema.table` shown as a caption below each chart
- The audit trail must record source table(s) for every query executed

### Data Quality Validation
- Before rendering any dataset, run these checks in `db_service.py`:
  - Row count > 0 (warn user if empty result)
  - No null values in primary key / identifier columns
  - Date ranges are within expected bounds (no future dates for historical data)
- Display a data freshness indicator: show the `MAX(updated_at)` timestamp on dashboards

### Data Classification
- PII columns (e.g., `email`, `ssn`, `phone`, `full_name`) must be tagged in `data_catalog.yaml`
- These columns must be masked at the service layer before any DataFrame is returned to the UI
- Masking rules by role:
  - `viewer`: All PII columns replaced with `***REDACTED***`
  - `analyst`: Partially masked (e.g., `j***@example.com`)
  - `admin`: Full visibility (logged in audit trail when accessed)

---

## 2. Access Control

### Role-Based Access Control (RBAC)
Define three roles — all enforcement happens in `auth_service.py` and `nav_guard.py`:

| Role     | Pages Accessible             | Export | PII Access | Query Limit |
|----------|------------------------------|--------|------------|-------------|
| viewer   | home, dashboard, chat        | No     | Redacted   | 500 rows    |
| analyst  | + audit_log                  | Yes    | Masked     | 5,000 rows  |
| admin    | All pages including admin    | Yes    | Full       | Unlimited   |

### Row-Level Security
- Implement at the SQL layer, not the Python layer
- Use Unity Catalog row filters where available
- Fallback: add a `WHERE` clause based on `current_user_region` or `current_user_department`
- Example pattern:
  ```sql
  SELECT * FROM catalog.schema.sales_data
  WHERE region = :user_region  -- parameterized, never f-string
  ```

### Column Masking
- Implement in `services/db_service.py` immediately after query execution
- Never return unmasked PII to the UI layer for unauthorized roles
- Log every PII access attempt by admin users in the audit trail

### Session Management
- User session must expire after 8 hours of inactivity
- Use `gr.State` to store user context per Gradio session; never use global Python variables for per-user state
- Re-authenticate if session token is missing or expired

---

## 3. Audit Trail

The audit trail is the primary governance artifact. It must be append-only.

### Required Fields (written by `audit_service.py`)
```python
{
    "timestamp": "ISO 8601 UTC",        # datetime.utcnow().isoformat()
    "session_id": "uuid4",
    "user_email": "user@example.com",
    "user_role": "analyst",
    "action_type": "QUERY | CHAT | EXPORT | LOGIN | ACCESS_DENIED | QUERY_FAILED",
    "ai_source": "genie | bedrock | mock | None",  # which tier answered the CHAT
    "source_tables": "catalog.schema.table",
    "query_text": "SELECT ...",         # parameterized template only, not filled values
    "row_count": 42,
    "execution_time_ms": 310,
    "pii_accessed": false
}
```

### Storage
- Local dev: `logs/audit_trail.csv` (append mode, never overwrite)
- Databricks: Unity Catalog Delta table `catalog.governance.audit_log`
- The `audit_log` tab in the app reads from this source and is restricted to `analyst` and `admin`

### Audit Log Rules
- Every `db_service` call MUST invoke `audit_service.log_query()` — no exceptions
- Failed queries must also be logged with `action_type: "QUERY_FAILED"` and error message
- Chat interactions must log: the natural language question, the generated SQL, AND the `ai_source` field (`ChatResponse.source`) so IT knows whether Genie or Bedrock answered

---

## 4. Application Guardrails

These guardrails constrain what apps the factory can produce, enforced via `governance/guardrails.yaml`.

### Allowed Operations
```yaml
allowed_sql_operations:
  - SELECT
  - WITH  # CTEs are allowed
blocked_sql_operations:
  - INSERT
  - UPDATE
  - DELETE
  - DROP
  - TRUNCATE
  - CREATE
  - ALTER
  - EXEC
  - EXECUTE
```

### Resource Limits
```yaml
resource_limits:
  max_rows_per_query: 10000
  max_query_execution_seconds: 30
  max_concurrent_queries_per_user: 3
  max_export_rows: 50000
  max_chart_data_points: 5000
```

### Template Restrictions
- Business users (viewer/analyst) may only use pre-approved dashboard templates
- Templates are defined in `governance/data_catalog.yaml` under `approved_templates`
- Custom SQL from the chat interface must pass through the guardrail validator before execution:
  1. Parse the generated SQL with `sqlparse`
  2. Reject any statement containing blocked operations
  3. Enforce row limit via injected `LIMIT` clause if missing
  4. Log validation result in audit trail

### Approval Workflow (Conceptual)
New app templates follow this lifecycle:
```
Developer submits → IT review (guardrail check) → Sandbox deploy → Approval → Production
```
- Sandbox apps are flagged with `category: "dev"` in `all_pages.py`
- Production apps are promoted by setting `category: "main"`
- The admin dashboard shows pending approvals and deployment status

---

## 5. IT Oversight

### Visibility Dashboard (`pages/admin.py`)
Admin-only page that displays:
- All deployed app pages and their deployment status
- Active sessions: user email, role, session start time, query count
- Resource usage: queries per hour, average execution time, error rate
- Recent audit log entries with filter by user, action type, and date range

### Health Monitoring
- Display query success rate as a KPI (target: > 99%)
- Alert if average query execution exceeds 10 seconds (display warning banner)
- Show data freshness for all source tables (staleness > 24h triggers warning)

### Compliance Reporting
- Admin can generate a governance report (CSV export) containing:
  - Total queries by user and role
  - PII access events
  - Access denied events
  - Export events

### Kill Switch
- Admin page must include a feature toggle section
- Each page in `all_pages.py` supports an `enabled: true/false` flag
- Disabling a page hides it from navigation for all non-admin users immediately
- This simulates the "kill switch" for non-compliant apps
