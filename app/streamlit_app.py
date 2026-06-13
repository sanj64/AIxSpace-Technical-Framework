"""AD-DSS Mission Replay & Monitoring Console — Streamlit application."""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Generator

import matplotlib
matplotlib.use("Agg")

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from ad_dss.common.schemas import MissionEvent
from ad_dss.core.mission_engine import MissionEngine
from ad_dss.reports.generate_report import generate_report
from ad_dss.utils.visualize import plot_risk_timeline, save_figure

# ── Constants ────────────────────────────────────────────────────────────────

CONFIG_PATH = "config/settings.yaml"
DATA_ROOT = Path("data/raw")

SCENARIOS: dict[str, str] = {
    "CubeSat/LEO (segments_clean)": str(DATA_ROOT / "segments_clean.csv"),
    "ESA Mission 1": str(DATA_ROOT / "ESA-M1" / "ESA-M1(preprocessed)" / "labels_cleaned.csv"),
    "ESA Mission 2": str(DATA_ROOT / "ESA-M2" / "ESA-M2(preprocessed)" / "labels_cleaned.csv"),
    "ESA Mission 3": str(DATA_ROOT / "ESA-M3" / "ESA- M3(preprocessed)" / "labels_cleaned.csv"),
    "Synthetic Thermal Failure": "GENERATE",
}

METHODS = ["zscore", "isolation_forest", "lstm"]
LEVEL_COLORS = {"LOW": "#2ecc71", "MEDIUM": "#f39c12", "CRITICAL": "#e74c3c"}


# ── App entry point (also importable for headless smoke test) ─────────────────

def build_app() -> None:
    """Configure the Streamlit page (importable without running the server)."""
    st.set_page_config(
        page_title="AD-DSS Mission Console",
        page_icon="🛰️",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _get_engine() -> MissionEngine:
    if "engine" not in st.session_state:
        st.session_state["engine"] = MissionEngine(CONFIG_PATH)
    return st.session_state["engine"]


def _ensure_thermal_csv() -> str:
    """Generate the thermal failure CSV if it doesn't exist yet."""
    out_path = Path("data/artifacts/failure_scenario_thermal.csv")
    if not out_path.exists():
        import sys
        sys.path.insert(0, str(Path("_source/Week 6 - System Modules (Final)/version_0/tests")))
        try:
            from failure_scenario_case_study import Config, generate_synthetic_telemetry, detector_rule_based, detector_zscore
            cfg = Config(raw=_load_config())
            df = generate_synthetic_telemetry(cfg)
            df["alert_rule"] = detector_rule_based(df, cfg)
            df["alert_z"] = detector_zscore(df, cfg)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out_path, index=False)
        except Exception:
            # Fallback: generate a simple thermal ramp synthetically
            _generate_simple_thermal(out_path)
    return str(out_path)


def _generate_simple_thermal(out_path: Path) -> None:
    from ad_dss.telemetry.handler import TelemetryHandler
    h = TelemetryHandler(CONFIG_PATH)
    df = h.generate_synthetic(n_points=500)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path)


def _resolve_data_path(scenario_name: str) -> str:
    path = SCENARIOS[scenario_name]
    if path == "GENERATE":
        return _ensure_thermal_csv()
    if not Path(path).exists():
        # fallback to segments_clean
        st.warning(f"Dataset not found: {path}. Using segments_clean.csv.")
        return str(DATA_ROOT / "segments_clean.csv")
    return path


# ── Sidebar ───────────────────────────────────────────────────────────────────

def _render_sidebar() -> tuple[str, str, int, float]:
    st.sidebar.title("AD-DSS Console")
    st.sidebar.markdown("**Spacecraft Anomaly Detection & Decision Support**")
    st.sidebar.divider()

    scenario = st.sidebar.selectbox("Scenario", list(SCENARIOS.keys()), index=0)
    method = st.sidebar.selectbox("Detection Method", METHODS, index=0)
    speed = st.sidebar.slider("Replay Speed (steps/sec)", 1, 50, 10)
    seed = st.sidebar.number_input("Seed", value=42, step=1)

    st.sidebar.divider()
    st.sidebar.markdown("**KPIs (live)**")

    # Running KPI placeholders
    if "kpi" in st.session_state:
        kpi = st.session_state["kpi"]
        st.sidebar.metric("Anomalies Flagged", kpi.get("n_anomalies", 0))
        st.sidebar.metric("CRITICAL Events", kpi.get("n_critical", 0))
        st.sidebar.metric("SAFE_MODE Actions", kpi.get("n_safe_mode", 0))
        st.sidebar.metric("Steps Processed", kpi.get("n_steps", 0))

    return scenario, method, int(seed), float(speed)


# ── Main panel ────────────────────────────────────────────────────────────────

def _render_controls() -> tuple[bool, bool, bool, bool]:
    cols = st.columns(4)
    play = cols[0].button("▶ Play", use_container_width=True)
    pause = cols[1].button("⏸ Pause", use_container_width=True)
    step = cols[2].button("⏭ Step", use_container_width=True)
    reset = cols[3].button("⏮ Reset", use_container_width=True)
    return play, pause, step, reset


def _render_phase_badge(event: MissionEvent) -> None:
    color_map = {
        "Launch": "#3498db",
        "Deployment": "#9b59b6",
        "Commissioning": "#1abc9c",
        "Operations": "#27ae60",
        "Decommissioning": "#e67e22",
    }
    color = color_map.get(event.phase.name, "#7f8c8d")
    st.markdown(
        f'<span style="background:{color};color:white;padding:4px 12px;border-radius:12px;font-weight:bold">'
        f"Phase: {event.phase.name} | Step {event.step}"
        f"</span>",
        unsafe_allow_html=True,
    )


def _render_telemetry_panel(history: list[MissionEvent]) -> None:
    st.subheader("Telemetry")
    if not history:
        st.info("Start playback to see telemetry.")
        return

    all_cols = list(history[0].telemetry_snapshot.keys())
    timestamps = [e.timestamp for e in history]
    anomaly_ts = {e.timestamp for e in history if any(a.anomaly_flag for a in e.anomaly_flags)}

    fig = go.Figure()
    for col in all_cols[:6]:  # limit to 6 channels for readability
        values = [e.telemetry_snapshot.get(col, 0.0) for e in history]
        fig.add_trace(go.Scatter(x=timestamps, y=values, name=col, mode="lines", line=dict(width=1)))

    # Anomaly markers
    anom_events = [e for e in history if e.timestamp in anomaly_ts]
    if anom_events:
        anom_x = [e.timestamp for e in anom_events]
        anom_y = [e.telemetry_snapshot.get(all_cols[0], 0.0) for e in anom_events]
        fig.add_trace(go.Scatter(
            x=anom_x, y=anom_y, name="Anomaly", mode="markers",
            marker=dict(color="red", size=8, symbol="x")
        ))

    fig.update_layout(height=280, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)


def _render_risk_panel(history: list[MissionEvent], current_event: MissionEvent | None) -> None:
    st.subheader("Risk")
    col_gauge, col_chart = st.columns([1, 2])

    with col_gauge:
        if current_event and current_event.risk:
            level = current_event.risk.level
            score = current_event.risk.score
            color = LEVEL_COLORS.get(level, "#7f8c8d")
            st.markdown(
                f'<div style="text-align:center;padding:20px;border-radius:12px;background:{color};color:white">'
                f'<div style="font-size:2em;font-weight:bold">{level}</div>'
                f'<div style="font-size:1.2em">{score:.2f}</div>'
                f'<div style="font-size:0.8em">{current_event.risk.subsystem}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            st.caption(current_event.risk.reason[:80] if current_event.risk.reason else "")
        else:
            st.info("No risk data yet.")

    with col_chart:
        risks = [e.risk for e in history if e.risk]
        if risks:
            ts = [r.timestamp for r in risks]
            scores = [r.score for r in risks]
            colors = [LEVEL_COLORS.get(r.level, "#95a5a6") for r in risks]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ts, y=scores, mode="lines+markers",
                marker=dict(color=colors, size=5),
                line=dict(color="#95a5a6", width=0.8),
            ))
            fig.add_hline(y=0.30, line_dash="dash", line_color=LEVEL_COLORS["MEDIUM"], annotation_text="MED")
            fig.add_hline(y=0.70, line_dash="dash", line_color=LEVEL_COLORS["CRITICAL"], annotation_text="CRIT")
            fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(range=[0, 1.05]))
            st.plotly_chart(fig, use_container_width=True)


def _render_decision_log(history: list[MissionEvent]) -> None:
    st.subheader("Decision & Backup Log")
    rows = []
    for e in reversed(history[-20:]):  # last 20
        if e.decision:
            rows.append({
                "Time": str(e.timestamp)[:19],
                "Phase": e.phase.name,
                "Action": e.decision.action,
                "Reason": e.decision.reason[:60],
            })
        for b in e.backups:
            rows.append({
                "Time": str(b.timestamp)[:19],
                "Phase": e.phase.name,
                "Action": f"BACKUP: {b.component}→{b.fallback_component}",
                "Reason": b.reason[:60],
            })
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, height=180)
    else:
        st.info("No decisions yet.")


def _render_report_button(history: list[MissionEvent], scenario: str, method: str) -> None:
    if not history:
        return
    if st.button("Generate Report", type="primary"):
        with st.spinner("Generating report..."):
            risks = [e.risk for e in history if e.risk]
            anomalies = [a for e in history for a in e.anomaly_flags]
            decisions = [e.decision for e in history if e.decision]
            backups = [b for e in history for b in e.backups]
            snap_df = pd.DataFrame(
                [e.telemetry_snapshot for e in history],
                index=[e.timestamp for e in history],
            )
            run_results = {
                "dataset": scenario[:20],
                "method": method,
                "seed": 42,
                "anomalies": anomalies,
                "risks": risks,
                "decisions": decisions,
                "backups": backups,
                "telemetry_df": snap_df,
            }
            import tempfile, os
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_p, pdf_p = generate_report(run_results, tmpdir)
                with open(csv_p, "rb") as f:
                    csv_bytes = f.read()
                with open(pdf_p, "rb") as f:
                    pdf_bytes = f.read()

        st.download_button("Download CSV", csv_bytes, file_name="ad_dss_report.csv", mime="text/csv")
        st.download_button("Download PDF", pdf_bytes, file_name="ad_dss_report.pdf", mime="application/pdf")


# ── Replay state machine ──────────────────────────────────────────────────────

def _init_replay(scenario: str, method: str, seed: int) -> None:
    data_path = _resolve_data_path(scenario)
    engine = _get_engine()
    gen = engine.run_replay(data_path, method=method, train=True)
    st.session_state["replay_gen"] = gen
    st.session_state["replay_history"] = []
    st.session_state["replay_running"] = False
    st.session_state["replay_done"] = False
    st.session_state["kpi"] = {"n_anomalies": 0, "n_critical": 0, "n_safe_mode": 0, "n_steps": 0}
    st.session_state["current_event"] = None


def _advance_one_step() -> bool:
    """Advance replay by one step. Returns False when exhausted."""
    gen: Generator = st.session_state.get("replay_gen")
    if gen is None or st.session_state.get("replay_done"):
        return False
    try:
        event: MissionEvent = next(gen)
        history: list = st.session_state["replay_history"]
        history.append(event)
        st.session_state["current_event"] = event

        kpi = st.session_state["kpi"]
        kpi["n_steps"] += 1
        kpi["n_anomalies"] += sum(a.anomaly_flag for a in event.anomaly_flags)
        if event.risk and event.risk.level == "CRITICAL":
            kpi["n_critical"] += 1
        if event.decision and event.decision.action == "SAFE_MODE":
            kpi["n_safe_mode"] += 1
        return True
    except StopIteration:
        st.session_state["replay_done"] = True
        st.session_state["replay_running"] = False
        return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    build_app()

    scenario, method, seed, speed = _render_sidebar()

    st.title("AD-DSS Mission Replay Console")
    st.caption("Spacecraft Anomaly Detection & Decision Support System — TRL 5")

    # Init / reset check
    if "replay_scenario" not in st.session_state or st.session_state.get("replay_scenario") != (scenario, method, seed):
        with st.spinner("Initialising engine and training detector..."):
            _init_replay(scenario, method, seed)
        st.session_state["replay_scenario"] = (scenario, method, seed)

    play, pause, step_btn, reset = _render_controls()

    if reset:
        with st.spinner("Resetting..."):
            _init_replay(scenario, method, seed)
        st.session_state["replay_scenario"] = (scenario, method, seed)
        st.rerun()

    if play:
        st.session_state["replay_running"] = True
    if pause:
        st.session_state["replay_running"] = False
    if step_btn:
        _advance_one_step()

    # Phase badge
    current = st.session_state.get("current_event")
    if current:
        _render_phase_badge(current)
        # Progress bar
        history_len = len(st.session_state.get("replay_history", []))
        st.progress(min(history_len / 500, 1.0))

    st.divider()

    # Panels
    history: list[MissionEvent] = st.session_state.get("replay_history", [])
    col_left, col_right = st.columns([2, 1])

    with col_left:
        _render_telemetry_panel(history)

    with col_right:
        _render_risk_panel(history, current)

    _render_decision_log(history)

    st.divider()
    _render_report_button(history, scenario, method)

    # Auto-advance when running
    if st.session_state.get("replay_running"):
        more = _advance_one_step()
        if more:
            delay = max(0.02, 1.0 / speed)
            time.sleep(delay)
            st.rerun()
        else:
            st.success("Replay complete!")

    if st.session_state.get("replay_done"):
        st.info("Mission replay complete. Press Reset to restart.")


if __name__ == "__main__":
    main()
