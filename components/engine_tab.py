"""Engine Health tab — NASA turbofan RUL tracking with maintenance schedule predictor."""
import logging
from datetime import date, timedelta

import gradio as gr
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from services import db_service, auth_service, audit_service

logger = logging.getLogger(__name__)

_STATUS_COLOR = {"Critical": "#E53935", "Warning": "#FB8C00", "Healthy": "#43A047"}

VARYING_SENSORS = [
    "SensorMeasure2", "SensorMeasure3", "SensorMeasure4", "SensorMeasure7",
    "SensorMeasure9", "SensorMeasure11", "SensorMeasure12", "SensorMeasure14",
    "SensorMeasure15", "SensorMeasure17", "SensorMeasure20", "SensorMeasure21",
]

ENGINE_COLORS = {1: "#60A5FA", 2: "#F472B6", 3: "#34D399"}


# ── Sensor chart helpers ───────────────────────────────────────────────────────

def _base_layout() -> dict:
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=50, r=30, t=50, b=60),
        xaxis=dict(gridcolor="rgba(148,163,184,0.1)"),
        yaxis=dict(gridcolor="rgba(148,163,184,0.1)"),
        legend=dict(orientation="h", yanchor="top", y=-0.25, font=dict(size=10)),
    )


def render_degradation(sensors: list, engines: list, cycle_min: int, cycle_max: int, raw_df: pd.DataFrame):
    if not sensors or not engines:
        return go.Figure()
    filtered = raw_df[
        (raw_df["id"].isin([int(e) for e in engines])) &
        (raw_df["Cycle"] >= cycle_min) &
        (raw_df["Cycle"] <= cycle_max)
    ]
    fig = go.Figure()
    for sensor in sensors:
        for eng_id, grp in filtered.groupby("id"):
            grp_s = grp.sort_values("Cycle")
            fig.add_trace(go.Scatter(
                x=grp_s["Cycle"], y=grp_s[sensor],
                mode="lines",
                name=f"Engine {eng_id} — {sensor.replace('SensorMeasure', 'Sensor ')}",
                line=dict(color=ENGINE_COLORS.get(eng_id, "#94A3B8"), width=1.8),
                opacity=0.85,
                hovertemplate=f"<b>Engine {eng_id}</b><br>{sensor}: %{{y:.3f}}<br>Cycle: %{{x}}<extra></extra>",
            ))
    fig.update_layout(
        title="Sensor Degradation Over Cycles",
        xaxis_title="Cycle", yaxis_title="Sensor Reading",
        **_base_layout(),
    )
    return fig


def render_heatmap(engines: list, cycle_min: int, cycle_max: int, raw_df: pd.DataFrame):
    if not engines:
        return go.Figure()
    filtered = raw_df[
        (raw_df["id"].isin([int(e) for e in engines])) &
        (raw_df["Cycle"] >= cycle_min) &
        (raw_df["Cycle"] <= cycle_max)
    ]
    corr   = filtered[VARYING_SENSORS].corr().round(2)
    labels = [s.replace("SensorMeasure", "Sensor ") for s in VARYING_SENSORS]
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=labels, y=labels,
        colorscale=[[0, "#1D4ED8"], [0.5, "#0F172A"], [1, "#DC2626"]],
        zmid=0,
        text=corr.values, texttemplate="%{text}", textfont=dict(size=8),
        hovertemplate="<b>%{x}</b> vs <b>%{y}</b><br>r = %{z:.2f}<extra></extra>",
    ))
    layout = _base_layout()
    layout["xaxis"] = dict(tickfont=dict(size=8), gridcolor="transparent")
    layout["yaxis"] = dict(tickfont=dict(size=8), gridcolor="transparent", autorange="reversed")
    layout["margin"] = dict(l=90, r=30, t=50, b=100)
    fig.update_layout(title="Sensor Correlation Matrix", **layout)
    return fig


def render_rolling(sensor: str, engines: list, cycle_min: int, cycle_max: int, window: int, raw_df: pd.DataFrame):
    if not engines or not sensor:
        return go.Figure()
    filtered = raw_df[
        (raw_df["id"].isin([int(e) for e in engines])) &
        (raw_df["Cycle"] >= cycle_min) &
        (raw_df["Cycle"] <= cycle_max)
    ]
    fig = go.Figure()
    for eng_id, grp in filtered.groupby("id"):
        g = grp.sort_values("Cycle").copy()
        g["rm"]    = g[sensor].rolling(window, min_periods=1).mean()
        g["rstd"]  = g[sensor].rolling(window, min_periods=1).std().fillna(0)
        g["upper"] = g["rm"] + 2 * g["rstd"]
        g["lower"] = g["rm"] - 2 * g["rstd"]
        color = ENGINE_COLORS.get(eng_id, "#94A3B8")
        r, g2, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)

        # Shaded band
        fig.add_trace(go.Scatter(
            x=pd.concat([g["Cycle"], g["Cycle"][::-1]]),
            y=pd.concat([g["upper"], g["lower"][::-1]]),
            fill="toself",
            fillcolor=f"rgba({r},{g2},{b},0.1)",
            line=dict(color="rgba(0,0,0,0)"), showlegend=False, hoverinfo="skip",
        ))
        # Band edges
        for band_y in [g["upper"], g["lower"]]:
            fig.add_trace(go.Scatter(
                x=g["Cycle"], y=band_y,
                line=dict(color=color, width=0.7, dash="dot"),
                showlegend=False, hoverinfo="skip",
            ))
        # Rolling mean
        fig.add_trace(go.Scatter(
            x=g["Cycle"], y=g["rm"], mode="lines",
            name=f"Engine {eng_id} (mean)",
            line=dict(color=color, width=2),
            hovertemplate=f"<b>Engine {eng_id}</b><br>Rolling Mean: %{{y:.3f}}<br>Cycle: %{{x}}<extra></extra>",
        ))
        # Raw dots
        fig.add_trace(go.Scatter(
            x=g["Cycle"], y=g[sensor], mode="markers",
            name=f"Engine {eng_id} (raw)",
            marker=dict(color=color, size=3, opacity=0.3),
            hovertemplate=f"<b>Engine {eng_id}</b><br>Raw: %{{y:.3f}}<br>Cycle: %{{x}}<extra></extra>",
        ))
    fig.update_layout(
        title=f"Rolling Deviation — {sensor.replace('SensorMeasure', 'Sensor ')} (window={window})",
        xaxis_title="Cycle", yaxis_title="Reading",
        **_base_layout(),
    )
    return fig


# ── Main build function ────────────────────────────────────────────────────────

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

    # ── Original charts (unchanged) ────────────────────────────────────────────
    with gr.Row():
        rul_trend   = gr.Plot(label="RUL Over Time — Top 10 Most Critical Engines")
        rul_buckets = gr.Plot(label="Fleet Health Distribution")

    with gr.Row():
        sensor_plot = gr.Plot(label="Sensor Profile (Avg SensorMeasure2 & 7 by Cycle)")
        status_bar  = gr.Plot(label="Engine Status Breakdown")

    gr.Markdown("### Engine Status Table")
    engine_table = gr.DataFrame(label="All Engines — sorted by lowest RUL", height=350)

    # ── Interactive Sensor Analysis ────────────────────────────────────────────
    gr.Markdown("---")
    gr.Markdown("## Interactive Sensor Analysis")
    gr.Markdown(
        "Drill into raw sensor data. All three charts share the engine and cycle filters below — "
        "charts update instantly when any filter changes. Click **Load Engine Data** above first."
    )

    # State holds the raw sensor dataframe fetched on load
    sensor_df_state = gr.State(value=None)

    # Shared filters
    with gr.Group():
        gr.Markdown("#### Filters")
        with gr.Row():
            engine_filter = gr.CheckboxGroup(
                choices=["1", "2", "3"],
                value=["1", "2", "3"],
                label="Engines",
            )
            with gr.Column():
                cycle_min_sl = gr.Slider(minimum=1, maximum=500, value=1,   step=1, label="Cycle — From")
                cycle_max_sl = gr.Slider(minimum=1, maximum=500, value=500, step=1, label="Cycle — To")

    # Chart 1
    gr.Markdown("### 📈 Sensor Degradation Explorer")
    gr.Markdown("Select one or more sensors to compare their readings across cycles per engine.")
    sensor_deg_dd = gr.Dropdown(
        choices=VARYING_SENSORS,
        value=["SensorMeasure2", "SensorMeasure7"],
        multiselect=True,
        label="Sensors to Plot",
    )
    chart_degradation = gr.Plot(label="Sensor Degradation Over Cycles")

    # Chart 2
    gr.Markdown("### 🔥 Sensor Correlation Heatmap")
    gr.Markdown(
        "Shows how sensors move together for the selected engines and cycle window. "
        "Narrow the cycle range to late-life cycles to see how correlations shift under stress."
    )
    chart_heatmap = gr.Plot(label="Sensor Correlation Matrix")

    # Chart 3
    gr.Markdown("### 📉 Rolling Deviation & Anomaly Bands")
    gr.Markdown("Rolling mean ± 2σ band per engine. Readings escaping the band are early degradation signals.")
    with gr.Row():
        sensor_roll_dd = gr.Dropdown(
            choices=VARYING_SENSORS,
            value="SensorMeasure2",
            label="Sensor",
            multiselect=False,
        )
        window_sl = gr.Slider(minimum=3, maximum=40, value=10, step=1, label="Rolling Window (cycles)")
    chart_rolling = gr.Plot(label="Rolling Deviation")

    # ── Maintenance Schedule (unchanged) ──────────────────────────────────────
    gr.Markdown("---")
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
            # ── Original chart data (all unchanged) ───────────────────────────
            trend_df  = db_service.get_engine_rul_trend(limit_engines=10)
            trend_fig = go.Figure()
            if len(trend_df) > 0:
                for eng_id, grp in trend_df.groupby("engine_id"):
                    trend_fig.add_trace(go.Scatter(
                        x=grp["cycle"], y=grp["rul"],
                        mode="lines", name=f"Engine {eng_id}",
                        line=dict(width=1.5),
                    ))
                trend_fig.add_hline(y=50, line_dash="dash", line_color="#E53935",
                                    annotation_text="Critical threshold (50)")
                trend_fig.update_layout(
                    title="RUL Over Cycles — 10 Most Critical Engines",
                    xaxis_title="Cycle", yaxis_title="Remaining Useful Life",
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="top", y=-0.2),
                )

            bucket_df  = db_service.get_engine_rul_buckets()
            bucket_fig = px.pie(
                bucket_df, names="bucket", values="count",
                color="bucket",
                color_discrete_map={
                    "Critical (<50)":  "#E53935",
                    "Warning (50-99)": "#FB8C00",
                    "Healthy (≥100)":  "#43A047",
                },
                title="Fleet Health Distribution",
                hole=0.45,
            )

            sensor_raw = db_service._sql_query(f"""
                SELECT Cycle AS cycle,
                       ROUND(AVG(SensorMeasure2), 2) AS sensor2,
                       ROUND(AVG(SensorMeasure7), 2) AS sensor7
                FROM {db_service._ENG_TBL}
                GROUP BY Cycle
                ORDER BY Cycle
                LIMIT 500
            """)
            sensor_fig = go.Figure()
            sensor_fig.add_trace(go.Scatter(x=sensor_raw["cycle"], y=sensor_raw["sensor2"],
                                            name="Sensor 2 (Temp)", mode="lines"))
            sensor_fig.add_trace(go.Scatter(x=sensor_raw["cycle"], y=sensor_raw["sensor7"],
                                            name="Sensor 7 (Fan Speed)", mode="lines"))
            sensor_fig.update_layout(title="Fleet-Average Sensor Readings by Cycle",
                                     xaxis_title="Cycle", yaxis_title="Reading")

            stat_fig = px.bar(
                bucket_df, x="bucket", y="count",
                color="bucket",
                color_discrete_map={
                    "Critical (<50)":  "#E53935",
                    "Warning (50-99)": "#FB8C00",
                    "Healthy (≥100)":  "#43A047",
                },
                title="Engine Count by Status",
                labels={"bucket": "Status", "count": "Engines"},
            )
            stat_fig.update_layout(showlegend=False)

            eng_df = db_service.get_engine_latest_status(limit=200)

            critical = int(bucket_df[bucket_df["bucket"] == "Critical (<50)"]["count"].sum())
            warning  = int(bucket_df[bucket_df["bucket"] == "Warning (50-99)"]["count"].sum())
            healthy  = int(bucket_df[bucket_df["bucket"] == "Healthy (≥100)"]["count"].sum())
            avg_rul  = int(eng_df["remaining_rul"].mean()) if len(eng_df) > 0 else 0

            # ── Fetch raw sensor data for new interactive charts ───────────────
            raw_sensor_df = db_service._sql_query(f"""
                SELECT id, Cycle, {", ".join(VARYING_SENSORS)}
                FROM {db_service._ENG_TBL}
                ORDER BY id, Cycle
            """)
            cyc_min = int(raw_sensor_df["Cycle"].min())
            cyc_max = int(raw_sensor_df["Cycle"].max())
            engines = [str(e) for e in sorted(raw_sensor_df["id"].unique())]

            audit_service.log_event(
                action_type="QUERY",
                user_email=email, user_role=role,
                source_tables=db_service.ENGINE_TABLE,
                query_text="Engine health tab load",
                row_count=len(eng_df),
            )

            return (
                # Original outputs (order unchanged)
                trend_fig, bucket_fig, sensor_fig, stat_fig, eng_df,
                f"### Critical Engines\n# **{critical}**",
                f"### Warning Engines\n# **{warning}**",
                f"### Healthy Engines\n# **{healthy}**",
                f"### Fleet Avg RUL\n# **{avg_rul} cycles**",
                "",
                # New outputs for sensor section
                raw_sensor_df,
                gr.CheckboxGroup(choices=engines, value=engines),
                gr.Slider(minimum=cyc_min, maximum=cyc_max, value=cyc_min),
                gr.Slider(minimum=cyc_min, maximum=cyc_max, value=cyc_max),
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
                    None, gr.update(), gr.update(), gr.update())

    def update_sensor_charts(sensors_deg, engines, cycle_min, cycle_max,
                             sensor_roll, window, raw_df):
        """Redraw all three interactive sensor charts from shared filters."""
        if raw_df is None:
            empty = go.Figure()
            return empty, empty, empty
        df = pd.DataFrame(raw_df) if isinstance(raw_df, list) else raw_df
        return (
            render_degradation(sensors_deg, engines, cycle_min, cycle_max, df),
            render_heatmap(engines, cycle_min, cycle_max, df),
            render_rolling(sensor_roll, engines, cycle_min, cycle_max, int(window), df),
        )

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

    # ── Wire load button ───────────────────────────────────────────────────────
    load_btn.click(
        fn=load_data,
        outputs=[
            rul_trend, rul_buckets, sensor_plot, status_bar, engine_table,
            kpi_critical, kpi_warning, kpi_healthy, kpi_avg_rul, status,
            sensor_df_state, engine_filter, cycle_min_sl, cycle_max_sl,
        ],
    )

    # ── Wire interactive filters → three sensor charts ─────────────────────────
    _sensor_inputs  = [sensor_deg_dd, engine_filter, cycle_min_sl, cycle_max_sl,
                       sensor_roll_dd, window_sl, sensor_df_state]
    _sensor_outputs = [chart_degradation, chart_heatmap, chart_rolling]

    for _comp in [sensor_deg_dd, engine_filter, cycle_min_sl, cycle_max_sl,
                  sensor_roll_dd, window_sl]:
        _comp.change(fn=update_sensor_charts,
                     inputs=_sensor_inputs,
                     outputs=_sensor_outputs)

    sched_btn.click(fn=generate_schedule, outputs=[sched_tbl])