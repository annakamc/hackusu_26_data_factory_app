"""Heater Health tab — voltage degradation and thermal analysis across charge cycles."""
import logging

import gradio as gr
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from services import db_service, auth_service, audit_service

logger = logging.getLogger(__name__)

_HEATER_COLORS = {
    "B0005": "#60A5FA",  # blue
    "B0006": "#F472B6",  # pink
    "B0007": "#34D399",  # green
    "B0018": "#FB923C",  # orange
}


def _build_voltage_trend(df: pd.DataFrame, selected: list) -> go.Figure:
    """Build voltage degradation chart filtered to selected heaters."""
    fig = go.Figure()

    for phid, grp in df.groupby("PhID"):
        if phid not in selected:
            continue
        grp_s = grp.sort_values("id_cycle")
        fig.add_trace(go.Scatter(
            x=grp_s["id_cycle"],
            y=grp_s["avg_voltage"],
            mode="lines",
            name=phid,
            line=dict(color=_HEATER_COLORS.get(phid, "#94A3B8"), width=2),
            hovertemplate=(
                f"<b>{phid}</b><br>"
                "Cycle: %{x}<br>"
                "Avg Voltage: %{y:.4f} V<extra></extra>"
            ),
        ))

    # Fleet average across selected heaters only
    filtered = df[df["PhID"].isin(selected)]
    if len(filtered) > 0:
        fleet_avg = filtered.groupby("id_cycle")["avg_voltage"].mean().reset_index()
        fig.add_trace(go.Scatter(
            x=fleet_avg["id_cycle"],
            y=fleet_avg["avg_voltage"],
            mode="lines",
            name="Fleet Average",
            line=dict(color="white", width=1.5, dash="dot"),
            opacity=0.5,
            hovertemplate="Fleet Avg — Cycle: %{x}<br>Voltage: %{y:.4f} V<extra></extra>",
        ))

    fig.update_layout(
        title="Voltage Degradation Over Cycles",
        xaxis_title="Cycle",
        yaxis_title="Avg Voltage (V)",
        legend=dict(orientation="h", yanchor="top", y=-0.2, font=dict(size=10)),
        hovermode="x unified",
        margin=dict(l=50, r=20, t=50, b=80),
        xaxis=dict(gridcolor="rgba(148,163,184,0.1)"),
        yaxis=dict(gridcolor="rgba(148,163,184,0.1)"),
    )
    return fig


def _build_health_bar(health_df_sorted: pd.DataFrame, show_threshold: bool) -> go.Figure:
    """Build the health score bar chart with optional threshold line."""
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
    ))

    if show_threshold:
        fig.add_hline(
            y=95, line_dash="dash", line_color="#000000", line_width=1.5,
            annotation_text="Degradation threshold (95%)",
            annotation_font=dict(color="#000000"),
        )

    # Invisible scatter traces just for the legend
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


def build() -> None:
    """Build the Heater Health tab inside a gr.Blocks context."""

    gr.Markdown("## Heater Health Analysis")
    gr.Markdown(
        "Voltage degradation and thermal monitoring across charge cycles.  \n"
        "_Source: `main.predictive_maintenance.heater_readings`_"
    )

    with gr.Row():
        load_btn = gr.Button("Load Heater Data", variant="primary")
        status   = gr.Markdown("")

    # ── KPI row ────────────────────────────────────────────────────────────────
    with gr.Row():
        kpi_avg_voltage   = gr.Markdown("### Fleet Avg Voltage\n# **—V**")
        kpi_avg_temp      = gr.Markdown("### Fleet Avg Temp\n# **—°C**")
        kpi_total_cycles  = gr.Markdown("### Total Cycles\n# **—**")
        kpi_most_degraded = gr.Markdown("### Most Degraded\n# **—**")

    # State
    trend_df_state  = gr.State(value=None)
    health_df_state = gr.State(value=None)

    # ── Charts ─────────────────────────────────────────────────────────────────
    with gr.Row():
        with gr.Column():
            heater_toggle = gr.CheckboxGroup(
                choices=[], value=[],
                label="Show Heaters",
            )
            voltage_trend = gr.Plot(label="Voltage Degradation Over Cycles (per heater)")
        with gr.Column():
            threshold_toggle = gr.Checkbox(
                value=True,
                label="Show Degradation Threshold Line",
            )
            health_bar = gr.Plot(label="Heater Health Score — Current vs Baseline Voltage")

    with gr.Row():
        temp_voltage   = gr.Plot(label="Temperature vs Voltage (degradation relationship)")
        discharge_plot = gr.Plot(label="Discharge Time Distribution per Heater")

    gr.Markdown("### Heater Summary Table")
    heater_table = gr.DataFrame(label="Per-heater stats — avg voltage, temp, cycles", height=250)

    # ── Degradation accordion ──────────────────────────────────────────────────
    with gr.Accordion("Degradation Detail", open=False):
        gr.Markdown(
            "Health score is derived from voltage: each heater's average voltage over its "
            "most recent 10 cycles compared to its first 10 cycles. "
            "A score below 95% indicates measurable degradation."
        )
        degradation_tbl = gr.DataFrame(label="Cycle-by-cycle voltage averages", height=300)

    # ── Event handlers ─────────────────────────────────────────────────────────
    def load_data(request: gr.Request):
        user  = auth_service.get_user_from_request(request)
        email = user["email"] if user else "unknown"
        role  = user["role"]  if user else "viewer"

        try:
            df = db_service._sql_query("""
                SELECT PhID, id_cycle, Time,
                       ROUND(AVG(Voltage_measured), 4)     AS avg_voltage,
                       ROUND(AVG(Temperature_measured), 4) AS avg_temp,
                       ROUND(AVG(Current_measured), 4)     AS avg_current,
                       ROUND(AVG(Voltage_charge), 4)       AS avg_voltage_charge,
                       COUNT(*)                            AS readings
                FROM dataknobs_predictive_maintenance_and_asset_management.datasets.heater_validation_data
                GROUP BY PhID, id_cycle, Time
                ORDER BY PhID, id_cycle
            """)

            # ── KPIs ──────────────────────────────────────────────────────────
            avg_v    = round(df["avg_voltage"].mean(), 3)
            avg_t    = round(df["avg_temp"].mean(), 2)
            n_cycles = df["id_cycle"].nunique()

            # Health score per heater: last 10 cycles vs first 10 cycles
            health_rows = []
            for phid, grp in df.groupby("PhID"):
                grp_s    = grp.sort_values("id_cycle")
                baseline = grp_s.head(10)["avg_voltage"].mean()
                recent   = grp_s.tail(10)["avg_voltage"].mean()
                score    = round((recent / baseline) * 100, 1) if baseline > 0 else 0
                health_rows.append({
                    "PhID": phid,
                    "baseline_voltage": round(baseline, 4),
                    "recent_voltage":   round(recent, 4),
                    "health_score_pct": score,
                })
            health_df     = pd.DataFrame(health_rows).sort_values("health_score_pct")
            most_degraded = health_df.iloc[0]["PhID"]

            # ── Chart 1: Voltage degradation ──────────────────────────────────
            all_heaters = sorted(df["PhID"].unique().tolist())
            volt_fig    = _build_voltage_trend(df, all_heaters)

            # ── Chart 2: Health score bar (threshold on by default) ────────────
            health_df_sorted = health_df.sort_values("health_score_pct", ascending=False)
            health_fig       = _build_health_bar(health_df_sorted, show_threshold=True)

            # ── Chart 3: Temperature vs Voltage scatter ────────────────────────
            temp_fig = go.Figure()
            for phid, grp in df.groupby("PhID"):
                temp_fig.add_trace(go.Scatter(
                    x=grp["avg_voltage"],
                    y=grp["avg_temp"],
                    mode="markers",
                    name=phid,
                    marker=dict(
                        color=_HEATER_COLORS.get(phid, "#94A3B8"),
                        size=5, opacity=0.55,
                    ),
                    hovertemplate=(
                        f"<b>{phid}</b><br>"
                        "Voltage: %{x:.4f} V<br>"
                        "Temp: %{y:.2f} °C<extra></extra>"
                    ),
                ))
            temp_fig.update_layout(
                title="Temperature vs Voltage — Degradation Relationship",
                xaxis_title="Avg Voltage (V)",
                yaxis_title="Avg Temperature (°C)",
                legend=dict(orientation="h", yanchor="top", y=-0.2, font=dict(size=10)),
                hovermode="closest",
                margin=dict(l=50, r=20, t=50, b=80),
                xaxis=dict(gridcolor="rgba(148,163,184,0.1)"),
                yaxis=dict(gridcolor="rgba(148,163,184,0.1)"),
            )

            # ── Chart 4: Discharge time box plot ──────────────────────────────
            discharge_fig = go.Figure()
            for phid, grp in df.groupby("PhID"):
                discharge_fig.add_trace(go.Box(
                    y=grp["Time"],
                    name=phid,
                    marker_color=_HEATER_COLORS.get(phid, "#94A3B8"),
                    boxmean=True,
                    hovertemplate=f"<b>{phid}</b><br>Time: %{{y:.1f}}s<extra></extra>",
                ))
            discharge_fig.update_layout(
                title="Discharge Time Distribution per Heater",
                xaxis_title="",
                yaxis_title="Discharge Time (s)",
                showlegend=False,
                margin=dict(l=50, r=20, t=50, b=40),
                yaxis=dict(gridcolor="rgba(148,163,184,0.1)"),
            )

            # ── Summary table ──────────────────────────────────────────────────
            summary_df = df.groupby("PhID").agg(
                avg_voltage=("avg_voltage", "mean"),
                avg_temp=("avg_temp", "mean"),
                avg_current=("avg_current", "mean"),
                total_cycles=("id_cycle", "nunique"),
                avg_discharge_time=("Time", "mean"),
            ).round(3).reset_index()
            summary_df.columns = [
                "Heater ID", "Avg Voltage (V)", "Avg Temp (°C)",
                "Avg Current (A)", "Total Cycles", "Avg Discharge Time (s)",
            ]

            # ── Degradation detail table ───────────────────────────────────────
            deg_df = df.groupby(["PhID", "id_cycle"])["avg_voltage"].mean().round(4).reset_index()
            deg_df.columns = ["Heater ID", "Cycle", "Avg Voltage (V)"]

            audit_service.log_event(
                action_type="QUERY",
                user_email=email, user_role=role,
                source_tables="dataknobs_predictive_maintenance_and_asset_management.datasets.heater_validation_data",
                query_text="Heater health tab load",
                row_count=len(df),
            )

            return (
                volt_fig, health_fig, temp_fig, discharge_fig,
                summary_df, deg_df,
                f"### Fleet Avg Voltage\n# **{avg_v} V**",
                f"### Fleet Avg Temp\n# **{avg_t} °C**",
                f"### Total Cycles\n# **{n_cycles}**",
                f"### Most Degraded\n# **{most_degraded}**",
                "",
                df,                                                         # → trend_df_state
                health_df_sorted,                                           # → health_df_state
                gr.CheckboxGroup(choices=all_heaters, value=all_heaters),  # → heater_toggle
            )

        except Exception as exc:
            logger.error("Heater tab load error: %s", exc)
            empty = go.Figure()
            return (
                empty, empty, empty, empty,
                gr.update(), gr.update(),
                "### Fleet Avg Voltage\n# **—V**",
                "### Fleet Avg Temp\n# **—°C**",
                "### Total Cycles\n# **—**",
                "### Most Degraded\n# **—**",
                f"⚠️ {str(exc)[:120]}",
                None, None, gr.update(),
            )

    def redraw_voltage_trend(selected, raw_df):
        if raw_df is None or not selected:
            return go.Figure()
        df = pd.DataFrame(raw_df) if isinstance(raw_df, list) else raw_df
        return _build_voltage_trend(df, selected)

    def redraw_health_bar(show_threshold, raw_health_df):
        if raw_health_df is None:
            return go.Figure()
        df = pd.DataFrame(raw_health_df) if isinstance(raw_health_df, list) else raw_health_df
        return _build_health_bar(df, show_threshold)

    # ── Wire load button ───────────────────────────────────────────────────────
    load_btn.click(
        fn=load_data,
        outputs=[
            voltage_trend, health_bar, temp_voltage, discharge_plot,
            heater_table, degradation_tbl,
            kpi_avg_voltage, kpi_avg_temp, kpi_total_cycles, kpi_most_degraded,
            status, trend_df_state, health_df_state, heater_toggle,
        ],
    )

    # ── Wire toggles ───────────────────────────────────────────────────────────
    heater_toggle.change(
        fn=redraw_voltage_trend,
        inputs=[heater_toggle, trend_df_state],
        outputs=[voltage_trend],
    )

    threshold_toggle.change(
        fn=redraw_health_bar,
        inputs=[threshold_toggle, health_df_state],
        outputs=[health_bar],
    )