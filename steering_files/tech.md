# Technical Steering: Databricks Data App Factory

## Tech Stack

### Required Platform
- **Databricks Free Edition** workspace (or trial for team collaboration)
- **Unity Catalog** — all tables must be registered and accessed through Unity Catalog
- **SQL Warehouse** — use one 2X-Small warehouse; share queries efficiently
- **Databricks Apps** — deploy the final Gradio application here

### Language & Runtime
- **Language:** Python 3.10+
- **Use `python3` and `pip3`** for all Python and package manager commands
- **Path handling:** Always use `pathlib.Path` — never hardcode OS-specific path separators

### Frontend Framework
- **Framework: Gradio** — preferred for ML/chatbot-heavy apps, conversational interfaces, and data dashboards
- Build apps using `gr.Blocks()` for full layout control
- Multi-section navigation via `gr.Tabs` / `gr.Tab` — no separate page registry file needed
- The top-level Blocks instance **must** be named `demo` for Gradio hot-reload to work:
  ```python
  with gr.Blocks(css="footer {visibility: hidden}") as demo:
      ...
  if __name__ == "__main__":
      demo.launch()
  ```
- The `css="footer {visibility: hidden}"` rule must always be included to suppress the Gradio footer in Databricks Apps

### Gradio Layout Primitives (use in this order of preference)
| Component | Purpose |
|---|---|
| `gr.Blocks()` | Top-level app container — always named `demo` |
| `gr.Tabs()` / `gr.Tab()` | Multi-section navigation (Dashboard, Chat, Admin, Audit) |
| `gr.Row()` | Horizontal layout container |
| `gr.Column(scale=N)` | Vertical layout with relative width |
| `gr.Accordion()` | Collapsible section for filters or advanced options |
| `gr.State()` | Per-session state (conversation history, current user, filters) |
| `@gr.render` | Reactive re-render when input components change |

### Gradio UI Components (use these specific components)
| Component | Use For |
|---|---|
| `gr.ChatInterface` | Simple single-function chatbot (wraps Chatbot + Textbox automatically) |
| `gr.Chatbot` | Full chat history display inside Blocks with manual control |
| `gr.DataFrame` | Tabular data display |
| `gr.ScatterPlot` / `gr.LinePlot` / `gr.BarPlot` | Native Gradio charts (quick, no Plotly needed) |
| `gr.Plot` | Embed a Plotly/Matplotlib figure |
| `gr.Markdown` | Headers, KPI values, formatted text |
| `gr.Textbox` | Text input (filters, natural language queries) |
| `gr.Dropdown` | Filter selectors |
| `gr.Button` | Trigger actions |
| `gr.Number` / `gr.Slider` | Numeric inputs |

### Database / Data Layer
- **Production:** Databricks SQL Warehouse via `databricks-sql-connector` + `databricks-sdk`
- **Local Mock/Testing:** SQLite (simulating a Databricks SQL Warehouse for offline dev)
- **Sample datasets:** Use Databricks Marketplace free datasets (Manufacturing domain preferred)
  - Supply Chain Inventory & Transaction Analytics (Dataplatr)
  - Predictive Maintenance & Asset Management (Dataknobs)
  - Enterprise Software Sales Dataset (Databricks)
- All tables must be accessed through Unity Catalog: `catalog.schema.table`

**Canonical Gradio DB connection pattern** (from official `gradio-data-app` template):
```python
import os
from databricks import sql
from databricks.sdk.core import Config
import pandas as pd

# Config() automatically pulls DATABRICKS_HOST + token from env / Databricks Apps OAuth
def sql_query(query: str) -> pd.DataFrame:
    cfg = Config()
    with sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
        credentials_provider=lambda: cfg.authenticate
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall_arrow().to_pandas()
```

- `DATABRICKS_WAREHOUSE_ID` is injected by `app.yaml` at runtime — never hardcode it
- `Config()` handles auth transparently in both local dev and deployed Databricks Apps
- Use `cursor.fetchall_arrow().to_pandas()` for best performance — not plain `fetchall()`
- Load data at module level (once on startup) for static datasets; use `gr.State` + event handlers for user-triggered refreshes

### AI / LLM Integration
- **SDK:** `strands-agents` (AWS Bedrock wrapper)
- **Model:** `global.anthropic.claude-sonnet-4-6` via AWS Bedrock
- **Conversational Interface:** Genie API for natural language queries against Unity Catalog
  - Endpoint: `POST /api/2.0/genie/spaces/{space_id}/start-conversation`
  - Fallback: Custom chatbot using LLM APIs with Text-to-SQL generation
- **Text-to-SQL pattern:** AI receives schema context + user question → generates parameterized SQL → executed safely
- Use `gr.ChatInterface` for a simple single-function chat; use `gr.Chatbot` inside `gr.Blocks` for full multi-tab integration

### Authentication
- **Databricks Apps (deployed):** `Config()` from `databricks.sdk.core` auto-resolves credentials via the Apps OAuth context — zero manual token handling required
- **Local dev:** Set `DATABRICKS_HOST` and `DATABRICKS_TOKEN` as environment variables; `Config()` picks them up automatically
- **NEVER** hardcode credentials, tokens, or connection strings in source code

**How `Config()` resolves credentials (in priority order):**
1. Databricks Apps injected OAuth (when deployed)
2. `DATABRICKS_HOST` + `DATABRICKS_TOKEN` environment variables (local dev)
3. `~/.databrickscfg` file (local dev fallback)

**User identity in Gradio (Databricks Apps):**
```python
# Gradio event handlers receive a gr.Request object as the last parameter when deployed
def handle_submit(user_input: str, history: list, request: gr.Request) -> tuple:
    email = request.headers.get("X-Forwarded-Email", "anonymous")
    # use email for RBAC and audit logging
    ...
```

### Visualization Libraries
- **Primary:** Gradio native plots (`gr.ScatterPlot`, `gr.LinePlot`, `gr.BarPlot`) — no extra dependencies
- **Secondary:** `plotly` via `gr.Plot` — for complex multi-series or map charts
- `pandas` — data manipulation before rendering
- All charts must be interactive (hover, zoom, filter-responsive)

---

## Architectural Constraints

### Separation of Concerns (MANDATORY)
Keep these layers strictly separate — no mixing of concerns:
- `app.py` — Gradio UI only; defines `gr.Blocks` layout and event wiring; no business logic, no SQL
- `services/db_service.py` — all database queries; returns DataFrames
- `services/ai_service.py` — all LLM/Bedrock/Genie logic; no UI elements
- `services/auth_service.py` — user identity resolution from `gr.Request`, role lookup
- `components/` — reusable Gradio UI builder functions (return Gradio component groups)

### Data Protection (MANDATORY)
- Use **parameterized queries** exclusively — never build SQL strings via f-strings with user input
- Never log raw query results that contain PII or sensitive data
- Audit log must capture: `timestamp`, `user_email`, `query_text`, `row_count`, `execution_time_ms`
- Sensitive columns (PII) must be masked before rendering — enforce at the service layer

### Resource Efficiency (Free Edition Limits)
- Compute: Limited to small clusters — avoid datasets > 100 MB
- SQL Warehouse: One 2X-Small per account — use `LIMIT` clauses; avoid full table scans
- Concurrent Jobs: Max 5 — do not spawn background threads unnecessarily
- Storage: Serverless only, quota-limited — use sample/synthetic data
- Apps: 1 deployed app per account — team uses Designated App Builder strategy

### Dependency Management
- All Python dependencies must be listed in `requirements.txt` using `~=` (compatible release) pinning
- **Baseline packages** (from official `gradio-data-app` template — use these exact versions):
  ```
  databricks-sql-connector~=3.4.0
  databricks-sdk~=0.33.0
  gradio~=4.44.0
  huggingface-hub~=0.35.3
  pandas~=2.2.3
  plotly~=5.22.0
  strands-agents
  ```
- `gradio~=4.44.0` matches the official Databricks template; the latest stable is `6.8.0` — only upgrade if you need a specific 5.x/6.x feature, as there are breaking API changes
- Do NOT use `>=` version pinning — it risks pulling in breaking changes during the hackathon

### Version Control
- Use Git/GitHub for source control
- Commit frequently with meaningful messages
- Tag your final submission version: `git tag v1.0-hackathon-submission`
- Never commit `.env` files — add to `.gitignore`
