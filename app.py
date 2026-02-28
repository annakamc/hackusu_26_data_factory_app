"""
Predictive Maintenance Intelligence Hub
Databricks Data App Factory — HackUSU 2026

Entry point. Run with:
    python app.py                      # local dev (SQLite mock)
    databricks apps deploy             # Databricks Apps

Local dev setup:
    1. python database/setup_db.py     # generate synthetic SQLite data
    2. cp .env.example .env && edit    # fill DATABRICKS_HOST etc. OR leave blank for mock
    3. python app.py
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# Create logs directory on first run
Path("logs").mkdir(exist_ok=True)

# ── Startup assertions ─────────────────────────────────────────────────────────
# Databricks is optional; absence → SQLite local mock
if os.getenv("DATABRICKS_WAREHOUSE_ID"):
    assert os.getenv("DATABRICKS_HOST"), "DATABRICKS_HOST must be set when using Databricks."
    logger.info("Mode: Databricks SQL Warehouse (%s)", os.getenv("DATABRICKS_HOST"))
else:
    logger.info("Mode: SQLite local mock (set DATABRICKS_WAREHOUSE_ID to use Databricks)")

# ── Load services and startup data ────────────────────────────────────────────
import yaml
import gradio as gr
from services import db_service, auth_service
from components import (
    dashboard_tab,
    cnc_tab,
    engine_tab,
    electrical_tab,
    chat_tab,
    audit_tab,
    admin_tab,
    request_access_tab,
)

# Workaround: Gradio 4.44.x / gradio_client crash when API schema has a boolean
# (TypeError: argument of type 'bool' is not iterable in get_type()). Patch before UI is served.
try:
    import gradio_client.utils as _gc_utils
    _get_type_orig = _gc_utils.get_type
    def _get_type_patched(schema):
        if isinstance(schema, bool):
            return "boolean"
        return _get_type_orig(schema)
    _gc_utils.get_type = _get_type_patched
except Exception:
    pass

try:
    summary = db_service.get_summary_kpis()
    logger.info("Startup KPIs loaded: %s", summary)
except Exception as exc:
    logger.warning("Could not load startup KPIs: %s", exc)
    summary = {}

try:
    schema_ctx = db_service.get_schema_context()
except Exception:
    schema_ctx = ""

_ROLES_PATH = Path("governance") / "roles.yaml"

# Tab names that map to role config in roles.yaml
_TAB_NAMES = ["Overview", "CNC Analysis", "Engine Health", "Electrical Monitor", "Audit Log", "Admin"]

# ── App layout ─────────────────────────────────────────────────────────────────
_CSS = """
footer {visibility: hidden}
.kpi-value { font-size: 2rem; font-weight: 700; }
/* Fixed bottom-right circular chat toggle button */
#chat-toggle-btn {
  position: fixed !important;
  bottom: 24px !important;
  right: 24px !important;
  left: auto !important;
  z-index: 1000;
  width: 56px !important;
  height: 56px !important;
  min-width: 56px !important;
  border-radius: 50% !important;
  padding: 0 !important;
  font-size: 1.5rem;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
  color: white !important;
  border: none !important;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
}
#chat-toggle-btn:hover,
#chat-toggle-btn button:hover {
  background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%) !important;
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5);
}
#chat-toggle-btn button {
  width: 56px !important;
  height: 56px !important;
  min-width: 56px !important;
  border-radius: 50% !important;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
  color: white !important;
}
#chat-side-panel { max-width: 420px; }
/* No gap between chat buttons and Answered by: Genie */
#chat-buttons-row { margin-bottom: 0 !important; }
#chat-source-label { margin-top: 0 !important; padding-top: 0 !important; }
/* No gap between chat panel and Example questions */
#chat-panel-column { margin-bottom: 0 !important; padding-bottom: 0 !important; }
#example-questions-section { margin-top: 0 !important; padding-top: 0 !important; }
"""

with gr.Blocks(css=_CSS, title="Predictive Maintenance Hub") as demo:

    # Per-session state
    conv_id_state = gr.State(None)       # Genie conversation ID
    panel_visible = gr.State(False)      # Side panel open/closed

    gr.Markdown(
        "# Predictive Maintenance Intelligence Hub\n"
        "_Powered by Databricks Unity Catalog · AI/BI Genie · Bedrock_"
    )

    with gr.Row():
        # Main content: tabs
        with gr.Column(scale=12):
            with gr.Tabs():
                with gr.Tab("Overview", visible=False) as tab_overview:
                    dashboard_outputs, dashboard_load_fn = dashboard_tab.build(summary)

                with gr.Tab("CNC Analysis", visible=False) as tab_cnc:
                    cnc_tab.build()

                with gr.Tab("Engine Health", visible=False) as tab_engine:
                    engine_tab.build()

                with gr.Tab("Electrical Monitor", visible=False) as tab_electrical:
                    electrical_tab.build()

                with gr.Tab("Audit Log", visible=False) as tab_audit:
                    audit_tab.build()

                with gr.Tab("Admin", visible=False) as tab_admin:
                    admin_tab.build()

                with gr.Tab("Request Access", visible=False) as tab_request:
                    request_access_outputs, request_access_load_fn = request_access_tab.build()

        # Side panel: chat UI (hidden by default, toggled by button)
        with gr.Column(scale=4, visible=False, elem_id="chat-side-panel") as chat_panel:
            chat_tab.build(conv_id_state, schema_ctx)

    # Toggle button: fixed bottom-right, circular message icon, opens/closes chat panel
    toggle_btn = gr.Button("💬", variant="secondary", elem_id="chat-toggle-btn")

    def toggle_panel(visible):
        return not visible, gr.update(visible=not visible)

    toggle_btn.click(
        fn=toggle_panel,
        inputs=[panel_visible],
        outputs=[panel_visible, chat_panel],
    )

    # ── Role-based tab visibility + initial data load ──────────────────────────
    _regular_tabs = [tab_overview, tab_cnc, tab_engine, tab_electrical, tab_audit, tab_admin]

    def on_page_load(request: gr.Request):
        user = auth_service.get_user_from_request(request)
        role = user["role"] if user else "no_access"

        try:
            with open(_ROLES_PATH) as f:
                config = yaml.safe_load(f)
            role_cfg = config.get("roles", {}).get(role, config["roles"].get("no_access", {}))
            allowed = role_cfg.get("tabs", [])
        except Exception:
            allowed = []

        if role == "no_access":
            # Hide all regular tabs, show only Request Access
            tab_updates = [gr.update(visible=False)] * len(_regular_tabs)
            tab_updates.append(gr.update(visible=True))   # tab_request
            # No dashboard data to load; return empty placeholders
            empty_dashboard = [gr.update()] * len(dashboard_outputs)
            request_updates = list(request_access_load_fn(request))
            return tab_updates + empty_dashboard + request_updates
        else:
            # Show permitted regular tabs, hide Request Access
            def _vis(name):
                if isinstance(allowed, str) and allowed == "all":
                    return gr.update(visible=True)
                return gr.update(visible=name in allowed)

            tab_updates = [_vis(name) for name in _TAB_NAMES]
            tab_updates.append(gr.update(visible=False))  # tab_request

            # Load dashboard charts
            dashboard_updates = list(dashboard_load_fn(request))
            # No user_display to update for request access tab
            request_updates = [gr.update()] * len(request_access_outputs)
            return tab_updates + dashboard_updates + request_updates

    all_tab_refs = _regular_tabs + [tab_request]
    demo.load(
        fn=on_page_load,
        outputs=all_tab_refs + dashboard_outputs + request_access_outputs,
    )


if __name__ == "__main__":
    print("Starting Gradio server... (wait for 'Running on local URL' before opening the browser)")
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", 7861)),
        show_error=True,
        share=False,
    )
