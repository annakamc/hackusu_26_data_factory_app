"""Overview Dashboard tab — KPI cards + summary charts across all asset types."""
import logging

import numpy as np
import gradio as gr
import plotly.express as px
import plotly.graph_objects as go

from services import db_service, auth_service, audit_service

logger = logging.getLogger(__name__)

_STATUS_COLORS = {
    "Failure imminent (<20)": "#B71C1C",
    "Critical (20-49)":       "#E53935",
    "Warning (50-125)":       "#FB8C00",
    "Safe (>125)":            "#43A047",
}


def _convex_hull_2d(points: np.ndarray) -> np.ndarray:
    """Return vertices of the 2D convex hull (Graham scan). points shape (n, 2)."""
    if len(points) < 3:
        return points
    pts = np.array(points, dtype=float)
    # Start with lowest y, then leftmost
    idx = np.lexsort((pts[:, 0], pts[:, 1]))
    start = idx[0]
    start_pt = pts[start]
    # Cross product: (a - o) x (b - o)
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    # Sort by angle from start (excluding start)
    others = np.array([i for i in range(len(pts)) if i != start])
    angles = np.arctan2(pts[others, 1] - start_pt[1], pts[others, 0] - start_pt[0])
    others = others[np.argsort(angles)]
    hull = [start]
    for i in others:
        while len(hull) >= 2 and cross(pts[hull[-2]], pts[hull[-1]], pts[i]) <= 0:
            hull.pop()
        hull.append(i)
    return pts[hull]


def build(summary: dict) -> list:
    """
    Build the Overview tab inside a gr.Blocks context.
    Returns list of chart components that app.py wires to demo.load().
    """
    # ── KPI Row ────────────────────────────────────────────────────────────────
    gr.Markdown("## Asset Health Overview")
    gr.Markdown(
        "_Source: `dataknobs_predictive_maintenance_and_asset_management.datasets.*` · Unity Catalog · "
        "Predictive Maintenance & Asset Management (Dataknobs)_"
    )

    with gr.Row():
        with gr.Column(scale=1, min_width=150):
            gr.Markdown("### Equipment Health")
            health_kpi = gr.Markdown(
                f"# **{summary.get('health_score', '--')}%**",
                elem_id="kpi-health",
            )
        with gr.Column(scale=1, min_width=150):
            gr.Markdown("### Avg Tool Wear")
            wear_kpi = gr.Markdown(
                f"# **{summary.get('avg_tool_wear', '--')} min**",
                elem_id="kpi-wear",
            )
        with gr.Column(scale=1, min_width=150):
            gr.Markdown("### Avg Engine RUL")
            rul_kpi = gr.Markdown(
                f"# **{summary.get('avg_rul', '--')} cycles**",
                elem_id="kpi-rul",
            )
        with gr.Column(scale=1, min_width=150):
            gr.Markdown("### Critical Engines")
            crit_kpi = gr.Markdown(
                f"# **{summary.get('critical_engines', '--')}**",
                elem_id="kpi-crit",
            )
        with gr.Column(scale=1, min_width=150):
            gr.Markdown("### Total CNC Failures")
            fail_kpi = gr.Markdown(
                f"# **{summary.get('total_failures', '--')}**",
                elem_id="kpi-fail",
            )
        with gr.Column(scale=1, min_width=150):
            gr.Markdown("### Electrical Fault Rate")
            elec_kpi = gr.Markdown(
                f"# **{summary.get('elec_fault_rate', '--')}%**",
                elem_id="kpi-elec",
            )

    with gr.Row():
        refresh_btn = gr.Button("Refresh Charts", variant="secondary", size="sm")
        status_msg  = gr.Markdown("")

    # ── Charts ─────────────────────────────────────────────────────────────────
    with gr.Row():
        failure_modes_chart = gr.Plot(label="CNC Failure Mode Breakdown")
        rul_buckets_chart   = gr.Plot(label="Engine Health Distribution")

    with gr.Row():
        torque_chart  = gr.Plot(label="Torque vs RPM (coloured by failure)")
        type_chart    = gr.Plot(label="Tool Wear vs Torque (coloured by failure)")

    # Anomaly alert banner
    gr.Markdown("### ⚠️ Anomaly Alerts (tool wear > 200 min or torque > 65 Nm)")
    anomaly_table = gr.DataFrame(label="At-Risk Assets", height=250)

    # ── Event handlers ─────────────────────────────────────────────────────────
    def load_charts(request: gr.Request):
        user  = auth_service.get_user_from_request(request)
        email = user["email"] if user else "unknown"
        role  = user["role"]  if user else "viewer"

        try:
            # --- Failure modes bar chart ---
            fm_df  = db_service.get_cnc_failure_modes()
            fm_df = fm_df.sort_values("count", ascending=True).reset_index(drop=True)
            fm_df["failure_mode"] = fm_df["failure_mode"].str.replace(r"\s*\([A-Z]+\)\s*$", "", regex=True)
            fm_fig = px.bar(
                fm_df, x="count", y="failure_mode",
                orientation="h",
                color="count", color_continuous_scale="Reds",
                title="CNC Failure Mode Breakdown",
                labels={"failure_mode": "Failure Mode", "count": "Incidents"},
            )
            # First bar (least incidents) slightly darker but barely lighter than second
            n_bars = len(fm_df)
            first_color = "#FCBEAC"   # barely lighter than second
            second_color = "#FCB59D"
            rest_colors = ["#FB6A4A", "#DE2D26", "#A50F15"][: max(0, n_bars - 2)]
            fm_fig.update_traces(
                marker_color=[first_color, second_color] + rest_colors
            )
            fm_fig.update_layout(coloraxis_showscale=False, showlegend=False)

            # --- RUL health buckets: vertical bar chart (ascending), same colors/classes ---
            rul_df  = db_service.get_engine_rul_buckets()
            rul_df = rul_df.sort_values("count", ascending=True).reset_index(drop=True)
            rul_fig = px.bar(
                rul_df, x="bucket", y="count",
                color="bucket",
                color_discrete_map=_STATUS_COLORS,
                title="Engine Health Distribution",
                labels={"bucket": "Health Status", "count": "Engines"},
            )
            rul_fig.update_layout(showlegend=False)

            # --- Torque vs RPM scatter ---
            sc_df    = db_service.get_cnc_scatter_data(limit=2000)
            tor_fig  = px.scatter(
                sc_df, x="rpm", y="torque_nm",
                color="failure_label",
                color_discrete_map={"Normal": "#43A047", "Failure": "#E53935"},
                opacity=0.6,
                title="Torque vs RPM",
                labels={"rpm": "Rotational Speed (RPM)", "torque_nm": "Torque (Nm)",
                        "failure_label": "Status"},
            )

            # --- Tool Wear vs Torque coloured by failure (failure zone) ---
            typ_fig = px.scatter(
                sc_df, x="tool_wear_min", y="torque_nm",
                color="failure_label",
                color_discrete_map={"Normal": "#43A047", "Failure": "#E53935"},
                opacity=0.6,
                title="Tool Wear vs Torque (coloured by failure)",
                labels={
                    "tool_wear_min": "Tool Wear (min)",
                    "torque_nm": "Torque (Nm)",
                    "failure_label": "Status",
                },
            )
            # Shaded pool around failure points (convex hull, red-tinted fill)
            fail_df = sc_df[sc_df["failure_label"] == "Failure"]
            if not fail_df.empty and len(fail_df) >= 2:
                pts = fail_df[["tool_wear_min", "torque_nm"]].to_numpy()
                if len(pts) >= 3:
                    hull = _convex_hull_2d(pts)
                    # Close the polygon
                    hull = np.vstack([hull, hull[0:1]])
                else:
                    hull = np.vstack([pts, pts[0:1]])
                hull_trace = go.Scatter(
                    x=hull[:, 0],
                    y=hull[:, 1],
                    fill="toself",
                    mode="lines",
                    line=dict(width=0),
                    fillcolor="rgba(229, 57, 53, 0.6)",
                    showlegend=False,
                    hoverinfo="skip",
                )
                typ_fig.add_trace(hull_trace)
                # Draw hull behind the scatter points
                typ_fig.data = [typ_fig.data[-1]] + list(typ_fig.data[:-1])
            typ_fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02))

            # --- Anomaly table ---
            anom_df = db_service.get_cnc_anomalies(limit=30)

            audit_service.log_event(
                action_type="QUERY",
                user_email=email, user_role=role,
                source_tables=f"{db_service.CNC_TABLE}, {db_service.ENGINE_TABLE}",
                query_text="Dashboard overview load",
                row_count=len(sc_df),
            )

            return fm_fig, rul_fig, tor_fig, typ_fig, anom_df, ""

        except Exception as exc:
            logger.error("Dashboard load_charts error: %s", exc)
            empty = go.Figure()
            empty.update_layout(title="Data unavailable")
            return empty, empty, empty, empty, gr.update(), f"⚠️ {str(exc)[:120]}"

    outputs = [failure_modes_chart, rul_buckets_chart, torque_chart,
               type_chart, anomaly_table, status_msg]
    refresh_btn.click(fn=load_charts, outputs=outputs)

    # Return (outputs, load_fn) so app.py can wire demo.load()
    return outputs, load_charts
