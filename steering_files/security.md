# Security Steering: Data App Factory

This file defines the security policies and coding guardrails the AI IDE must follow
for every line of code it generates. Treat this as a non-negotiable security checklist.

---

## 1. Credential & Secret Management

### Rules (MANDATORY — AI must not violate these)
- **NEVER** hardcode credentials, tokens, passwords, or connection strings in any source file
- **NEVER** commit `.env` files — always include `.env` in `.gitignore`
- **NEVER** log secrets, tokens, or connection strings — even at DEBUG level
- **NEVER** expose the Databricks token in Gradio UI output or error messages

### Approved Secret Patterns
```python
# CORRECT — local development
from dotenv import load_dotenv
import os
load_dotenv()
token = os.getenv("DATABRICKS_TOKEN")  # reads from .env, never hardcoded

# CORRECT — Databricks Apps deployed environment (Config() auto-resolves OAuth, no manual token needed)
from databricks.sdk.core import Config
cfg = Config()  # credentials injected automatically by the Apps runtime

# WRONG — never do this
token = "dapi1234567890abcdef"  # BLOCKED: hardcoded credential
```

### Required `.env.example` File
The AI must generate this file (with placeholder values only):
```env
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=your_token_here
DATABRICKS_WAREHOUSE_ID=your_warehouse_id
DATABRICKS_CATALOG=main
DATABRICKS_SCHEMA=default
BEDROCK_REGION=us-east-1
```

---

## 2. SQL Injection Prevention

### Rules (MANDATORY)
- All SQL queries must use parameterized execution — never string interpolation with user input
- The AI must validate this pattern whenever it generates SQL-executing code

### Approved Query Patterns
```python
# CORRECT — parameterized with databricks-sdk
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
result = w.statement_execution.execute_statement(
    warehouse_id=warehouse_id,
    statement="SELECT * FROM catalog.schema.sales WHERE region = :region",
    parameters=[{"name": "region", "value": user_region, "type": "STRING"}]
)

# CORRECT — parameterized with SQLite (local mock)
import sqlite3
conn = sqlite3.connect("database/warehouse.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM sales WHERE region = ?", (user_region,))

# WRONG — never do this
query = f"SELECT * FROM sales WHERE region = '{user_region}'"  # BLOCKED: SQL injection risk
cursor.execute(query)
```

### Chat Interface SQL Safety
When the AI generates SQL from a natural language query (Text-to-SQL):
1. Parse with `sqlparse.parse()` — reject multi-statement inputs
2. Validate no blocked keywords: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `EXEC`
3. Inject `LIMIT {max_rows}` if no LIMIT clause present
4. Wrap in a try/except and return a user-friendly error (never raw exception text to UI)

---

## 3. Authentication & Authorization

### User Identity Resolution (Gradio pattern)
```python
# services/auth_service.py — canonical pattern for Gradio + Databricks Apps
import os
import yaml
from pathlib import Path

def get_user_from_request(request) -> dict | None:
    """
    Resolve the current user from a gr.Request object (Databricks Apps / IAP).
    Falls back to DEV_USER_EMAIL env var for local dev.
    Returns: {"email": str, "role": str} or None

    Usage in any Gradio event handler:
        def my_handler(input_val, request: gr.Request):
            user = auth_service.get_user_from_request(request)
    """
    try:
        # Databricks Apps / IAP injects this header
        email = None
        if request and hasattr(request, "headers"):
            email = request.headers.get("X-Forwarded-Email")
        if not email:
            # Local dev fallback — set in .env
            email = os.getenv("DEV_USER_EMAIL", "dev@local")
        if not email:
            return None
        return {"email": email, "role": resolve_role(email)}
    except Exception:
        return None

def resolve_role(email: str) -> str:
    """Look up role from governance/roles.yaml — never hardcode role assignments."""
    roles_path = Path(__file__).parent.parent / "governance" / "roles.yaml"
    with open(roles_path) as f:
        config = yaml.safe_load(f)
    user_map = config.get("users", {})
    return user_map.get(email, config.get("default_role", "viewer"))
```

### Tab-Level Access Enforcement (Gradio)
In Gradio, enforce role gating inside event handler functions by returning early before executing any logic:

```python
# Pattern for every sensitive event handler
def load_audit_data(request: gr.Request) -> pd.DataFrame:
    user = auth_service.get_user_from_request(request)
    if not user or user["role"] not in ("analyst", "admin"):
        audit_service.log_event(action_type="ACCESS_DENIED",
                                user_email=user["email"] if user else "unknown")
        return pd.DataFrame({"error": ["Access denied. Analyst or Admin role required."]})
    # ... proceed with data loading
```

For the Admin tab, show a placeholder instead of live data when role is insufficient:
```python
def build_admin_tab() -> None:
    with gr.Tab("Admin"):
        output = gr.DataFrame(label="App Health")

        def load(request: gr.Request):
            user = auth_service.get_user_from_request(request)
            if not user or user["role"] != "admin":
                return pd.DataFrame({"message": ["Admin access required."]})
            return db_service.get_app_health_data()

        # Trigger on tab load using a dummy button or gr.on("load")
        gr.Button("Refresh", variant="secondary").click(fn=load, outputs=[output])
```

### Role Hierarchy
```
admin > analyst > viewer
```
A role satisfies any requirement at or below its level (admin can access viewer pages).

---

## 4. Input Validation & XSS Prevention

### User Text Input Rules
- All `gr.Textbox` values must be sanitized before use in event handlers
- Strip leading/trailing whitespace: `value.strip()`
- Maximum length enforcement: reject inputs > 2000 characters for chat, > 200 for filters
- Never pass user input directly to `gr.Markdown` with `value=user_input` — Gradio renders markdown, so a malicious user could inject formatting; only render system-generated markdown

### File Upload Safety (if applicable)
- Only allow `.csv` file uploads for data import features
- Validate MIME type and file extension before processing
- Maximum file size: 10 MB
- Parse with `pd.read_csv()` inside a try/except — never `eval()` or `exec()` on uploaded content

---

## 5. Error Handling & Information Disclosure

### Rules
- **NEVER** show raw Python tracebacks or exception text to end users
- Catch all exceptions at the service layer and return structured error objects
- Display only user-friendly messages in the UI

### Approved Error Pattern
```python
# services/db_service.py
def get_sales_data(region: str, limit: int = 1000) -> pd.DataFrame:
    try:
        # ... execute query
        return df
    except Exception as e:
        audit_service.log_event(action_type="QUERY_FAILED", error=str(e))
        raise ServiceError("Unable to retrieve sales data. Please try again.") from e

# components/dashboard_tab.py — event handler returns error to Gradio output
def load_data(region: str, request: gr.Request) -> pd.DataFrame:
    try:
        return db_service.get_sales_data(region=region)
    except ServiceError as e:
        return pd.DataFrame({"error": [str(e)]})  # user-friendly message only
```

---

## 6. Data Transmission & Storage

### In Transit
- All Databricks connections use HTTPS/TLS — enforced by the SDK; no plain HTTP allowed
- Never pass sensitive data as URL query parameters

### At Rest
- The local `warehouse.db` (SQLite) must contain only **synthetic/sample** data — no real PII
- The `logs/audit_trail.csv` must not contain query result data — only metadata

### Export Security
- CSV exports are restricted to `analyst` and `admin` roles (enforced in `nav_guard.py`)
- Export filenames must not expose internal table names or schema: use generic names like `data_export_YYYYMMDD.csv`
- Log every export event in the audit trail with row count and user

---

## 7. Dependency Security

- Pin all dependency versions in `requirements.txt` (use `==` not `>=`)
- Do not install packages not listed in `requirements.txt` without updating the file
- Avoid packages with known CVEs — if the AI suggests an unfamiliar package, add a comment noting it should be reviewed
- Do not use `subprocess`, `os.system()`, or `eval()` anywhere in the codebase
