"""Engine Health tab — NASA turbofan RUL tracking with maintenance schedule predictor."""
import logging
from datetime import date, timedelta

import gradio as gr
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from services import db_service, auth_service, audit_service

logger = logging.getLogger(__name__)

_STATUS_COLOR = {"Critical": "#E53935", "Warning": "#FB8C00", "Healthy": "#43A047"}

VARYING_SENSORS = [
    "SensorMeasure2", "SensorMeasure3", "SensorMeasure4", "SensorMeasure7",
    "SensorMeasure9", "SensorMeasure11", "SensorMeasure12", "SensorMeasure14",
    "SensorMeasure15", "SensorMeasure17", "SensorMeasure20", "SensorMeasure21",
]


ENGINE_COLORS = {1: "#60A5FA", 2: "#F472B6", 3: "#34D399"}


def _build_sensor_scatter(df: pd.DataFrame, sensor_x: str, sensor_y: str) -> go.Figure:
    """Scatter plot comparing two sensors, one dot per reading, coloured by engine."""
    if df is None or sensor_x not in df.columns or sensor_y not in df.columns:
        return go.Figure()

    label_x = sensor_x.replace("SensorMeasure", "Sensor ")
    label_y = sensor_y.replace("SensorMeasure", "Sensor ")
    fig = go.Figure()

    for eng_id, grp in df.groupby("engine_id"):
        fig.add_trace(go.Scatter(
            x=grp[sensor_x],
            y=grp[sensor_y],
            mode="markers",
            name=f"Engine {eng_id}",
            marker=dict(
                color=ENGINE_COLORS.get(eng_id, "#94A3B8"),
                size=4,
                opacity=0.6,
            ),
            hovertemplate=(
                f"<b>Engine {eng_id}</b><br>"
                f"{label_x}: %{{x:.3f}}<br>"
                f"{label_y}: %{{y:.3f}}<br>"
                "Cycle: %{customdata}<extra></extra>"
            ),
            customdata=grp["cycle"],
        ))

    fig.update_layout(
        title=f"{label_x} vs {label_y}",
        xaxis_title=label_x,
        yaxis_title=label_y,
        legend=dict(orientation="h", yanchor="top", y=-0.2, font=dict(size=10)),
        hovermode="closest",
        margin=dict(l=50, r=20, t=50, b=80),
        xaxis=dict(gridcolor="rgba(148,163,184,0.15)"),
        yaxis=dict(gridcolor="rgba(148,163,184,0.15)"),
    )
    return fig


def build() -> None:
    """Build the Engine Health tab inside a gr.Blocks context."""

    gr.Markdown("## Engine Health & Remaining Useful Life")
    gr.Markdown(
        "NASA turbofan degradation dataset — track engine RUL across operating cycles.  \n"
        "_Source: `main.predictive_maintenance.nasa_engine_rul`_"
    )

    with gr.Row():
        load_btn = gr.Button("Load Engine Data", variant="primary")
        status   = gr.Markdown("")

    # ── Summary KPI row ────────────────────────────────────────────────────────
    with gr.Row():
        kpi_critical = gr.Markdown("### Critical Engines\n# **—**")
        kpi_warning  = gr.Markdown("### Warning Engines\n# **—**")
        kpi_healthy  = gr.Markdown("### Healthy Engines\n# **—**")
        kpi_avg_rul  = gr.Markdown("### Fleet Avg RUL\n# **—**")

    # ── Charts ─────────────────────────────────────────────────────────────────
    with gr.Row():
        rul_trend   = gr.Plot(label="RUL Over Time — Top 10 Most Critical Engines")
        with gr.Column():
            with gr.Row():
                sensor_x_dd = gr.Dropdown(
                    choices=VARYING_SENSORS, value="SensorMeasure2",
                    label="X Axis Sensor", scale=1,
                )
                sensor_y_dd = gr.Dropdown(
                    choices=VARYING_SENSORS, value="SensorMeasure7",
                    label="Y Axis Sensor", scale=1,
                )
            rul_buckets = gr.Plot(label="Sensor Comparison")

    with gr.Row():
        sensor_plot = gr.Plot(label="Sensor Profile — Fleet Average by Cycle")
        status_bar  = gr.Plot(label="Engine Status Breakdown")

    gr.Markdown("### Engine Status Table")
    engine_table = gr.DataFrame(label="All Engines — sorted by lowest RUL", height=350)

    # ── STRETCH GOAL: Maintenance Schedule ─────────────────────────────────────
    with gr.Accordion("Maintenance Schedule Predictor (Stretch Goal)", open=False):
        gr.Markdown(
            "Automatically generates a 30-day maintenance calendar based on each engine's "
            "RUL. Engines with RUL ≤ 30 cycles are flagged as **URGENT** (schedule within 7 days)."
        )
        sched_btn = gr.Button("Generate Schedule", variant="secondary")
        sched_tbl = gr.DataFrame(label="Recommended Maintenance Schedule", height=300)

    # ── Event handlers ─────────────────────────────────────────────────────────
    def load_data(request: gr.Request):
        user  = auth_service.get_user_from_request(request)
        email = user["email"] if user else "unknown"
        role  = user["role"]  if user else "viewer"

        try:
            # ── Chart 1: RUL Trend — color-coded by severity, critical zone band ──
            trend_df  = db_service.get_engine_rul_trend(limit_engines=10)
            trend_fig = go.Figure()
            if len(trend_df) > 0:
                engine_min_rul = (
                    trend_df.groupby("engine_id")["rul"].min().sort_values()
                )
                palette = px.colors.sample_colorscale(
                    "RdYlGn",
                    [i / max(len(engine_min_rul) - 1, 1)
                     for i in range(len(engine_min_rul))][::-1],
                )
                color_map = dict(zip(engine_min_rul.index, palette))

                for eng_id, grp in trend_df.groupby("engine_id"):
                    grp_s = grp.sort_values("cycle")
                    trend_fig.add_trace(go.Scatter(
                        x=grp_s["cycle"], y=grp_s["rul"],
                        mode="lines",
                        name=f"Engine {eng_id}",
                        line=dict(width=2, color=color_map.get(eng_id, "#94A3B8")),
                        hovertemplate=(
                            f"<b>Engine {eng_id}</b><br>"
                            "Cycle: %{x}<br>RUL: %{y} cycles<extra></extra>"
                        ),
                    ))

                trend_fig.add_hrect(
                    y0=0, y1=50,
                    fillcolor="rgba(229,57,53,0.07)", line_width=0,
                    annotation_text="Critical zone",
                    annotation_position="top left",
                    annotation_font=dict(color="#E53935", size=11),
                )
                trend_fig.add_hline(
                    y=50, line_dash="dash", line_color="#E53935", line_width=1.5,
                )
                trend_fig.add_hrect(
                    y0=50, y1=100,
                    fillcolor="rgba(251,140,0,0.05)", line_width=0,
                )

            trend_fig.update_layout(
                title="RUL Over Cycles — 10 Most Critical Engines",
                xaxis_title="Cycle",
                yaxis_title="Remaining Useful Life (cycles)",
                showlegend=True,
                legend=dict(orientation="h", yanchor="top", y=-0.2, font=dict(size=10)),
                hovermode="x unified",
                margin=dict(l=50, r=20, t=50, b=80),
            )

            # ── Chart 2: Sensor Comparison Scatter ───────────────────────────
            bucket_df = db_service.get_engine_rul_buckets()
            bucket_order = ["Critical (<50)", "Warning (50-99)", "Healthy (≥100)"]
            bucket_df["bucket"] = pd.Categorical(
                bucket_df["bucket"], categories=bucket_order, ordered=True
            )
            bucket_df = bucket_df.sort_values("bucket")

            scatter_raw = db_service._sql_query(f"""
                SELECT id AS engine_id, Cycle AS cycle, {", ".join(VARYING_SENSORS)}
                FROM {db_service._ENG_TBL}
                ORDER BY id, Cycle
            """)

            bucket_fig = _build_sensor_scatter(
                scatter_raw, "SensorMeasure2", "SensorMeasure7"
            )

            # ── Chart 3: Sensor Profile — all meaningful sensors, legend toggle ─
            sensor_selects = ", ".join(
                [f"ROUND(AVG({s}), 4) AS {s}" for s in VARYING_SENSORS]
            )
            sensor_raw = db_service._sql_query(f"""
                SELECT Cycle AS cycle, {sensor_selects}
                FROM {db_service._ENG_TBL}
                GROUP BY Cycle
                ORDER BY Cycle
                LIMIT 500
            """)

            sensor_fig = go.Figure()
            colors = px.colors.qualitative.Safe + px.colors.qualitative.Pastel

            for i, sensor in enumerate(VARYING_SENSORS):
                if sensor not in sensor_raw.columns:
                    continue
                label = sensor.replace("SensorMeasure", "Sensor ")
                col = sensor_raw[sensor]
                col_range = col.max() - col.min()
                normalized = (col - col.min()) / col_range if col_range > 0 else col * 0

                sensor_fig.add_trace(go.Scatter(
                    x=sensor_raw["cycle"],
                    y=normalized,
                    mode="lines",
                    name=label,
                    line=dict(width=1.5, color=colors[i % len(colors)]),
                    # First 4 visible by default; rest toggled via legend click
                    visible=True if i < 4 else "legendonly",
                    hovertemplate=(
                        f"<b>{label}</b><br>"
                        "Cycle: %{x}<br>"
                        "Raw avg: %{customdata:.3f}<extra></extra>"
                    ),
                    customdata=sensor_raw[sensor],
                ))

            sensor_fig.update_layout(
                title="Fleet-Average Sensor Readings by Cycle (normalised 0–1)",
                xaxis_title="Cycle",
                yaxis_title="Normalised Reading",
                legend=dict(
                    orientation="v",
                    x=1.02, y=1,
                    font=dict(size=10),
                    itemclick="toggle",
                    itemdoubleclick="toggleothers",
                ),
                hovermode="x unified",
                margin=dict(l=50, r=160, t=50, b=40),
            )

            # ── Chart 4: Engine Status Breakdown — cleaner vertical bar ─────────
            stat_fig = go.Figure()
            for _, row in bucket_df.iterrows():
                status_key = row["bucket"].split()[0]
                stat_fig.add_trace(go.Bar(
                    x=[row["bucket"]],
                    y=[row["count"]],
                    name=row["bucket"],
                    marker=dict(
                        color=_STATUS_COLOR.get(status_key, "#94A3B8"),
                        line=dict(width=0),
                    ),
                    text=[row["count"]],
                    textposition="outside",
                    textfont=dict(size=14),
                    hovertemplate=f"<b>{row['bucket']}</b><br>Engines: {row['count']}<extra></extra>",
                    width=0.5,
                ))

            stat_fig.update_layout(
                title="Engine Count by Status",
                xaxis_title="",
                yaxis_title="Number of Engines",
                showlegend=False,
                margin=dict(l=50, r=20, t=50, b=40),
                yaxis=dict(gridcolor="rgba(148,163,184,0.15)"),
                bargap=0.4,
            )

            # ── Engine table & KPIs (unchanged) ──────────────────────────────────
            eng_df   = db_service.get_engine_latest_status(limit=200)
            critical = int(bucket_df[bucket_df["bucket"] == "Critical (<50)"]["count"].sum())
            warning  = int(bucket_df[bucket_df["bucket"] == "Warning (50-99)"]["count"].sum())
            healthy  = int(bucket_df[bucket_df["bucket"] == "Healthy (≥100)"]["count"].sum())
            avg_rul  = int(eng_df["remaining_rul"].mean()) if len(eng_df) > 0 else 0

            audit_service.log_event(
                action_type="QUERY",
                user_email=email, user_role=role,
                source_tables=db_service.ENGINE_TABLE,
                query_text="Engine health tab load",
                row_count=len(eng_df),
            )

            return (
                trend_fig, bucket_fig, sensor_fig, stat_fig, eng_df,
                f"### Critical Engines\n# **{critical}**",
                f"### Warning Engines\n# **{warning}**",
                f"### Healthy Engines\n# **{healthy}**",
                f"### Fleet Avg RUL\n# **{avg_rul} cycles**",
                "",
                scatter_raw,
            )

        except Exception as exc:
            logger.error("Engine tab load error: %s", exc)
            empty = go.Figure()
            return (empty, empty, empty, empty, gr.update(),
                    "### Critical Engines\n# **—**",
                    "### Warning Engines\n# **—**",
                    "### Healthy Engines\n# **—**",
                    "### Fleet Avg RUL\n# **—**",
                    f"⚠️ {str(exc)[:120]}",
                    None)

    def generate_schedule(request: gr.Request):
        """STRETCH: Build a maintenance schedule from current RUL data."""
        try:
            eng_df = db_service.get_engine_latest_status(limit=500)
            today  = date.today()
            rows   = []
            for _, row in eng_df.iterrows():
                rul = row["remaining_rul"]
                if rul < 0:
                    rul = 0
                if rul <= 30:
                    sched_date = today + timedelta(days=max(1, int(rul * 0.5)))
                    priority   = "URGENT" if rul <= 15 else "HIGH"
                elif rul <= 100:
                    sched_date = today + timedelta(days=int(rul * 0.6))
                    priority   = "MEDIUM"
                else:
                    continue

                rows.append({
                    "Engine ID":         int(row["engine_id"]),
                    "Current Status":    row["status"],
                    "RUL (cycles)":      int(rul),
                    "Scheduled Date":    sched_date.isoformat(),
                    "Priority":          priority,
                    "Action":            "Preventive Maintenance Inspection",
                })
            if not rows:
                rows = [{"Engine ID": "—", "note": "All engines healthy — no urgent maintenance"}]
            return pd.DataFrame(rows)
        except Exception as exc:
            return pd.DataFrame({"error": [str(exc)]})

    scatter_df_state = gr.State(value=None)

    def redraw_scatter(sensor_x, sensor_y, raw_df):
        if raw_df is None:
            return go.Figure()
        df = pd.DataFrame(raw_df) if isinstance(raw_df, list) else raw_df
        return _build_sensor_scatter(df, sensor_x, sensor_y)

    sensor_x_dd.change(fn=redraw_scatter,
                       inputs=[sensor_x_dd, sensor_y_dd, scatter_df_state],
                       outputs=[rul_buckets])
    sensor_y_dd.change(fn=redraw_scatter,
                       inputs=[sensor_x_dd, sensor_y_dd, scatter_df_state],
                       outputs=[rul_buckets])

    load_btn.click(
        fn=load_data,
        outputs=[rul_trend, rul_buckets, sensor_plot, status_bar, engine_table,
                 kpi_critical, kpi_warning, kpi_healthy, kpi_avg_rul, status,
                 scatter_df_state],
    )
    sched_btn.click(fn=generate_schedule, outputs=[sched_tbl])