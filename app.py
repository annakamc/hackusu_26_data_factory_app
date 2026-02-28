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

# ── App layout ─────────────────────────────────────────────────────────────────
_CSS = """
footer {visibility: hidden}
.kpi-value { font-size: 2rem; font-weight: 700; }
/* Fixed bottom-left chat toggle button — visible on every tab */
#chat-toggle-btn { position: fixed; bottom: 20px; left: 20px; z-index: 1000; }
#chat-side-panel { max-width: 420px; }
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
        # Main content: tabs only (no "Ask Your Data" tab)
        with gr.Column(scale=12):
            with gr.Tabs():
                with gr.Tab("Overview"):
                    dashboard_outputs, dashboard_load_fn = dashboard_tab.build(summary)

                with gr.Tab("CNC Analysis"):
                    cnc_tab.build()

                with gr.Tab("Engine Health"):
                    engine_tab.build()

                with gr.Tab("Electrical Monitor"):
                    electrical_tab.build()

                with gr.Tab("Audit Log"):
                    audit_tab.build()

                with gr.Tab("Admin"):
                    admin_tab.build()

        # Side panel: chat UI (hidden by default, toggled by button)
        with gr.Column(scale=4, visible=False, elem_id="chat-side-panel") as chat_panel:
            chat_tab.build(conv_id_state, schema_ctx)

    # Toggle button: fixed bottom-left, opens/closes chat panel
    toggle_btn = gr.Button("Chat", variant="secondary", elem_id="chat-toggle-btn")

    def toggle_panel(visible):
        return not visible, gr.update(visible=not visible)

    toggle_btn.click(
        fn=toggle_panel,
        inputs=[panel_visible],
        outputs=[panel_visible, chat_panel],
    )

    # Auto-load Overview charts when page first opens
    demo.load(fn=dashboard_load_fn, outputs=dashboard_outputs)


if __name__ == "__main__":
    print("Starting Gradio server... (wait for 'Running on local URL' before opening the browser)")
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", 7860)),
        show_error=True,
        share=False,
    )
