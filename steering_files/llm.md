# LLM & AI Integration Steering: Data App Factory

This file defines exactly how the AI IDE should generate LLM integration code.
All conversational interface features, Text-to-SQL generation, and AI responses must
follow the patterns defined here.

---

## 1. Model & Provider

### Conversational Interface — Two-Tier Architecture

```
User question
      │
      ▼
┌─────────────────────────────┐
│  TIER 1 — Genie API         │  Primary: schema-aware, Unity Catalog native,
│  (try first, always)        │  respects row-level security automatically
└────────────┬────────────────┘
             │ fails (no Space configured, timeout, rate limit, FAILED status)
             ▼
┌─────────────────────────────┐
│  TIER 2 — Bedrock / Claude  │  Fallback: Text-to-SQL via Claude Sonnet,
│  Text-to-SQL + db_service   │  runs validated SQL against SQL Warehouse
└─────────────────────────────┘
             │ no Databricks connection at all
             ▼
┌─────────────────────────────┐
│  TIER 3 — Mock (local dev)  │  USE_MOCK_AI=true in .env
└─────────────────────────────┘
```

### When Each Tier Is Used

| Situation | Tier Used |
|---|---|
| `GENIE_SPACE_ID` set and Space healthy | Genie (Tier 1) |
| Genie returns `FAILED` or `UNABLE_TO_ANSWER` | Bedrock fallback (Tier 2) |
| Genie timeout (> 60s) | Bedrock fallback (Tier 2) |
| Genie rate limit hit (5 req/min) | Bedrock fallback (Tier 2) |
| `GENIE_SPACE_ID` not set at all | Bedrock fallback (Tier 2) |
| `USE_MOCK_AI=true` | Mock (Tier 3) |

### Models
- **Genie:** Uses the Databricks-managed model behind the Genie Space — no model ID needed
- **Bedrock fallback:** `global.anthropic.claude-sonnet-4-6`
- **Insight summaries:** `global.anthropic.claude-sonnet-4-6` via Strands Agents SDK

---

## 2. Unified Chat Entry Point (the ONLY function the UI should call)

The Gradio chat handler must call **one function** — `chat_with_data()`. It handles the
Genie → Bedrock → Mock fallback chain internally. The UI never calls Genie or Bedrock directly.

```python
# services/ai_service.py  — complete file

import os
import time
import logging
import requests
import sqlparse
import re
from dataclasses import dataclass, field
from strands import Agent
from strands.models import BedrockModel

logger = logging.getLogger(__name__)

# ── Environment ──────────────────────────────────────────────────────────────
DATABRICKS_HOST  = os.getenv("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")
GENIE_SPACE_ID   = os.getenv("GENIE_SPACE_ID", "")     # empty = Genie disabled
BEDROCK_REGION   = os.getenv("BEDROCK_REGION", "us-east-1")
USE_MOCK         = os.getenv("USE_MOCK_AI", "false").lower() == "true"

GENIE_HEADERS = {
    "Authorization": f"Bearer {DATABRICKS_TOKEN}",
    "Content-Type": "application/json",
}

BLOCKED_SQL_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
    "ALTER", "CREATE", "EXEC", "EXECUTE", "GRANT", "REVOKE",
}
MAX_ROW_LIMIT = 10_000


# ── Response dataclass ────────────────────────────────────────────────────────
@dataclass
class ChatResponse:
    text: str                              # plain-English explanation shown in chat
    dataframe: "pd.DataFrame | None" = None  # query results rendered as table/chart in UI
    sql: str | None = None                 # generated SQL — audit log ONLY, never shown in chat
    conversation_id: str | None = None     # Genie conversation ID for multi-turn
    source: str = "genie"                  # "genie" | "bedrock" | "mock"
    error: str | None = None               # set only when all tiers fail


# ── PUBLIC ENTRY POINT ────────────────────────────────────────────────────────
def chat_with_data(
    question: str,
    conversation_id: str | None = None,
    schema_context: str = "",
) -> ChatResponse:
    """
    Single entry point for all conversational queries.
    Tries Genie first; falls back to Bedrock Text-to-SQL; falls back to mock.

    Args:
        question:        The user's natural-language question.
        conversation_id: Existing Genie conversation ID for multi-turn (None = new conv).
        schema_context:  Table/column descriptions passed to Bedrock if Genie fails.
                         Load from data/schema.yaml at startup.
    """
    if USE_MOCK:
        return _mock_response(question)

    # ── Tier 1: Genie ─────────────────────────────────────────────────────────
    if GENIE_SPACE_ID:
        try:
            if conversation_id:
                return _continue_genie(conversation_id, question)
            else:
                return _start_genie(question)
        except Exception as e:
            logger.warning("Genie failed (%s), falling back to Bedrock. Error: %s",
                           type(e).__name__, e)

    # ── Tier 2: Bedrock Text-to-SQL ───────────────────────────────────────────
    try:
        return _bedrock_text_to_sql(question, schema_context)
    except Exception as e:
        logger.error("Bedrock fallback also failed: %s", e)
        return ChatResponse(
            text="I was unable to answer your question. Please try rephrasing it.",
            error=str(e),
            source="error",
        )


# ── Tier 1: Genie implementation ──────────────────────────────────────────────
def _start_genie(question: str) -> ChatResponse:
    url = f"{DATABRICKS_HOST}/api/2.0/genie/spaces/{GENIE_SPACE_ID}/start-conversation"
    resp = requests.post(url, headers=GENIE_HEADERS, json={"content": question}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return _poll_genie(data["conversation_id"], data["message_id"])


def _continue_genie(conversation_id: str, question: str) -> ChatResponse:
    url = (f"{DATABRICKS_HOST}/api/2.0/genie/spaces/{GENIE_SPACE_ID}"
           f"/conversations/{conversation_id}/messages")
    resp = requests.post(url, headers=GENIE_HEADERS, json={"content": question}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return _poll_genie(conversation_id, data["message_id"])


def _poll_genie(conversation_id: str, message_id: str,
                max_wait: int = 60) -> ChatResponse:
    """
    Poll until COMPLETED or FAILED.
    Exponential backoff: 1s → 2s → 4s → capped at 5s.
    Raises RuntimeError on FAILED; TimeoutError on timeout — both trigger Bedrock fallback.
    """
    url = (f"{DATABRICKS_HOST}/api/2.0/genie/spaces/{GENIE_SPACE_ID}"
           f"/conversations/{conversation_id}/messages/{message_id}")
    wait, elapsed = 1, 0
    while elapsed < max_wait:
        data = requests.get(url, headers=GENIE_HEADERS, timeout=10).json()
        status = data.get("status")
        if status == "COMPLETED":
            text, sql = "", None
            for att in data.get("attachments", []):
                if att.get("type") == "text":
                    text = att.get("content", "")
                elif att.get("type") == "query":
                    sql = att.get("query", {}).get("query")
            # Execute the SQL so the UI can render a table/chart instead of raw code
            df = None
            if sql:
                try:
                    from services import db_service
                    df = db_service._sql_query(validate_sql(sql))
                except Exception as exc:
                    logger.warning("Could not fetch Genie query results as DataFrame: %s", exc)
            return ChatResponse(
                text=text or "Here are your results.",
                dataframe=df,
                sql=sql,        # kept for audit logging only
                conversation_id=conversation_id,
                source="genie",
            )
        elif status == "FAILED":
            raise RuntimeError(f"Genie FAILED: {data.get('error', 'unknown')}")
        time.sleep(wait)
        elapsed += wait
        wait = min(wait * 2, 5)
    raise TimeoutError("Genie timed out.")


# ── Tier 2: Bedrock Text-to-SQL fallback ─────────────────────────────────────
_BEDROCK_AGENT: Agent | None = None   # module-level singleton

def _get_agent() -> Agent:
    global _BEDROCK_AGENT
    if _BEDROCK_AGENT is None:
        _BEDROCK_AGENT = Agent(model=BedrockModel(
            model_id="global.anthropic.claude-sonnet-4-6",
            region_name=BEDROCK_REGION,
        ))
    return _BEDROCK_AGENT


_TEXT_TO_SQL_PROMPT = """\
You are a SQL expert for Databricks SQL Warehouse. Convert the user question to a single \
valid SELECT statement.

STRICT RULES:
- Output ONLY the SQL statement, nothing else
- Only SELECT is allowed — never INSERT, UPDATE, DELETE, DROP, ALTER, or any DDL
- Always use fully qualified table names: catalog.schema.table
- Always include LIMIT {limit} unless the query already has a LIMIT
- If the question cannot be answered with the available schema, output exactly:
  UNABLE_TO_ANSWER: <one sentence explanation>

Available schema:
{schema_context}

User question: {question}"""


def _bedrock_text_to_sql(question: str, schema_context: str) -> ChatResponse:
    """Generate SQL via Claude, validate it, execute via db_service, return result."""
    from services import db_service   # late import to avoid circular dependency

    agent = _get_agent()
    raw_sql = str(agent(_TEXT_TO_SQL_PROMPT.format(
        question=question,
        schema_context=schema_context or "(no schema provided — use best judgement)",
        limit=MAX_ROW_LIMIT,
    ))).strip()

    if raw_sql.startswith("UNABLE_TO_ANSWER"):
        return ChatResponse(
            text=f"I couldn't find data to answer that question. {raw_sql.split(':', 1)[-1].strip()}",
            source="bedrock",
        )

    # Validate before execution — mandatory
    safe_sql = validate_sql(raw_sql)

    # Execute and summarise
    df = db_service._sql_query(safe_sql)
    summary = f"Found {len(df):,} row(s)."
    if len(df) > 0:
        try:
            summary = generate_insight_summary(
                data_description=df.head(10).to_string(index=False),
                context=question,
            )
        except Exception:
            pass   # summary stays as row count — don't fail the whole response

    return ChatResponse(
        text=summary,
        dataframe=df,           # rendered as table/chart in the UI
        sql=safe_sql,           # kept for audit logging only
        conversation_id=None,   # Bedrock fallback is stateless — no multi-turn conv_id
        source="bedrock",
    )


# ── SQL validator (called for ALL LLM-generated SQL) ─────────────────────────
def validate_sql(sql: str) -> str:
    """
    Validate and sanitize any LLM-generated SQL before execution.
    Raises ValueError with a user-safe message if validation fails.
    """
    sql = sql.strip().rstrip(";")
    if ";" in sql:
        raise ValueError("Multi-statement SQL is not allowed.")
    parsed = sqlparse.parse(sql)
    if not parsed:
        raise ValueError("Could not parse the generated SQL.")
    if parsed[0].get_type() != "SELECT":
        raise ValueError("Only SELECT queries are allowed.")
    upper = sql.upper()
    for kw in BLOCKED_SQL_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            raise ValueError(f"Blocked keyword detected: {kw}")
    if not re.search(r"\bLIMIT\b", upper):
        sql = f"{sql} LIMIT {MAX_ROW_LIMIT}"
    return sql


# ── Insight summariser (used by Bedrock fallback) ─────────────────────────────
def generate_insight_summary(data_description: str, context: str) -> str:
    """Ask Claude for a plain-English business insight. Never pass raw PII rows."""
    agent = _get_agent()
    prompt = (
        f"A business user asked: '{context}'\n"
        f"Query results (sample):\n{data_description}\n\n"
        "Write 2-3 bullet-point insights for a non-technical business user. "
        "Be specific with numbers. Do not mention SQL or technical details."
    )
    return str(agent(prompt))


# ── Tier 3: Mock (local dev only) ─────────────────────────────────────────────
def _mock_response(question: str) -> ChatResponse:
    import pandas as pd
    mock_df = pd.DataFrame({
        "category": ["Electronics", "Clothing", "Food", "Tools"],
        "total_sales": [15_000, 8_200, 12_400, 4_300],
    })
    return ChatResponse(
        text=f"[MOCK] Here are simulated results for: '{question}'",
        dataframe=mock_df,
        sql="SELECT category, SUM(amount) AS total_sales FROM main.sales.orders GROUP BY 1 LIMIT 10",
        conversation_id="mock-conv-001",
        source="mock",
    )
```

---

## 3. Gradio Chat UI (calls `chat_with_data` — never Genie or Bedrock directly)

```python
# components/chat_tab.py
import gradio as gr
from services import ai_service, audit_service

def build(conv_id_state: gr.State, schema_context: str = "") -> None:
    """
    Build the Ask Your Data tab inside a gr.Blocks context.
    conv_id_state: gr.State holding the current Genie conversation_id (or None).
    schema_context: pre-loaded string from data/schema.yaml passed at startup.
    """
    import pandas as pd

    gr.Markdown("## Ask Your Data")
    gr.Markdown("Ask questions in plain English. Powered by Genie with Bedrock fallback.")

    chatbot      = gr.Chatbot(label="", height=350, type="messages", render_markdown=True)
    # Data outputs — default hidden until a query returns results
    results_table = gr.DataFrame(label="Query Results", height=300, visible=False)
    msg_box      = gr.Textbox(placeholder="e.g. What were total sales last quarter?",
                              label="Your question", max_lines=3)
    with gr.Row():
        submit_btn = gr.Button("Ask", variant="primary")
        clear_btn  = gr.Button("Clear", variant="secondary")
    source_label = gr.Markdown("")   # shows "Answered by: Genie" or "Answered by: Bedrock"

    def respond(message: str, history: list, conv_id: str | None,
                request: gr.Request) -> tuple:
        if not message.strip() or len(message) > 2000:
            return history, message, conv_id, "", gr.update(visible=False)

        email = request.headers.get("X-Forwarded-Email", "local-dev") if request else "local-dev"

        result = ai_service.chat_with_data(
            question=message,
            conversation_id=conv_id,
            schema_context=schema_context,
        )

        # Reply is explanation text ONLY — never append raw SQL or code to the chat
        reply = result.text if not result.error else \
            "Sorry, I could not answer that question. Please try rephrasing it."

        audit_service.log_event(
            action_type="CHAT",
            query_text=result.sql or message,   # SQL goes to audit log, not the chat window
            user_email=email,
        )

        new_history = history + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": reply},
        ]
        source_md = f"_Answered by: **{result.source.capitalize()}**_"

        # Render data as a table; hide the component if there are no results
        if result.dataframe is not None and len(result.dataframe) > 0:
            table_update = gr.update(value=result.dataframe, visible=True)
        else:
            table_update = gr.update(value=None, visible=False)

        return new_history, "", result.conversation_id, source_md, table_update

    submit_btn.click(fn=respond,
                     inputs=[msg_box, chatbot, conv_id_state],
                     outputs=[chatbot, msg_box, conv_id_state, source_label, results_table])
    msg_box.submit(fn=respond,
                   inputs=[msg_box, chatbot, conv_id_state],
                   outputs=[chatbot, msg_box, conv_id_state, source_label, results_table])
    clear_btn.click(fn=lambda: ([], "", None, "", gr.update(value=None, visible=False)),
                    outputs=[chatbot, msg_box, conv_id_state, source_label, results_table])
```

**Key notes:**
- **Default output is a table + explanation — never raw SQL or code in the chat window.** The SQL is logged to the audit trail silently.
- `results_table` is hidden until a query returns rows; it appears automatically below the chat.
- The `source_label` shows whether the answer came from Genie or the Bedrock fallback — good for demo transparency.
- `conversation_id` is carried forward from Genie responses for multi-turn context; the Bedrock path returns `None` (stateless), so each Bedrock question starts fresh.
- On any error, the response degrades gracefully — the user sees a friendly message, never a stack trace.

---

## 4. Environment Variables

```env
# .env.example — copy to .env and fill in real values; never commit .env

# Databricks connection (required for both tiers)
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=your_personal_access_token
DATABRICKS_WAREHOUSE_ID=your_sql_warehouse_id     # injected by app.yaml in production

# Tier 1 — Genie (optional; Tier 2 used if not set)
GENIE_SPACE_ID=your_genie_space_id                # leave empty to disable Genie

# Tier 2 — Bedrock fallback
BEDROCK_REGION=us-east-1

# Local dev mock (disables all real API calls)
USE_MOCK_AI=false
DEV_USER_EMAIL=you@example.com
```

**Startup assertion** — add to top of `app.py`:
```python
assert os.getenv("DATABRICKS_HOST"),         "DATABRICKS_HOST must be set"
assert os.getenv("DATABRICKS_WAREHOUSE_ID"), "DATABRICKS_WAREHOUSE_ID must be set in app.yaml"
# GENIE_SPACE_ID is optional — absence triggers Bedrock fallback automatically
```

---

## 5. Genie API Constraints & Rate Limits

| Constraint | Value |
|---|---|
| Max rows per Genie query | 5,000 |
| Rate limit | 5 queries/minute per workspace (best-effort) |
| Max conversations per Space | 10,000 |
| Polling method | GET (does NOT count toward rate limit) |
| POST calls that count toward limit | start-conversation, send-message |
| Recommended poll interval | 1s → 2s → 4s → capped at 5s |
| Max wait before Bedrock fallback triggers | 60 seconds |

**Rate limit handling in Gradio** — add a query counter to `gr.State`:
```python
# In app.py, track queries per session
query_count = gr.State(0)

# In respond():
def respond(message, history, conv_id, qcount, request: gr.Request):
    if qcount >= 4:
        warning = "You are approaching the Genie rate limit. Switching to Bedrock for this query."
        result = ai_service.chat_with_data(question=message,
                                           conversation_id=None,   # force Bedrock by clearing conv_id
                                           schema_context=schema_context)
    else:
        result = ai_service.chat_with_data(message, conv_id, schema_context)
    return ..., qcount + 1
```

---

## 6. Prompt Engineering Guidelines

When the AI IDE generates prompt strings for Claude, it must follow these rules:

### Default Response Format (MANDATORY)
- **Never output raw SQL or code blocks to the user.** The generated SQL is for execution and audit logging only.
- **Always return results as a table (`gr.DataFrame`) and/or a plain-English explanation.** Never paste query results as raw text in the chat.
- **Explanation text should be 2–5 sentences** written for a non-technical business user — no SQL syntax, no column names, no technical jargon.
- If the user explicitly asks for code (e.g. "show me the SQL" or "write a script"), respond with: *"This app answers data questions with tables and charts. For raw SQL, please contact your analyst."*
- Suggested chart pairing (auto-detect from DataFrame shape):
  - 2 columns: category + numeric → bar chart
  - Date/time column + numeric → line chart
  - 3+ numeric columns → scatter plot or table

### System Prompt Best Practices
- **Be specific about output format** — tell Claude exactly what to return (SQL only, bullets, JSON)
- **Define boundaries explicitly** — "Only generate SELECT statements", "Do not reveal table names"
- **Provide schema context** — pass column names + types + descriptions; never send full data rows
- **Include a refusal path** — always tell the model what to return if it cannot answer (`UNABLE_TO_ANSWER:`)

### What NOT to Put in Prompts
- Raw PII or sensitive data values
- Connection strings, tokens, or credentials
- More than ~10 rows of sample data (send column metadata instead)

### Response Length Targets
- Text-to-SQL: 1–5 lines; set `max_tokens=500`
- Insight summaries: 50–200 words; set `max_tokens=300`

### Handling Hallucinations
- Always run `validate_sql()` on every LLM-generated SQL before execution
- If the query returns 0 rows, tell the user — do not ask Claude to invent data
- Prefix all AI-generated insight text: *"AI-generated summary — verify with source data"*

---

## 7. Genie Setup Checklist (do this before the hackathon)

Before your app can use Tier 1, a team member must:

1. Log in to your Databricks workspace
2. Navigate to **AI/BI → Genie**
3. Click **Create Genie Space**
4. Add your Unity Catalog tables to the Space
5. Write 3–5 sample questions so Genie learns your domain vocabulary
6. Copy the Space ID from the URL: `…/genie/spaces/<SPACE_ID>`
7. Set `GENIE_SPACE_ID=<SPACE_ID>` in `.env` (local) and `app.yaml` (deployed)
8. Verify with: `curl -X POST $DATABRICKS_HOST/api/2.0/genie/spaces/$GENIE_SPACE_ID/start-conversation -H "Authorization: Bearer $DATABRICKS_TOKEN" -d '{"content": "How many rows are in the sales table?"}'`

If Step 8 returns a `conversation_id`, Genie is working. If not, the app will automatically fall back to Bedrock.
