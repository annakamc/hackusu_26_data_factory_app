# Project Structure: Databricks Data App Factory

Follow this exact directory structure. The AI IDE should generate all files to conform
to these paths and naming conventions.

```
my-data-app/
├── app.yaml                        # Databricks Apps deployment configuration
├── requirements.txt                # Pinned Python dependencies
├── .env.example                    # Template for local environment variables (no real secrets)
├── .gitignore                      # Must include .env, *.db, __pycache__, logs/
├── README.md                       # Project documentation and user guide
│
├── app.py                          # Main Gradio entry point — defines gr.Blocks layout
│
├── services/                       # Business logic — no UI imports allowed here
│   ├── db_service.py               # All SQL execution; returns pandas DataFrames
│   ├── ai_service.py               # LLM/Bedrock/Genie API calls; Text-to-SQL logic
│   ├── auth_service.py             # User identity from gr.Request, role resolution
│   └── audit_service.py           # Writes to audit trail; never reads from UI layer
│
├── components/                     # Reusable Gradio UI builder functions
│   ├── dashboard_tab.py            # Builds the Dashboard gr.Tab content; returns nothing (uses gr.Blocks context)
│   ├── chat_tab.py                 # Builds the Chat gr.Tab with gr.Chatbot + gr.Textbox
│   ├── audit_tab.py                # Builds the Audit Log gr.Tab (analyst/admin only)
│   ├── admin_tab.py                # Builds the Admin gr.Tab (admin only)
│   └── kpi_row.py                  # Reusable KPI metric row using gr.Markdown + gr.Number
│
├── data/                           # Data layer definitions (no raw data files in git)
│   ├── queries.sql                 # Named SQL query templates (parameterized)
│   ├── schema.yaml                 # Unity Catalog table definitions and metadata
│   └── sample_data.csv             # Synthetic seed data for local SQLite testing only
│
├── database/                       # Local mock database (for offline development only)
│   ├── setup_db.py                 # Creates SQLite tables and inserts synthetic seed data
│   └── warehouse.db                # Generated SQLite file (in .gitignore)
│
├── governance/                     # Governance artifacts — document the factory rules
│   ├── roles.yaml                  # User role definitions and tab/feature permissions
│   ├── guardrails.yaml             # Allowed query patterns, resource limits, blocked operations
│   ├── data_catalog.yaml           # Approved datasets: name, owner, sensitivity, access level
│   └── approval_workflow.md        # Conceptual approval process for new app deployments
│
├── logs/                           # Runtime logs (in .gitignore, generated at runtime)
│   └── audit_trail.csv             # Append-only governance log (timestamp, user, query, rows)
│
└── tests/                          # Unit and integration tests
    ├── test_db_service.py
    ├── test_ai_service.py
    └── test_auth_service.py
```

---

## Key File Contracts

### `app.yaml` (Databricks Apps Configuration)
This is the deployment manifest. The official Gradio template structure is:
```yaml
command: [
  "python",
  "app.py"
]

env:
  - name: "DATABRICKS_WAREHOUSE_ID"
    valueFrom: "sql-warehouse"          # Databricks Apps injects the warehouse ID at runtime
  - name: "GENIE_SPACE_ID"
    value: "your-genie-space-id"        # Add additional static env vars here
  - name: "BEDROCK_REGION"
    value: "us-east-1"
```

- The Gradio command is `["python", "app.py"]` — NOT `["streamlit", "run", "app.py"]`
- `valueFrom: "sql-warehouse"` is the canonical way to inject a SQL Warehouse ID — never hardcode it
- No `GRADIO_BROWSER_GATHER_USAGE_STATS` needed; suppress the footer via `css="footer {visibility: hidden}"` in `gr.Blocks()`

### `app.py` (Entry Point)
The top-level Blocks instance **must be named `demo`** for Gradio hot-reload to work.

```python
import gradio as gr
import os
from services import auth_service, db_service
from components import dashboard_tab, chat_tab, audit_tab, admin_tab

assert os.getenv("DATABRICKS_WAREHOUSE_ID"), "DATABRICKS_WAREHOUSE_ID must be set in app.yaml."

# Load static data once at startup (not on every user action)
initial_data = db_service.get_summary_data()

with gr.Blocks(css="footer {visibility: hidden}", title="Data App Factory") as demo:
    # Per-session state
    current_user = gr.State(None)   # populated on first interaction via gr.Request
    chat_history = gr.State([])

    gr.Markdown("# Data App Factory")

    with gr.Tabs():
        with gr.Tab("Dashboard"):
            dashboard_tab.build(initial_data)

        with gr.Tab("Ask Your Data"):
            chat_tab.build(chat_history, current_user)

        with gr.Tab("Audit Log"):
            audit_tab.build()               # enforces analyst/admin role internally

        with gr.Tab("Admin"):
            admin_tab.build()               # enforces admin role internally

if __name__ == "__main__":
    demo.launch()
```

### `components/dashboard_tab.py` (Dashboard Tab)
Each component module exposes a single `build(...)` function called inside the `gr.Blocks` context:

```python
import gradio as gr
import pandas as pd

def build(data: pd.DataFrame) -> None:
    """Called inside gr.Blocks context. Adds Dashboard tab components in-place."""
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Total Revenue")
            gr.Number(value=data["revenue"].sum(), label="", interactive=False)
        with gr.Column(scale=1):
            gr.Markdown("### Total Orders")
            gr.Number(value=len(data), label="", interactive=False)
        with gr.Column(scale=1):
            gr.Markdown("### Avg Order Value")
            gr.Number(value=data["revenue"].mean(), label="", interactive=False)

    with gr.Row():
        region_filter = gr.Dropdown(
            choices=sorted(data["region"].unique().tolist()),
            label="Filter by Region", value=None
        )

    chart = gr.ScatterPlot(
        value=data, x="order_date", y="revenue",
        x_title="Date", y_title="Revenue ($)",
        height=400, container=False
    )
    table = gr.DataFrame(value=data, height=300)

    # Wire filter to chart and table
    region_filter.change(
        fn=lambda r: (data[data["region"] == r] if r else data,
                      data[data["region"] == r] if r else data),
        inputs=[region_filter],
        outputs=[chart, table]
    )
```

### `components/chat_tab.py` (Conversational Interface)
```python
import gradio as gr
from services import ai_service, audit_service

def build(chat_history: gr.State, current_user: gr.State) -> None:
    gr.Markdown("## Ask Your Data\nAsk questions in plain English.")
    chatbot = gr.Chatbot(label="", height=400, type="messages")
    msg_input = gr.Textbox(placeholder="e.g. What were total sales last quarter?",
                           label="Your question", max_lines=3)
    submit_btn = gr.Button("Ask", variant="primary")
    clear_btn = gr.Button("Clear", variant="secondary")

    def respond(message: str, history: list, request: gr.Request) -> tuple:
        if not message.strip():
            return history, ""
        email = request.headers.get("X-Forwarded-Email", "local-dev")
        try:
            result = ai_service.start_genie_conversation(message)
            history = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": result.text or "Here are the results."}
            ]
            audit_service.log_event(action_type="CHAT", query_text=result.sql or message,
                                    user_email=email)
        except Exception:
            history = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": "Sorry, I could not process that question. Please try again."}
            ]
        return history, ""

    submit_btn.click(fn=respond, inputs=[msg_input, chatbot, current_user],
                     outputs=[chatbot, msg_input])
    msg_input.submit(fn=respond, inputs=[msg_input, chatbot, current_user],
                     outputs=[chatbot, msg_input])
    clear_btn.click(fn=lambda: ([], ""), outputs=[chatbot, msg_input])
```

### `services/db_service.py` (Data Access)
- All functions must accept only typed parameters (no raw user strings in SQL)
- Return type is always `pd.DataFrame`
- Include `row_limit: int = 1000` parameter on all query functions
- Log every call to `audit_service.log_query()` before returning
- Use the canonical connection pattern from the official `gradio-data-app` template:

```python
import os
from databricks import sql
from databricks.sdk.core import Config
import pandas as pd

def _sql_query(query: str) -> pd.DataFrame:
    """Low-level executor. Never call from UI layer — use typed public functions only."""
    cfg = Config()
    with sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
        credentials_provider=lambda: cfg.authenticate
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall_arrow().to_pandas()

# Public functions are typed — never expose raw query strings to callers
def get_summary_data(limit: int = 5000) -> pd.DataFrame:
    return _sql_query(f"SELECT * FROM main.sales.orders LIMIT {limit}")
```

### `governance/roles.yaml` (RBAC)
```yaml
roles:
  viewer:
    tabs: [Dashboard, "Ask Your Data"]
    can_export: false
    can_see_pii: false
  analyst:
    tabs: [Dashboard, "Ask Your Data", "Audit Log"]
    can_export: true
    can_see_pii: false
  admin:
    tabs: all
    can_export: true
    can_see_pii: true
```

---

## Naming Conventions

- Python files: `snake_case.py`
- Gradio tab labels: Title Case string matching `roles.yaml` tab names exactly
- SQL queries: named with action verb + subject (`get_monthly_sales`, `count_active_users`)
- YAML keys: `snake_case`
- Environment variables: `SCREAMING_SNAKE_CASE` (e.g., `DATABRICKS_HOST`)
- Git branches: `feature/feature-name`, `fix/bug-name`
