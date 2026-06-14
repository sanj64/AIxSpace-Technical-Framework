"""AD-DSS Mission Control Center — Streamlit application."""

from __future__ import annotations

import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Generator

import matplotlib

matplotlib.use("Agg")

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml
from plotly.subplots import make_subplots

from ad_dss.common.schemas import MissionEvent
from ad_dss.core.mission_engine import MissionEngine
from ad_dss.reports.generate_report import generate_report

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

PHASE_COLORS = {
    "Launch": "#3498db",
    "Deployment": "#9b59b6",
    "Commissioning": "#1abc9c",
    "Operations": "#27ae60",
    "Decommissioning": "#e67e22",
}

ACTION_ICONS = {
    "SAFE_MODE": "🛑",
    "ABORT_PAYLOAD": "❌",
    "NOTIFY_GROUND": "⚠️",
    "LOG": "📝",
    "IGNORE": "🔇",
}

ACTION_SEVERITY = {
    "SAFE_MODE": "critical",
    "ABORT_PAYLOAD": "critical",
    "NOTIFY_GROUND": "medium",
    "LOG": "low",
    "IGNORE": "low",
}

SUBSYSTEM_COLORS = {
    "EPS": "#f39c12",
    "ADCS": "#3498db",
    "COM": "#2ecc71",
    "Thermal": "#e74c3c",
    "default": "#95a5a6",
}

# Representative telemetry channel per subsystem
_SUBSYSTEM_KEY_CHANNELS = {
    "EPS": ["EPS_voltage", "EPS_v"],
    "ADCS": ["ADCS_roll", "ADCS_x_rate"],
    "COM": ["COM_rssi", "COM_signal"],
    "Thermal": ["Thermal_board", "Thermal_temp", "T_component"],
}

_DARK_BG = "#0d1117"
_PANEL_BG = "#161b22"
_CARD_BG = "#1c2128"
_BORDER = "#30363d"
_TEXT = "#e6edf3"
_TEXT_DIM = "#8b949e"
_ACCENT = "#79c0ff"

# ── Orbital constants (Earth radius = 1 unit) ─────────────────────────────────
_R_ORBIT = 1.15  # ~400 km LEO normalised to Earth radius
_INC_DEG = 51.6  # ISS-like inclination
_N_OPS_ORBITS = 8  # orbits completed during Operations phase

# KSC launch site (lat, lon in degrees)
_KSC_LAT = 28.5
_KSC_LON = -80.5

WARP_OPTIONS = ["0.25×", "0.5×", "1×", "2×", "5×", "10×", "30×", "60×", "300×"]
WARP_STEPS = {
    "0.25×": 0.25,
    "0.5×": 0.5,
    "1×": 1,
    "2×": 2,
    "5×": 5,
    "10×": 10,
    "30×": 30,
    "60×": 60,
    "300×": 300,
}


# ── App entry point ───────────────────────────────────────────────────────────


def build_app() -> None:
    """Configure Streamlit page — importable without a running server."""
    st.set_page_config(
        page_title="AD-DSS Mission Control",
        page_icon="🛰️",
        layout="wide",
        initial_sidebar_state="expanded",
    )


# ── Config & utilities ────────────────────────────────────────────────────────


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _get_engine() -> MissionEngine:
    if "engine" not in st.session_state:
        st.session_state["engine"] = MissionEngine(CONFIG_PATH)
    return st.session_state["engine"]


def _ensure_thermal_csv() -> str:
    out_path = Path("data/artifacts/failure_scenario_thermal.csv")
    if not out_path.exists():
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
        st.warning(f"Dataset not found: {path}. Falling back to segments_clean.csv.")
        return str(DATA_ROOT / "segments_clean.csv")
    return path


def _infer_active_subsystems(event: MissionEvent | None, history: list[MissionEvent]) -> list[str]:
    """Return unique subsystem names from anomaly_flags; fallback to config."""
    seen: list[str] = []
    src = event or (history[-1] if history else None)
    if src:
        for a in src.anomaly_flags:
            if a.subsystem not in seen:
                seen.append(a.subsystem)
    if not seen:
        seen = ["EPS", "ADCS", "COM", "Thermal"]
    return seen


def _get_subsystem_key_value(sub: str, snapshot: dict) -> tuple[str, float]:
    """Pick the most representative telemetry value for a subsystem."""
    for candidate in _SUBSYSTEM_KEY_CHANNELS.get(sub, []):
        if candidate in snapshot:
            return candidate, float(snapshot[candidate])
    # Fallback: first key starting with sub+"_"
    for k, v in snapshot.items():
        if k.startswith(sub + "_") or k.startswith(sub.lower() + "_"):
            return k, float(v)
    # Last resort: first key
    if snapshot:
        k = next(iter(snapshot))
        return k, float(snapshot[k])
    return "N/A", 0.0


def _sub_color(sub: str) -> str:
    return SUBSYSTEM_COLORS.get(sub, SUBSYSTEM_COLORS["default"])


def _level_led(level: str) -> str:
    cls = {"LOW": "led-green", "MEDIUM": "led-amber", "CRITICAL": "led-red"}.get(level, "led-gray")
    return f'<span class="{cls}"></span>'


def _hex_alpha(hex_color: str, alpha: float) -> str:
    """Convert #rrggbb + alpha (0‒1) to rgba() — Plotly rejects 8-char hex."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── MCC Theme injection ───────────────────────────────────────────────────────


def _inject_mcc_theme(is_critical: bool = False) -> None:
    """Inject dark MCC CSS. Called every render cycle as the first st.* call."""
    base_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');

:root {
    --bg: #0d1117; --panel: #161b22; --card: #1c2128;
    --border: #30363d; --accent: #1f6feb;
    --text: #e6edf3; --dim: #8b949e; --mono: #79c0ff;
    --green: #2ecc71; --amber: #f39c12; --red: #e74c3c;
    --blue: #3498db; --purple: #9b59b6; --teal: #1abc9c;
}

/* ── App background ── */
.stApp, [data-testid="stAppViewContainer"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Rajdhani', 'Segoe UI', sans-serif !important;
}
[data-testid="stHeader"] { background: var(--bg) !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #0a0e13 !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * { color: var(--text) !important; }
[data-testid="stSidebar"] .stMarkdown p { color: var(--dim) !important; }

/* ── Typography ── */
h1, h2, h3, h4 { color: var(--text) !important; letter-spacing: 0.04em; }
h3 { font-size: 0.85em !important; text-transform: uppercase;
     color: var(--dim) !important; letter-spacing: 0.12em; }
p, label, .stMarkdown { color: var(--text) !important; }

/* ── Inputs ── */
.stSelectbox > div > div, .stNumberInput > div > div > input {
    background: var(--card) !important;
    border-color: var(--border) !important;
    color: var(--text) !important;
}
.stSlider { color: var(--text) !important; }
.stCheckbox label { color: var(--text) !important; }
.stMultiSelect > div { background: var(--card) !important; border-color: var(--border) !important; }

/* ── Buttons ── */
.stButton > button {
    background: var(--card) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    font-family: 'Rajdhani', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    transition: border-color 0.15s, color 0.15s !important;
}
.stButton > button:hover {
    border-color: var(--accent) !important;
    color: var(--mono) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1f6feb, #1158c7) !important;
    border-color: #1f6feb !important;
    color: white !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] { background: var(--card); border-radius: 6px; padding: 8px; border: 1px solid var(--border); }
[data-testid="stMetricLabel"] { color: var(--dim) !important; font-size: 0.75em !important; text-transform: uppercase; letter-spacing: 0.08em; }
[data-testid="stMetricValue"] { color: var(--mono) !important; font-family: 'Share Tech Mono', monospace !important; }
[data-testid="stMetricDelta"] svg { display: none; }

/* ── Dividers ── */
hr { border-color: var(--border) !important; margin: 12px 0 !important; }

/* ── DataFrames ── */
[data-testid="stDataFrame"] { background: var(--panel) !important; }
.stDataFrame { border: 1px solid var(--border) !important; border-radius: 6px; }

/* ── Progress bar ── */
.stProgress > div > div { background: linear-gradient(90deg, #1f6feb, var(--teal)) !important; }
.stProgress { background: var(--card) !important; }

/* ── Alerts / info ── */
.stAlert { background: var(--card) !important; border-color: var(--border) !important; color: var(--text) !important; }

/* ── Spinner ── */
.stSpinner > div { border-top-color: var(--accent) !important; }

/* ── Status dots ── */
.led-green { display:inline-block;width:10px;height:10px;border-radius:50%;
             background:#2ecc71;box-shadow:0 0 7px #2ecc71;margin-right:6px;vertical-align:middle; }
.led-red   { display:inline-block;width:10px;height:10px;border-radius:50%;
             background:#e74c3c;box-shadow:0 0 7px #e74c3c;margin-right:6px;vertical-align:middle; }
.led-amber { display:inline-block;width:10px;height:10px;border-radius:50%;
             background:#f39c12;box-shadow:0 0 7px #f39c12;margin-right:6px;vertical-align:middle; }
.led-gray  { display:inline-block;width:10px;height:10px;border-radius:50%;
             background:#444;margin-right:6px;vertical-align:middle; }

/* ── MCC cards ── */
.mcc-card { background:var(--card);border:1px solid var(--border);border-radius:6px;
            padding:12px 14px;margin-bottom:6px; }
.mcc-card-header { font-size:0.72em;text-transform:uppercase;letter-spacing:0.12em;
                   color:var(--dim);margin-bottom:4px; }
.mcc-card-value  { font-family:'Share Tech Mono',monospace;font-size:1.5em;color:var(--mono); }
.mcc-card-sub    { font-size:0.72em;color:var(--dim);margin-top:3px; }

/* ── Alert rows ── */
.alert-critical { background:rgba(231,76,60,0.12);border-left:3px solid #e74c3c;
                  padding:5px 10px;margin:2px 0;border-radius:2px; }
.alert-medium   { background:rgba(243,156,18,0.12);border-left:3px solid #f39c12;
                  padding:5px 10px;margin:2px 0;border-radius:2px; }
.alert-low      { background:rgba(46,204,113,0.06);border-left:3px solid #2ecc71;
                  padding:5px 10px;margin:2px 0;border-radius:2px; }

/* ── Badges ── */
.badge { display:inline-block;padding:2px 7px;border-radius:3px;font-size:0.72em;
         font-weight:700;text-transform:uppercase;letter-spacing:0.05em; }
.badge-critical { background:#e74c3c22;color:#e74c3c;border:1px solid #e74c3c55; }
.badge-medium   { background:#f39c1222;color:#f39c12;border:1px solid #f39c1255; }
.badge-low      { background:#2ecc7122;color:#2ecc71;border:1px solid #2ecc7155; }
.badge-info     { background:#3498db22;color:#3498db;border:1px solid #3498db55; }

/* ── Scrollable panels ── */
.mcc-scroll { height:300px;overflow-y:auto;background:var(--panel);
              border:1px solid var(--border);border-radius:6px;padding:8px; }
.mcc-scroll-sm { height:220px;overflow-y:auto;background:var(--panel);
                 border:1px solid var(--border);border-radius:6px;padding:8px; }

/* ── Section labels ── */
.mcc-section { font-size:0.72em;text-transform:uppercase;letter-spacing:0.15em;
               color:#555e6e;margin-bottom:6px;margin-top:2px;font-weight:600; }

/* ── Mission clock ── */
.mcc-clock { font-family:'Share Tech Mono',monospace;font-size:2.6em;
             color:#79c0ff;letter-spacing:0.12em;display:inline-block; }
.mcc-clock-label { font-size:0.65em;text-transform:uppercase;letter-spacing:0.14em;
                   color:#555e6e;display:block;margin-bottom:2px; }
.warp-badge { font-family:'Share Tech Mono',monospace;font-size:0.85em;
              color:#2ecc71;background:rgba(46,204,113,0.1);
              border:1px solid rgba(46,204,113,0.35);border-radius:4px;
              padding:3px 10px;letter-spacing:0.08em;
              vertical-align:middle;margin-left:14px; }
</style>
"""

    critical_css = """
<style>
@keyframes criticalPulse {
    0%   { box-shadow: 0 0 0 2px rgba(231,76,60,0.6); }
    50%  { box-shadow: 0 0 0 5px rgba(231,76,60,0.2); }
    100% { box-shadow: 0 0 0 2px rgba(231,76,60,0.6); }
}
.stApp {
    outline: 2px solid #e74c3c !important;
    animation: criticalPulse 1.2s infinite !important;
}
.critical-banner {
    background: linear-gradient(90deg, rgba(231,76,60,0.9), rgba(192,57,43,0.9));
    color: #fff; text-align: center; padding: 10px 16px;
    font-size: 1em; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; border-radius: 4px; margin-bottom: 10px;
}
</style>
"""
    st.markdown(base_css, unsafe_allow_html=True)
    if is_critical:
        st.markdown(critical_css, unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────


def _render_sidebar() -> tuple[str, str, int, float, str]:
    st.sidebar.markdown(
        "<div style=\"font-family:'Share Tech Mono',monospace;font-size:1.2em;"
        'color:#79c0ff;letter-spacing:0.1em;padding:4px 0 2px">⬡ AD-DSS MCC</div>'
        '<div style="font-size:0.72em;color:#555e6e;letter-spacing:0.08em;'
        'text-transform:uppercase;margin-bottom:12px">Mission Control Center</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.divider()

    scenario = st.sidebar.selectbox("Mission Scenario", list(SCENARIOS.keys()), index=0)
    method = st.sidebar.selectbox("Detection Method", METHODS, index=0)
    warp_label = st.sidebar.select_slider("⏱ Time Warp", options=WARP_OPTIONS, value="10×")
    speed = WARP_STEPS[warp_label]
    seed = st.sidebar.number_input("Seed", value=42, step=1)

    st.sidebar.divider()
    st.sidebar.markdown(
        '<div class="mcc-section" style="color:#555e6e">Live Telemetry</div>',
        unsafe_allow_html=True,
    )

    if "kpi" in st.session_state:
        kpi = st.session_state["kpi"]
        prev = st.session_state.get("_kpi_prev", {})

        def _delta(key: str) -> str | None:
            cur = kpi.get(key, 0)
            p = prev.get(key, cur)
            return f"+{cur - p}" if cur > p else None

        col1, col2 = st.sidebar.columns(2)
        col1.metric("Anomalies", kpi.get("n_anomalies", 0), delta=_delta("n_anomalies"))
        col2.metric("CRITICAL", kpi.get("n_critical", 0), delta=_delta("n_critical"))
        col1.metric("SAFE_MODE", kpi.get("n_safe_mode", 0), delta=_delta("n_safe_mode"))
        col2.metric("Steps", kpi.get("n_steps", 0))

        # System status LED
        current = st.session_state.get("current_event")
        if current and current.risk:
            level = current.risk.level
            color = LEVEL_COLORS[level]
            st.sidebar.markdown(
                f'<div style="margin-top:8px;padding:8px 10px;background:{color}18;'
                f'border:1px solid {color}44;border-radius:4px;text-align:center">'
                f"{_level_led(level)}"
                f'<span style="font-weight:700;color:{color};font-size:0.9em;'
                f'letter-spacing:0.1em">{level}</span></div>',
                unsafe_allow_html=True,
            )
        # snapshot prev kpi for delta next frame
        st.session_state["_kpi_prev"] = dict(kpi)

    return scenario, method, int(seed), float(speed), warp_label


# ── Controls ──────────────────────────────────────────────────────────────────


def _render_controls() -> tuple[bool, bool, bool, bool]:
    cols = st.columns([1, 1, 1, 1, 4])
    play = cols[0].button("▶ PLAY", use_container_width=True, type="primary")
    pause = cols[1].button("⏸ PAUSE", use_container_width=True)
    step = cols[2].button("⏭ STEP", use_container_width=True)
    reset = cols[3].button("⏮ RESET", use_container_width=True)
    return play, pause, step, reset


# ── Mission header ────────────────────────────────────────────────────────────


def _render_mission_header(
    event: MissionEvent | None,
    history: list[MissionEvent],
    scenario: str,
) -> None:
    cols = st.columns([3, 2, 2, 2, 2])

    # Col 0 — Identity
    elapsed = ""
    if len(history) >= 2:
        try:
            delta = history[-1].timestamp - history[0].timestamp
            total_s = int(delta.total_seconds())
            elapsed = f"{total_s // 3600:02d}:{(total_s % 3600) // 60:02d}:{total_s % 60:02d}"
        except Exception:
            elapsed = f"{len(history)} steps"

    cols[0].markdown(
        f"<div style=\"font-family:'Share Tech Mono',monospace;font-size:1.1em;"
        f'color:#79c0ff;font-weight:700">⬡ AD-DSS MCC</div>'
        f'<div style="font-size:0.8em;color:#8b949e;margin-top:2px">'
        f"{scenario[:35]}</div>"
        f"<div style=\"font-family:'Share Tech Mono',monospace;font-size:1.3em;"
        f'color:#e6edf3;margin-top:4px">T+ {elapsed or "--:--:--"}</div>',
        unsafe_allow_html=True,
    )

    # Col 1 — Phase
    phase_name = event.phase.name if event else "STANDBY"
    phase_color = PHASE_COLORS.get(phase_name, "#555e6e")
    cols[1].markdown(
        f'<div class="mcc-card-header">Mission Phase</div>'
        f'<div style="background:{phase_color}22;border:1px solid {phase_color}66;'
        f'border-radius:4px;padding:8px 12px;text-align:center">'
        f'<span style="font-weight:700;color:{phase_color};font-size:1.1em;'
        f'letter-spacing:0.08em">{phase_name.upper()}</span></div>',
        unsafe_allow_html=True,
    )

    # Col 2 — Step + progress
    step_val = event.step if event else 0
    total = event.phase.end_idx if event else 500
    pct = min(step_val / max(total, 1), 1.0)
    cols[2].markdown(
        f'<div class="mcc-card-header">Step</div>'
        f'<div class="mcc-card-value">{step_val:,}</div>',
        unsafe_allow_html=True,
    )
    cols[2].progress(pct)

    # Col 3 — System health
    if event:
        n_flagged = sum(1 for a in event.anomaly_flags if a.anomaly_flag)
        if n_flagged == 0:
            health, hcolor = "NOMINAL", "#2ecc71"
            hled = "led-green"
        elif event.risk and event.risk.level == "CRITICAL":
            health, hcolor = "CRITICAL", "#e74c3c"
            hled = "led-red"
        else:
            health, hcolor = "DEGRADED", "#f39c12"
            hled = "led-amber"
    else:
        health, hcolor, hled = "STANDBY", "#555e6e", "led-gray"

    cols[3].markdown(
        f'<div class="mcc-card-header">System Health</div>'
        f'<div style="background:{hcolor}18;border:1px solid {hcolor}44;border-radius:4px;'
        f'padding:8px 12px;text-align:center">'
        f'<span class="{hled}"></span>'
        f'<span style="font-weight:700;color:{hcolor};letter-spacing:0.08em">{health}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    # Col 4 — Risk state
    if event and event.risk:
        level = event.risk.level
        score = event.risk.score
        rcolor = LEVEL_COLORS[level]
        cols[4].markdown(
            f'<div class="mcc-card-header">Risk State</div>'
            f'<div style="background:{rcolor}22;border:2px solid {rcolor}88;border-radius:6px;'
            f'padding:10px;text-align:center">'
            f'<div style="font-size:1.4em;font-weight:700;color:{rcolor};'
            f'letter-spacing:0.1em">{level}</div>'
            f"<div style=\"font-family:'Share Tech Mono',monospace;color:{rcolor};"
            f'font-size:1.1em">{score:.3f}</div>'
            f'<div style="font-size:0.75em;color:#8b949e;margin-top:2px">'
            f"{event.risk.subsystem}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        cols[4].markdown(
            '<div class="mcc-card-header">Risk State</div>'
            '<div class="mcc-card" style="text-align:center">'
            '<span class="led-gray"></span>'
            '<span style="color:#555e6e">AWAITING DATA</span></div>',
            unsafe_allow_html=True,
        )


# ── Mission timeline ──────────────────────────────────────────────────────────


def _render_mission_timeline(history: list[MissionEvent], total_steps: int) -> None:
    st.markdown('<div class="mcc-section">Mission Timeline</div>', unsafe_allow_html=True)

    phase_fracs = [
        ("Launch", 0.00, 0.05),
        ("Deployment", 0.05, 0.15),
        ("Commissioning", 0.15, 0.30),
        ("Operations", 0.30, 0.90),
        ("Decommissioning", 0.90, 1.00),
    ]

    fig = go.Figure()
    for name, fs, fe in phase_fracs:
        s = int(fs * total_steps)
        e = int(fe * total_steps)
        color = PHASE_COLORS.get(name, "#555e6e")
        fig.add_trace(
            go.Bar(
                x=[e - s],
                y=["Timeline"],
                base=[s],
                orientation="h",
                name=name,
                marker_color=_hex_alpha(color, 0.33),
                marker_line_color=color,
                marker_line_width=1,
                text=name,
                textposition="inside",
                textfont=dict(size=10, color="#e6edf3"),
                hovertemplate=f"{name}<br>Steps {s}–{e}<extra></extra>",
            )
        )

    if history:
        cur_step = history[-1].step
        fig.add_vline(
            x=cur_step,
            line_color="#ffffff",
            line_width=2,
            annotation_text="NOW",
            annotation_font_color="#ffffff",
            annotation_font_size=9,
        )

        critical_steps = [e.step for e in history if e.risk and e.risk.level == "CRITICAL"]
        if critical_steps:
            fig.add_trace(
                go.Scatter(
                    x=critical_steps,
                    y=["Timeline"] * len(critical_steps),
                    mode="markers",
                    name="CRITICAL",
                    marker=dict(
                        color="#e74c3c", size=10, symbol="diamond", line=dict(width=1, color="#fff")
                    ),
                    showlegend=True,
                    hovertemplate="CRITICAL at step %{x}<extra></extra>",
                )
            )

    fig.update_layout(
        height=100,
        barmode="stack",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.05,
            x=0,
            font=dict(size=9, color="#8b949e"),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            range=[0, total_steps],
            showgrid=False,
            color="#555e6e",
            tickfont=dict(size=9),
        ),
        yaxis=dict(showticklabels=False),
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_PANEL_BG,
        margin=dict(l=0, r=0, t=28, b=20),
        font=dict(color=_TEXT, size=9),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Subsystem health grid ─────────────────────────────────────────────────────


def _render_subsystem_health_grid(event: MissionEvent | None, history: list[MissionEvent]) -> None:
    st.markdown('<div class="mcc-section">Subsystem Health</div>', unsafe_allow_html=True)

    subsystems = _infer_active_subsystems(event, history)
    anomaly_counts: dict[str, int] = defaultdict(int)
    for e in history:
        for a in e.anomaly_flags:
            if a.anomaly_flag:
                anomaly_counts[a.subsystem] += 1

    cols = st.columns(len(subsystems))
    for i, sub in enumerate(subsystems):
        color = _sub_color(sub)
        has_anomaly = False
        cur_score = 0.0
        key_name, cur_val = "N/A", 0.0

        if event:
            for a in event.anomaly_flags:
                if a.subsystem == sub:
                    has_anomaly = bool(a.anomaly_flag)
                    cur_score = a.score
                    break
            key_name, cur_val = _get_subsystem_key_value(sub, event.telemetry_snapshot)

        led = "led-red" if has_anomaly else "led-green"
        border_color = "#e74c3c" if has_anomaly else _BORDER
        status_text = "ANOMALY" if has_anomaly else "NOMINAL"
        status_color = "#e74c3c" if has_anomaly else "#2ecc71"
        cnt = anomaly_counts.get(sub, 0)

        cols[i].markdown(
            f'<div class="mcc-card" style="border-top:3px solid {color};'
            f'border-color:{border_color}">'
            f'<div class="mcc-card-header"><span class="{led}"></span>{sub}</div>'
            f'<div class="mcc-card-value">{cur_val:.3f}</div>'
            f'<div class="mcc-card-sub">{key_name}</div>'
            f'<div style="margin-top:6px;display:flex;justify-content:space-between;'
            f'align-items:center">'
            f'<span style="font-size:0.72em;font-weight:700;color:{status_color};'
            f'letter-spacing:0.08em">{status_text}</span>'
            f'<span style="font-family:monospace;font-size:0.8em;color:{color}">'
            f"score {cur_score:.3f}</span>"
            f"</div>"
            f'<div style="font-size:0.7em;color:#555e6e;margin-top:3px">'
            f"Anomalies: {cnt}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ── Enhanced telemetry panel ──────────────────────────────────────────────────


def _render_telemetry_panel(history: list[MissionEvent]) -> None:
    st.markdown('<div class="mcc-section">Telemetry Channels</div>', unsafe_allow_html=True)

    if not history:
        st.markdown(
            '<div class="mcc-card" style="text-align:center;color:#555e6e;padding:24px">'
            "Start playback to stream telemetry.</div>",
            unsafe_allow_html=True,
        )
        return

    # Limit to last 200 steps for performance
    plot_hist = history[-200:]
    all_cols = list(plot_hist[0].telemetry_snapshot.keys())

    # Channel selector
    sel_cols = st.multiselect(
        "Channels",
        options=all_cols,
        default=all_cols[:6],
        key="tel_channel_select",
        label_visibility="collapsed",
    )
    autoscroll = st.checkbox("Auto-scroll", value=True, key="tel_autoscroll")

    if not sel_cols:
        sel_cols = all_cols[:4]

    timestamps = [e.timestamp for e in plot_hist]

    # Two subplots: telemetry (70%) + anomaly score (30%)
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.68, 0.32],
        vertical_spacing=0.06,
    )

    # Telemetry traces
    anomaly_ts_set = {
        e.timestamp for e in plot_hist if any(a.anomaly_flag for a in e.anomaly_flags)
    }
    for col in sel_cols:
        values = [e.telemetry_snapshot.get(col, 0.0) for e in plot_hist]
        prefix = col.split("_")[0] if "_" in col else col
        trace_color = _sub_color(prefix)
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=values,
                name=col,
                mode="lines",
                line=dict(color=trace_color, width=1.2),
                hovertemplate=f"{col}: %{{y:.4f}}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # Anomaly X markers on first selected channel
    anom_events = [e for e in plot_hist if e.timestamp in anomaly_ts_set]
    if anom_events and sel_cols:
        ax = [e.timestamp for e in anom_events]
        ay = [e.telemetry_snapshot.get(sel_cols[0], 0.0) for e in anom_events]
        fig.add_trace(
            go.Scatter(
                x=ax,
                y=ay,
                name="Anomaly",
                mode="markers",
                marker=dict(
                    color="#e74c3c", size=9, symbol="x", line=dict(width=2, color="#e74c3c")
                ),
                hovertemplate="Anomaly at %{x}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    # Phase transition lines
    for idx in range(1, len(plot_hist)):
        if plot_hist[idx].phase.name != plot_hist[idx - 1].phase.name:
            pcolor = PHASE_COLORS.get(plot_hist[idx].phase.name, "#555e6e")
            fig.add_vline(
                x=plot_hist[idx].timestamp,
                line_color=pcolor,
                line_dash="dot",
                line_width=1,
                annotation_text=plot_hist[idx].phase.name,
                annotation_font_size=8,
                annotation_font_color=pcolor,
                row=1,
                col=1,
            )

    # Anomaly score traces (per subsystem)
    sub_scores: dict[str, list[float]] = defaultdict(list)
    sub_ts: dict[str, list] = defaultdict(list)
    for e in plot_hist:
        for a in e.anomaly_flags:
            sub_scores[a.subsystem].append(a.score)
            sub_ts[a.subsystem].append(e.timestamp)

    for sub, scores in sub_scores.items():
        fig.add_trace(
            go.Scatter(
                x=sub_ts[sub],
                y=scores,
                name=f"{sub} score",
                mode="lines",
                line=dict(color=_sub_color(sub), width=1, dash="dot"),
                showlegend=True,
                hovertemplate=f"{sub} score: %{{y:.3f}}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    # Threshold line on score subplot
    fig.add_hline(y=0.5, line_dash="dash", line_color="#555e6e", line_width=0.8, row=2, col=1)

    # X-axis range for autoscroll
    if autoscroll and len(timestamps) > 1:
        x_range = [timestamps[max(0, len(timestamps) - 100)], timestamps[-1]]
        fig.update_xaxes(range=x_range, row=1, col=1)
        fig.update_xaxes(range=x_range, row=2, col=1)

    fig.update_layout(
        height=370,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", y=-0.12, font=dict(size=9, color=_TEXT_DIM)),
        paper_bgcolor=_DARK_BG,
        plot_bgcolor=_PANEL_BG,
        font=dict(color=_TEXT, size=10),
    )
    fig.update_xaxes(gridcolor="#1e252e", color=_TEXT_DIM)
    fig.update_yaxes(gridcolor="#1e252e", color=_TEXT_DIM, row=1, col=1)
    fig.update_yaxes(
        gridcolor="#1e252e",
        color=_TEXT_DIM,
        range=[0, 1.05],
        title_text="Score",
        title_font=dict(size=9),
        row=2,
        col=1,
    )

    st.plotly_chart(fig, use_container_width=True)


# ── Risk contribution panel ───────────────────────────────────────────────────


def _render_risk_contribution_panel(
    history: list[MissionEvent], current_event: MissionEvent | None
) -> None:
    st.markdown('<div class="mcc-section">Risk Breakdown</div>', unsafe_allow_html=True)

    # Per-subsystem scores from current + recent window
    sub_scores: dict[str, float] = {}
    recent = history[-5:] if len(history) >= 5 else history
    for e in recent:
        for a in e.anomaly_flags:
            sub_scores[a.subsystem] = max(sub_scores.get(a.subsystem, 0.0), a.score * 0.75)
    if current_event:
        for a in current_event.anomaly_flags:
            sub_scores[a.subsystem] = max(sub_scores.get(a.subsystem, 0.0), a.score)

    if sub_scores:
        subs = list(sub_scores.keys())
        scores = [sub_scores[s] for s in subs]
        bar_colors = [
            (
                LEVEL_COLORS["CRITICAL"]
                if s >= 0.70
                else LEVEL_COLORS["MEDIUM"] if s >= 0.30 else LEVEL_COLORS["LOW"]
            )
            for s in scores
        ]
        bar_fig = go.Figure(
            go.Bar(
                x=scores,
                y=subs,
                orientation="h",
                marker_color=[_hex_alpha(c, 0.53) for c in bar_colors],
                marker_line_color=bar_colors,
                marker_line_width=1.5,
                text=[f"{s:.3f}" for s in scores],
                textposition="inside",
                textfont=dict(color="#e6edf3", size=10),
                hovertemplate="%{y}: %{x:.3f}<extra></extra>",
            )
        )
        bar_fig.add_vline(x=0.30, line_dash="dash", line_color=LEVEL_COLORS["MEDIUM"], line_width=1)
        bar_fig.add_vline(
            x=0.70, line_dash="dash", line_color=LEVEL_COLORS["CRITICAL"], line_width=1
        )
        bar_fig.update_layout(
            height=160,
            xaxis=dict(
                range=[0, 1.05], gridcolor="#1e252e", color=_TEXT_DIM, tickfont=dict(size=9)
            ),
            yaxis=dict(color=_TEXT_DIM, tickfont=dict(size=9)),
            paper_bgcolor=_DARK_BG,
            plot_bgcolor=_PANEL_BG,
            margin=dict(l=0, r=0, t=5, b=0),
            font=dict(color=_TEXT, size=9),
            showlegend=False,
        )
        st.plotly_chart(bar_fig, use_container_width=True)
    else:
        st.markdown(
            '<div class="mcc-card" style="text-align:center;color:#555e6e;padding:12px">'
            "Awaiting risk data...</div>",
            unsafe_allow_html=True,
        )

    # Risk score timeline
    risks = [e.risk for e in history if e.risk]
    if risks:
        ts = [r.timestamp for r in risks]
        scores_r = [r.score for r in risks]
        colors_r = [LEVEL_COLORS.get(r.level, "#95a5a6") for r in risks]
        tl = go.Figure()
        tl.add_trace(
            go.Scatter(
                x=ts,
                y=scores_r,
                mode="lines+markers",
                marker=dict(color=colors_r, size=4),
                line=dict(color="#30363d", width=1),
                hovertemplate="Risk: %{y:.3f}<extra></extra>",
                showlegend=False,
            )
        )
        tl.add_hline(y=0.30, line_dash="dot", line_color=LEVEL_COLORS["MEDIUM"], line_width=0.8)
        tl.add_hline(y=0.70, line_dash="dot", line_color=LEVEL_COLORS["CRITICAL"], line_width=0.8)
        tl.update_layout(
            height=130,
            yaxis=dict(
                range=[0, 1.05], gridcolor="#1e252e", color=_TEXT_DIM, tickfont=dict(size=9)
            ),
            xaxis=dict(gridcolor="#1e252e", color=_TEXT_DIM, tickfont=dict(size=9)),
            paper_bgcolor=_DARK_BG,
            plot_bgcolor=_PANEL_BG,
            margin=dict(l=0, r=0, t=5, b=0),
            font=dict(color=_TEXT, size=9),
        )
        st.plotly_chart(tl, use_container_width=True)


def _render_risk_panel(history: list[MissionEvent], current_event: MissionEvent | None) -> None:
    """Kept for backward compatibility — delegates to contribution panel."""
    _render_risk_contribution_panel(history, current_event)


# ── Anomaly alert feed ────────────────────────────────────────────────────────


def _render_anomaly_alert_feed(history: list[MissionEvent]) -> None:
    st.markdown('<div class="mcc-section">Alert Feed</div>', unsafe_allow_html=True)

    rows_html = ""
    count = 0
    for e in reversed(history):
        if count >= 50:
            break
        level = e.risk.level if e.risk else "LOW"
        alert_class = {
            "CRITICAL": "alert-critical",
            "MEDIUM": "alert-medium",
        }.get(level, "alert-low")

        for a in e.anomaly_flags:
            if not a.anomaly_flag:
                continue
            ts_str = str(e.timestamp)[:19]
            sub = a.subsystem
            sc = a.score
            color = _sub_color(sub)
            reason = e.risk.reason if e.risk else f"Anomaly in {sub}"
            reason_short = reason[:80] + ("…" if len(reason) > 80 else "")

            rows_html += (
                f'<div class="{alert_class}" style="font-size:0.82em">'
                f'<span style="font-family:monospace;color:#555e6e">{ts_str}</span>'
                f'<span class="badge" style="margin:0 6px;background:{color}22;'
                f'color:{color};border:1px solid {color}44">{sub}</span>'
                f'<span style="color:#c9d1d9">{reason_short}</span>'
                f'<span style="float:right;font-family:monospace;color:{color};'
                f'font-size:0.9em">{sc:.3f}</span>'
                f"</div>"
            )
            count += 1
            if count >= 50:
                break

    if not rows_html:
        rows_html = (
            '<div style="text-align:center;color:#555e6e;padding:20px;font-size:0.85em">'
            "No anomalies detected yet.</div>"
        )

    st.markdown(
        f'<div class="mcc-scroll-sm">{rows_html}</div>',
        unsafe_allow_html=True,
    )


# ── Backup status panel ───────────────────────────────────────────────────────


def _render_backup_status_panel(history: list[MissionEvent]) -> None:
    st.markdown('<div class="mcc-section">Backup Systems</div>', unsafe_allow_html=True)

    cfg = st.session_state.setdefault("_cfg", _load_config())
    backup_cfg = cfg.get("backup_strategies", {})

    # Scan history for activated backups
    active_backups: dict[str, object] = {}
    for e in history:
        for b in e.backups:
            if b.activated:
                active_backups[b.component.split("_")[0]] = b

    canonical = ["EPS", "ADCS", "COM", "Thermal"]
    cols = st.columns(len(canonical))
    for i, sub in enumerate(canonical):
        color = _sub_color(sub)
        bc = backup_cfg.get(sub, {})
        primary_comp = bc.get("component", sub)
        fallback_comp = bc.get("fallback_component", "—")

        bk = active_backups.get(sub)
        if bk:
            cols[i].markdown(
                f'<div class="mcc-card" style="border-top:3px solid #e74c3c;'
                f'border-color:#e74c3c44">'
                f'<div class="mcc-card-header" style="color:#e74c3c">'
                f'<span class="led-red"></span>{sub}</div>'
                f'<div style="font-size:0.85em;font-weight:700;color:#e74c3c;'
                f'letter-spacing:0.06em">⚠ BACKUP ACTIVE</div>'
                f'<div style="font-size:0.72em;color:#8b949e;margin-top:4px;'
                f'text-decoration:line-through">{primary_comp}</div>'
                f'<div style="font-size:0.78em;color:#f39c12">→ {fallback_comp}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            cols[i].markdown(
                f'<div class="mcc-card" style="border-top:3px solid {color}">'
                f'<div class="mcc-card-header"><span class="led-green"></span>{sub}</div>'
                f'<div style="font-size:0.85em;font-weight:700;color:#2ecc71;'
                f'letter-spacing:0.06em">PRIMARY</div>'
                f'<div style="font-size:0.72em;color:#8b949e;margin-top:4px">'
                f"{primary_comp}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )


# ── Decision log ──────────────────────────────────────────────────────────────


def _render_decision_log(history: list[MissionEvent]) -> None:
    st.markdown('<div class="mcc-section">Decision Log</div>', unsafe_allow_html=True)

    rows_html = ""
    count = 0
    for e in reversed(history):
        if count >= 50:
            break

        phase_name = e.phase.name
        phase_color = PHASE_COLORS.get(phase_name, "#555e6e")

        # Decision entry
        if e.decision:
            action = e.decision.action
            icon = ACTION_ICONS.get(action, "")
            sev = ACTION_SEVERITY.get(action, "low")
            sub = e.risk.subsystem if e.risk else "—"
            sc = _sub_color(sub)
            ts_str = str(e.decision.timestamp)[:19]
            reason = e.decision.reason

            rows_html += (
                f'<tr style="border-bottom:1px solid #1e252e">'
                f'<td style="padding:6px 8px;font-family:monospace;font-size:0.78em;'
                f'color:#555e6e;white-space:nowrap">{ts_str}</td>'
                f'<td style="padding:6px 8px">'
                f'<span style="font-size:0.78em;font-weight:700;color:{phase_color};'
                f'letter-spacing:0.06em">{phase_name}</span></td>'
                f'<td style="padding:6px 8px">'
                f'<span class="badge" style="background:{sc}22;color:{sc};'
                f'border:1px solid {sc}44">{sub}</span></td>'
                f'<td style="padding:6px 8px;white-space:nowrap">{icon} '
                f'<span class="badge badge-{sev}">{action}</span></td>'
                f'<td style="padding:6px 8px;color:#c9d1d9;font-size:0.85em">{reason}</td>'
                f"</tr>"
            )
            count += 1

        # Backup entries
        for b in e.backups:
            ts_str = str(b.timestamp)[:19]
            rows_html += (
                f'<tr style="border-bottom:1px solid #1e252e;background:rgba(231,76,60,0.05)">'
                f'<td style="padding:6px 8px;font-family:monospace;font-size:0.78em;'
                f'color:#555e6e;white-space:nowrap">{ts_str}</td>'
                f'<td style="padding:6px 8px">'
                f'<span style="font-size:0.78em;font-weight:700;color:{phase_color};'
                f'letter-spacing:0.06em">{phase_name}</span></td>'
                f'<td style="padding:6px 8px">'
                f'<span class="badge badge-critical">{b.component.split("_")[0]}</span></td>'
                f'<td style="padding:6px 8px;white-space:nowrap">🔄 '
                f'<span class="badge badge-info">BACKUP</span></td>'
                f'<td style="padding:6px 8px;color:#c9d1d9;font-size:0.85em">'
                f"{b.component} → {b.fallback_component}: {b.reason}</td>"
                f"</tr>"
            )
            count += 1
            if count >= 50:
                break

    if rows_html:
        st.markdown(
            f'<div class="mcc-scroll">'
            f'<table style="width:100%;border-collapse:collapse;font-size:0.82em">'
            f'<thead><tr style="background:#0a0e13;color:#555e6e;font-size:0.75em;'
            f'text-transform:uppercase;letter-spacing:0.08em">'
            f'<th style="padding:7px 8px;text-align:left;white-space:nowrap">Time</th>'
            f'<th style="padding:7px 8px;text-align:left">Phase</th>'
            f'<th style="padding:7px 8px;text-align:left">System</th>'
            f'<th style="padding:7px 8px;text-align:left">Action</th>'
            f'<th style="padding:7px 8px;text-align:left">Reason</th>'
            f"</tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            f"</table></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="mcc-card" style="text-align:center;color:#555e6e;padding:16px">'
            "No decisions logged yet.</div>",
            unsafe_allow_html=True,
        )


# ── Report button ─────────────────────────────────────────────────────────────


def _render_report_button(history: list[MissionEvent], scenario: str, method: str) -> None:
    if not history:
        return
    if st.button("📄 Generate Mission Report", type="primary"):
        with st.spinner("Generating report…"):
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
            with tempfile.TemporaryDirectory() as tmpdir:
                csv_p, pdf_p = generate_report(run_results, tmpdir)
                with open(csv_p, "rb") as f:
                    csv_bytes = f.read()
                with open(pdf_p, "rb") as f:
                    pdf_bytes = f.read()

        c1, c2 = st.columns(2)
        c1.download_button(
            "⬇ Download CSV", csv_bytes, file_name="ad_dss_report.csv", mime="text/csv"
        )
        c2.download_button(
            "⬇ Download PDF", pdf_bytes, file_name="ad_dss_report.pdf", mime="application/pdf"
        )


# ── Replay state machine ──────────────────────────────────────────────────────


def _init_replay(scenario: str, method: str, seed: int) -> None:
    st.session_state.pop("_earth_traces", None)  # force Earth cache rebuild
    data_path = _resolve_data_path(scenario)
    engine = _get_engine()
    gen = engine.run_replay(data_path, method=method, train=True)
    st.session_state["replay_gen"] = gen
    st.session_state["replay_history"] = []
    st.session_state["replay_running"] = False
    st.session_state["replay_done"] = False
    st.session_state["kpi"] = {
        "n_anomalies": 0,
        "n_critical": 0,
        "n_safe_mode": 0,
        "n_steps": 0,
    }
    st.session_state["_kpi_prev"] = {}
    st.session_state["current_event"] = None


def _advance_one_step() -> bool:
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


# ── Mission clock ─────────────────────────────────────────────────────────────


def _render_mission_clock(history: list[MissionEvent], warp_label: str) -> None:
    elapsed_s = 0
    met_str = "—"
    if len(history) >= 2:
        try:
            delta = history[-1].timestamp - history[0].timestamp
            elapsed_s = int(delta.total_seconds())
            met_str = str(history[-1].timestamp)[:19]
        except Exception:
            elapsed_s = len(history)
            met_str = "—"

    hrs = elapsed_s // 3600
    mins = (elapsed_s % 3600) // 60
    secs = elapsed_s % 60

    cols = st.columns([3, 1, 1, 1])
    cols[0].markdown(
        f'<span class="mcc-clock-label">Mission Elapsed Time</span>'
        f'<span class="mcc-clock">T+ {hrs:02d}:{mins:02d}:{secs:02d}</span>'
        f'<span class="warp-badge">{warp_label} WARP</span>',
        unsafe_allow_html=True,
    )
    cols[1].metric("Steps", len(history))
    cols[2].metric("MET", met_str[11:19] if len(met_str) >= 19 else "—")
    cols[3].metric("Date", met_str[:10] if len(met_str) >= 10 else "—")


# ── Orbital helpers ────────────────────────────────────────────────────────────


def _sat_xyz(step: int, total_steps: int, phase_name: str) -> tuple[float, float, float]:
    """Return normalised (x,y,z) satellite position. Earth radius = 1."""
    inc = np.radians(_INC_DEG)
    frac = step / max(total_steps, 1)

    if phase_name == "Launch":
        # Rise from KSC to orbit altitude along a curved arc
        t = min(frac / 0.05, 1.0)  # 0→1 within launch phase span
        r = 1.0 + (_R_ORBIT - 1.0) * t
        lat = np.radians(_KSC_LAT)
        lon = np.radians(_KSC_LON + t * 20.0)  # slight eastward pitch
        x = float(r * np.cos(lat) * np.cos(lon))
        y = float(r * np.cos(lat) * np.sin(lon))
        z = float(r * np.sin(lat))
        return x, y, z

    if phase_name == "Decommissioning":
        # Inward spiral from orbit to surface
        t = max(0.0, min((frac - 0.90) / 0.10, 1.0))
        r = _R_ORBIT - (_R_ORBIT - 1.0) * (t**1.5)
        angle = t * 4 * np.pi  # two loops on the way down
        x = float(r * np.cos(angle))
        y = float(r * np.sin(angle) * np.cos(inc))
        z = float(r * np.sin(angle) * np.sin(inc))
        return x, y, z

    # Orbital phase — map fraction to angle across N_OPS_ORBITS full loops
    if frac < 0.05:
        ops_t = 0.0
    elif frac < 0.90:
        ops_t = (frac - 0.05) / 0.85
    else:
        ops_t = 1.0
    angle = ops_t * _N_OPS_ORBITS * 2 * np.pi
    x = float(_R_ORBIT * np.cos(angle))
    y = float(_R_ORBIT * np.sin(angle) * np.cos(inc))
    z = float(_R_ORBIT * np.sin(angle) * np.sin(inc))
    return x, y, z


def _build_earth_traces() -> list:
    """Build static Earth sphere + grid traces. Cached in session_state."""
    n = 60
    phi_e = np.linspace(0, np.pi, n)
    theta_e = np.linspace(0, 2 * np.pi, n)
    xe = np.outer(np.sin(phi_e), np.cos(theta_e))
    ye = np.outer(np.sin(phi_e), np.sin(theta_e))
    ze = np.outer(np.cos(phi_e), np.ones(n))

    # Surface colour: dark ocean blue at poles, slightly lighter at equator
    surface_color = ze  # −1 (S pole) → +1 (N pole)
    earth = go.Surface(
        x=xe,
        y=ye,
        z=ze,
        surfacecolor=surface_color,
        colorscale=[
            [0.0, "#0a1a3a"],
            [0.3, "#0e2a5c"],
            [0.5, "#1a4a8a"],
            [0.7, "#1e5a3e"],
            [1.0, "#0a2010"],
        ],
        showscale=False,
        opacity=1.0,
        lighting=dict(ambient=0.45, diffuse=0.85, specular=0.15, roughness=0.7),
        lightposition=dict(x=2, y=1, z=2),
        name="Earth",
        hoverinfo="skip",
    )

    traces: list = [earth]

    # Latitude rings every 30°
    for lat_deg in range(-60, 90, 30):
        lat = np.radians(lat_deg)
        t = np.linspace(0, 2 * np.pi, 120)
        gx = np.cos(lat) * np.cos(t)
        gy = np.cos(lat) * np.sin(t)
        gz = np.sin(lat) * np.ones(120)
        color = "rgba(100,160,255,0.30)" if lat_deg == 0 else "rgba(255,255,255,0.08)"
        width = 1.5 if lat_deg == 0 else 1
        traces.append(
            go.Scatter3d(
                x=gx,
                y=gy,
                z=gz,
                mode="lines",
                line=dict(color=color, width=width),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # Meridians every 45°
    for lon_deg in range(0, 360, 45):
        lon = np.radians(lon_deg)
        t = np.linspace(0, np.pi, 60)
        gx = np.sin(t) * np.cos(lon)
        gy = np.sin(t) * np.sin(lon)
        gz = np.cos(t)
        traces.append(
            go.Scatter3d(
                x=gx,
                y=gy,
                z=gz,
                mode="lines",
                line=dict(color="rgba(255,255,255,0.06)", width=1),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    return traces


def _render_orbital_view(
    history: list[MissionEvent],
    current_event: MissionEvent | None,
    total_steps: int,
) -> None:
    st.markdown('<div class="mcc-section">Orbital Trajectory</div>', unsafe_allow_html=True)

    # Cache static Earth + grid
    if "_earth_traces" not in st.session_state:
        st.session_state["_earth_traces"] = _build_earth_traces()
    traces = list(st.session_state["_earth_traces"])  # shallow copy

    inc = np.radians(_INC_DEG)

    # Full orbit reference circle
    t_orb = np.linspace(0, 2 * np.pi, 360)
    traces.append(
        go.Scatter3d(
            x=_R_ORBIT * np.cos(t_orb),
            y=_R_ORBIT * np.sin(t_orb) * np.cos(inc),
            z=_R_ORBIT * np.sin(t_orb) * np.sin(inc),
            mode="lines",
            line=dict(color="rgba(100,180,255,0.30)", width=2, dash="dot"),
            name="Orbit path",
            hoverinfo="skip",
        )
    )

    # Launch reference arc (KSC → orbit)
    t_launch = np.linspace(0, 1, 60)
    lx, ly, lz = [], [], []
    for t in t_launch:
        r = 1.0 + (_R_ORBIT - 1.0) * t
        lat = np.radians(_KSC_LAT)
        lon = np.radians(_KSC_LON + t * 20.0)
        lx.append(float(r * np.cos(lat) * np.cos(lon)))
        ly.append(float(r * np.cos(lat) * np.sin(lon)))
        lz.append(float(r * np.sin(lat)))
    traces.append(
        go.Scatter3d(
            x=lx,
            y=ly,
            z=lz,
            mode="lines",
            line=dict(color="rgba(46,204,113,0.55)", width=2, dash="dash"),
            name="Launch arc",
        )
    )

    # Deorbit spiral reference
    t_deorbit = np.linspace(0, 1, 120)
    dx, dy, dz = [], [], []
    for t in t_deorbit:
        r = _R_ORBIT - (_R_ORBIT - 1.0) * (t**1.5)
        angle = t * 4 * np.pi
        dx.append(float(r * np.cos(angle)))
        dy.append(float(r * np.sin(angle) * np.cos(inc)))
        dz.append(float(r * np.sin(angle) * np.sin(inc)))
    traces.append(
        go.Scatter3d(
            x=dx,
            y=dy,
            z=dz,
            mode="lines",
            line=dict(color="rgba(231,76,60,0.45)", width=2, dash="dash"),
            name="Deorbit spiral",
        )
    )

    # Satellite trail — last 30 events
    trail_events = history[-30:] if len(history) > 30 else history
    if trail_events:
        tx, ty, tz, trail_colors = [], [], [], []
        for i, ev in enumerate(trail_events):
            x, y, z = _sat_xyz(ev.step, total_steps, ev.phase.name)
            tx.append(x)
            ty.append(y)
            tz.append(z)
            alpha = 0.2 + 0.8 * (i / max(len(trail_events) - 1, 1))
            phase_col = PHASE_COLORS.get(ev.phase.name, "#95a5a6")
            r2, g2, b2 = int(phase_col[1:3], 16), int(phase_col[3:5], 16), int(phase_col[5:7], 16)
            trail_colors.append(f"rgba({r2},{g2},{b2},{alpha:.2f})")

        traces.append(
            go.Scatter3d(
                x=tx,
                y=ty,
                z=tz,
                mode="lines",
                line=dict(color=trail_colors[-1], width=3),
                name="Sat trail",
                hoverinfo="skip",
            )
        )

        # Ground track (project trail onto Earth surface)
        gtx, gty, gtz = [], [], []
        for x, y, z in zip(tx, ty, tz):
            r = float(np.sqrt(x**2 + y**2 + z**2))
            if r > 0:
                gtx.append(x / r)
                gty.append(y / r)
                gtz.append(z / r)
        traces.append(
            go.Scatter3d(
                x=gtx,
                y=gty,
                z=gtz,
                mode="lines",
                line=dict(color="rgba(150,150,150,0.25)", width=1),
                name="Ground track",
                hoverinfo="skip",
            )
        )

    # Current satellite position
    if current_event:
        sx, sy, sz = _sat_xyz(current_event.step, total_steps, current_event.phase.name)
        phase_col = PHASE_COLORS.get(current_event.phase.name, "#79c0ff")
        r3, g3, b3 = int(phase_col[1:3], 16), int(phase_col[3:5], 16), int(phase_col[5:7], 16)
        # Halo
        traces.append(
            go.Scatter3d(
                x=[sx],
                y=[sy],
                z=[sz],
                mode="markers",
                marker=dict(size=22, color=f"rgba({r3},{g3},{b3},0.18)", symbol="circle"),
                hoverinfo="skip",
                showlegend=False,
            )
        )
        # Dot
        traces.append(
            go.Scatter3d(
                x=[sx],
                y=[sy],
                z=[sz],
                mode="markers",
                marker=dict(
                    size=10, color=phase_col, symbol="circle", line=dict(width=2, color="#ffffff")
                ),
                name="Satellite",
                hovertemplate=(
                    f"Phase: {current_event.phase.name}<br>"
                    f"Step: {current_event.step}<extra></extra>"
                ),
            )
        )

    # Build figure
    fig = go.Figure(data=traces)

    phase_name = current_event.phase.name if current_event else "—"
    phase_color = PHASE_COLORS.get(phase_name, "#555e6e")
    fig.update_layout(
        height=480,
        scene=dict(
            bgcolor="#0a0e13",
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, showbackground=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, showbackground=False),
            zaxis=dict(showgrid=False, zeroline=False, showticklabels=False, showbackground=False),
            camera=dict(eye=dict(x=1.6, y=1.6, z=0.8)),
            aspectmode="cube",
        ),
        paper_bgcolor="#0a0e13",
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(
            font=dict(color=_TEXT_DIM, size=9),
            bgcolor="rgba(0,0,0,0)",
            orientation="h",
            y=1.02,
            x=0,
        ),
        annotations=[
            dict(
                text=f"<b>{phase_name}</b>",
                xref="paper",
                yref="paper",
                x=0.99,
                y=0.97,
                xanchor="right",
                yanchor="top",
                showarrow=False,
                font=dict(color=phase_color, size=13, family="Share Tech Mono"),
                bgcolor="rgba(0,0,0,0.4)",
                bordercolor=phase_color,
                borderwidth=1,
                borderpad=6,
            )
        ],
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    build_app()

    # Sidebar (selectors + live KPIs)
    scenario, method, seed, speed, warp_label = _render_sidebar()

    # Init / scenario-change check
    if "replay_scenario" not in st.session_state or st.session_state.get("replay_scenario") != (
        scenario,
        method,
        seed,
    ):
        with st.spinner("Initialising engine and training detector…"):
            _init_replay(scenario, method, seed)
        st.session_state["replay_scenario"] = (scenario, method, seed)

    # Controls — process state changes before rendering
    play, pause, step_btn, reset = _render_controls()

    if reset:
        with st.spinner("Resetting…"):
            _init_replay(scenario, method, seed)
        st.session_state["replay_scenario"] = (scenario, method, seed)
        st.rerun()
    if play:
        st.session_state["replay_running"] = True
    if pause:
        st.session_state["replay_running"] = False
    if step_btn:
        _advance_one_step()

    # Current state
    current: MissionEvent | None = st.session_state.get("current_event")
    history: list[MissionEvent] = st.session_state.get("replay_history", [])
    is_critical = bool(current and current.risk and current.risk.level == "CRITICAL")

    # 1. Inject MCC theme (dark CSS + optional critical flash)
    _inject_mcc_theme(is_critical)

    # 1b. Mission clock
    _render_mission_clock(history, warp_label)

    st.markdown("<hr>", unsafe_allow_html=True)

    # 2. CRITICAL banner
    if is_critical and current and current.risk:
        st.markdown(
            f'<div class="critical-banner">🚨 CRITICAL ALERT — '
            f"{current.risk.subsystem} — {current.risk.reason[:90]}</div>",
            unsafe_allow_html=True,
        )

    # 3. Mission header bar
    _render_mission_header(current, history, scenario)

    st.markdown("<hr>", unsafe_allow_html=True)

    # 4. Mission timeline
    total_steps = history[-1].phase.end_idx if history else 500
    _render_mission_timeline(history, total_steps)

    st.markdown("<hr>", unsafe_allow_html=True)

    # 5. Subsystem health grid
    _render_subsystem_health_grid(current, history)

    st.markdown("<hr>", unsafe_allow_html=True)

    # 5b. 3D Orbital view
    _render_orbital_view(history, current, total_steps)

    st.markdown("<hr>", unsafe_allow_html=True)

    # 6. Main two-column: telemetry (left) + risk (right)
    col_tel, col_risk = st.columns([3, 2])
    with col_tel:
        _render_telemetry_panel(history)
    with col_risk:
        _render_risk_contribution_panel(history, current)

    st.markdown("<hr>", unsafe_allow_html=True)

    # 7. Bottom row: alert feed (wider) + backup status (narrower)
    col_alerts, col_backup = st.columns([3, 2])
    with col_alerts:
        _render_anomaly_alert_feed(history)
    with col_backup:
        _render_backup_status_panel(history)

    st.markdown("<hr>", unsafe_allow_html=True)

    # 8. Decision log (full width)
    _render_decision_log(history)

    st.markdown("<hr>", unsafe_allow_html=True)

    # 9. Report
    _render_report_button(history, scenario, method)

    # 10. Completion messages
    if st.session_state.get("replay_done"):
        st.success("✓ Mission replay complete. Press ⏮ RESET to restart.")

    # 11. Auto-advance loop
    if st.session_state.get("replay_running"):
        more = _advance_one_step()
        if more:
            delay = max(0.02, 1.0 / speed)
            time.sleep(delay)
            st.rerun()
        else:
            st.session_state["replay_running"] = False
            st.rerun()


if __name__ == "__main__":
    main()
