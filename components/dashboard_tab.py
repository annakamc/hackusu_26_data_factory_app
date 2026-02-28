"""Overview Dashboard tab — KPI cards + summary charts across all asset types."""
import logging

import gradio as gr
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from services import db_service, auth_service, audit_service

logger = logging.getLogger(__name__)

_STATUS_COLORS = {
    "Failure imminent (<20)": "#B71C1C",
    "Critical (20-49)":       "#E53935",
    "Warning (50-125)":       "#FB8C00",
    "Safe (>125)":            "#43A047",
}

_HEATER_COLORS = {
    "B0005": "#60A5FA",
    "B0006": "#F472B6",
    "B0007": "#34D399",
    "B0018": "#FB923C",
}

_FAULT_PALETTE = ["#43A047", "#1976D2", "#E53935", "#FB8C00"]


def _build_health_bar(health_df_sorted: pd.DataFrame, show_threshold: bool) -> go.Figure:
    """Build the heater health score bar chart with optional threshold line."""
    bar_colors = [
        "#43A047" if s >= 98 else "#FB8C00" if s >= 95 else "#E53935"
        for s in health_df_sorted["health_score_pct"]
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=health_df_sorted["PhID"],
        y=health_df_sorted["health_score_pct"],
        marker_color=bar_colors,
        text=[f"{s}%" for s in health_df_sorted["health_score_pct"]],
        textposition="outside",
        textfont=dict(size=13),
        hovertemplate="<b>%{x}</b><br>Health Score: %{y:.1f}%<extra></extra>",
        width=0.5,
        showlegend=False,
    ))

    if show_threshold:
        fig.add_hline(
            y=95, line_dash="dash", line_color="#000000", line_width=1.5,
            annotation_text="Degradation threshold (95%)",
            annotation_font=dict(color="#000000"),
        )

    for color, label in [
        ("#43A047", "Good (≥ 98%)"),
        ("#FB8C00", "Warning (95–98%)"),
        ("#E53935", "Critical (< 95%)"),
    ]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=10, color=color, symbol="square"),
            name=label,
            showlegend=True,
        ))

    fig.update_layout(
        title="Heater Health Score (Recent vs Baseline Voltage)",
        xaxis_title="",
        yaxis_title="Health Score (%)",
        yaxis=dict(range=[85, 102], gridcolor="rgba(148,163,184,0.1)"),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="right", x=1,
            font=dict(size=11),
        ),
        margin=dict(l=50, r=20, t=70, b=40),
        bargap=0.4,
    )
    return fig


def _build_fault_bar(fault_df: pd.DataFrame, selected: list) -> go.Figure:
    """Build the fault type bar chart filtered to selected fault types."""
    filtered = fault_df[fault_df["fault_type"].isin(selected)].sort_values(
        "count", ascending=False
    ).reset_index(drop=True)

    fig = go.Figure()
    for i, row in filtered.iterrows():
        fig.add_trace(go.Bar(
            x=[row["fault_type"]],
            y=[row["count"]],
            name=row["fault_type"],
            marker_color=_FAULT_PALETTE[i % len(_FAULT_PALETTE)],
            text=[row["count"]],
            textposition="outside",
            textfont=dict(size=12),
            hovertemplate=f"<b>{row['fault_type']}</b><br>Count: {row['count']}<extra></extra>",
            width=0.6,
        ))

    fig.update_layout(
        title="Fault Type Distribution",
        xaxis_title="",
        yaxis_title="Number of Events",
        showlegend=False,
        margin=dict(l=50, r=40, t=50, b=120),
        xaxis=dict(tickangle=-30, tickfont=dict(size=11)),
        yaxis=dict(gridcolor="rgba(148,163,184,0.15)"),
        bargap=0.3,
    )
    return fig


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
        # Chart 3: Heater Health Score
        with gr.Column():
            threshold_toggle = gr.Checkbox(
                value=True,
                label="Show Degradation Threshold Line",
            )
            torque_chart = gr.Plot(label="Heater Health Score")

        # Chart 4: Electrical Fault Distribution
        with gr.Column():
            fault_toggle = gr.CheckboxGroup(
                choices=[], value=[],
                label="Show Fault Types",
            )
            type_chart = gr.Plot(label="Fault Type Distribution")

    # State
    health_df_state = gr.State(value=None)
    fault_df_state  = gr.State(value=None)

    # Anomaly alert banner
    gr.Markdown("### ⚠️ Anomaly Alerts (tool wear > 200 min or torque > 65 Nm)")
    anomaly_table = gr.DataFrame(label="At-Risk Assets", height=250)

    # ── Event handlers ─────────────────────────────────────────────────────────
    def load_charts(request: gr.Request):
        user  = auth_service.get_user_from_request(request)
        email = user["email"] if user else "unknown"
        role  = user["role"]  if user else "viewer"

        try:
            # --- Chart 1: Failure modes bar chart ---
            fm_df = db_service.get_cnc_failure_modes()
            fm_df = fm_df.sort_values("count", ascending=True).reset_index(drop=True)
            fm_df["failure_mode"] = fm_df["failure_mode"].str.replace(r"\s*\([A-Z]+\)\s*$", "", regex=True)
            fm_fig = px.bar(
                fm_df, x="count", y="failure_mode",
                orientation="h",
                color="count", color_continuous_scale="Reds",
                title="CNC Failure Mode Breakdown",
                labels={"failure_mode": "Failure Mode", "count": "Incidents"},
            )
            n_bars = len(fm_df)
            first_color  = "#FCBEAC"
            second_color = "#FCB59D"
            rest_colors  = ["#FB6A4A", "#DE2D26", "#A50F15"][:max(0, n_bars - 2)]
            fm_fig.update_traces(marker_color=[first_color, second_color] + rest_colors)
            fm_fig.update_layout(coloraxis_showscale=False, showlegend=False)

            # --- Chart 2: RUL health buckets ---
            rul_df  = db_service.get_engine_rul_buckets()
            rul_df  = rul_df.sort_values("count", ascending=True).reset_index(drop=True)
            rul_fig = px.bar(
                rul_df, x="bucket", y="count",
                color="bucket",
                color_discrete_map=_STATUS_COLORS,
                title="Engine Health Distribution",
                labels={"bucket": "Health Status", "count": "Engines"},
            )
            rul_fig.update_layout(showlegend=False)

            # --- Chart 3: Heater Health Score ---
            heater_df = db_service._sql_query("""
                SELECT PhID, id_cycle,
                       ROUND(AVG(Voltage_measured), 4) AS avg_voltage
                FROM dataknobs_predictive_maintenance_and_asset_management.datasets.heater_validation_data
                GROUP BY PhID, id_cycle
                ORDER BY PhID, id_cycle
            """)
            health_rows = []
            for phid, grp in heater_df.groupby("PhID"):
                grp_s    = grp.sort_values("id_cycle")
                baseline = grp_s.head(10)["avg_voltage"].mean()
                recent   = grp_s.tail(10)["avg_voltage"].mean()
                score    = round((recent / baseline) * 100, 1) if baseline > 0 else 0
                health_rows.append({"PhID": phid, "health_score_pct": score})
            health_df_sorted = (
                pd.DataFrame(health_rows)
                .sort_values("health_score_pct", ascending=False)
                .reset_index(drop=True)
            )
            heater_health_fig = _build_health_bar(health_df_sorted, show_threshold=True)

            # --- Chart 4: Electrical Fault Distribution ---
            fault_df   = db_service.get_electrical_fault_summary()
            fault_df   = fault_df.sort_values("count", ascending=False).reset_index(drop=True)
            all_faults = fault_df["fault_type"].tolist()
            fault_fig  = _build_fault_bar(fault_df, all_faults)

            # --- Anomaly table ---
            anom_df = db_service.get_cnc_anomalies(limit=30)

            audit_service.log_event(
                action_type="QUERY",
                user_email=email, user_role=role,
                source_tables=f"{db_service.CNC_TABLE}, {db_service.ENGINE_TABLE}",
                query_text="Dashboard overview load",
                row_count=len(anom_df),
            )

            return (
                fm_fig, rul_fig, heater_health_fig, fault_fig, anom_df, "",
                health_df_sorted,                                          # → health_df_state
                fault_df,                                                  # → fault_df_state
                gr.CheckboxGroup(choices=all_faults, value=all_faults),   # → fault_toggle
            )

        except Exception as exc:
            logger.error("Dashboard load_charts error: %s", exc)
            empty = go.Figure()
            empty.update_layout(title="Data unavailable")
            return (
                empty, empty, empty, empty, gr.update(),
                f"⚠️ {str(exc)[:120]}",
                None, None, gr.update(),
            )

    def redraw_health_bar(show_threshold, raw_health_df):
        if raw_health_df is None:
            return go.Figure()
        df = pd.DataFrame(raw_health_df) if isinstance(raw_health_df, list) else raw_health_df
        return _build_health_bar(df, show_threshold)

    def redraw_fault_chart(selected, raw_df):
        if raw_df is None or not selected:
            return go.Figure()
        df = pd.DataFrame(raw_df) if isinstance(raw_df, list) else raw_df
        return _build_fault_bar(df, selected)

    outputs = [
        failure_modes_chart, rul_buckets_chart, torque_chart,
        type_chart, anomaly_table, status_msg,
        health_df_state, fault_df_state, fault_toggle,
    ]

    refresh_btn.click(fn=load_charts, outputs=outputs)

    threshold_toggle.change(
        fn=redraw_health_bar,
        inputs=[threshold_toggle, health_df_state],
        outputs=[torque_chart],
    )

    fault_toggle.change(
        fn=redraw_fault_chart,
        inputs=[fault_toggle, fault_df_state],
        outputs=[type_chart],
    )

    # Return (outputs, load_fn) so app.py can wire demo.load()
    return outputs, load_charts