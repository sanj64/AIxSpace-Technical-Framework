"""Visualization utilities: pure functions returning matplotlib Figures (headless-safe)."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")  # force non-interactive backend before any other matplotlib import

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
import numpy as np
import pandas as pd

from ad_dss.common.schemas import AnomalyResult, MissionPhase, RiskResult

_LEVEL_COLORS = {"LOW": "#2ecc71", "MEDIUM": "#f39c12", "CRITICAL": "#e74c3c"}
_PHASE_COLORS = ["#e8f4f8", "#fef9e7", "#eafaf1", "#fdedec", "#f5eef8"]


def plot_telemetry(
    df: pd.DataFrame,
    anomalies: list[AnomalyResult] | None = None,
    phases: list[MissionPhase] | None = None,
    figsize: tuple[int, int] = (14, 5),
) -> Figure:
    """Plot subsystem time series with optional anomaly markers and phase bands."""
    fig, ax = plt.subplots(figsize=figsize)

    for col in df.columns:
        ax.plot(df.index, df[col], lw=0.8, label=col, alpha=0.85)

    if anomalies:
        anom_ts = [a.timestamp for a in anomalies if a.anomaly_flag == 1]
        for ts in anom_ts:
            ax.axvline(ts, color="#e74c3c", alpha=0.4, lw=0.7)

    if phases:
        n = len(df)
        for i, phase in enumerate(phases):
            start_ts = df.index[min(phase.start_idx, n - 1)]
            end_ts = df.index[min(phase.end_idx - 1, n - 1)]
            color = _PHASE_COLORS[i % len(_PHASE_COLORS)]
            ax.axvspan(start_ts, end_ts, alpha=0.15, color=color, label=f"Phase: {phase.name}")

    ax.set_title("Subsystem Telemetry", fontsize=12)
    ax.set_xlabel("Time")
    ax.set_ylabel("Value")
    ax.legend(loc="upper right", fontsize=7, ncol=3)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def plot_risk_timeline(
    risk_results: list[RiskResult],
    figsize: tuple[int, int] = (14, 4),
) -> Figure:
    """Plot risk score over time, colour-coded by level."""
    if not risk_results:
        fig, ax = plt.subplots(figsize=figsize)
        ax.set_title("Risk Timeline (no data)")
        return fig

    ts = [r.timestamp for r in risk_results]
    scores = [r.score for r in risk_results]
    colors = [_LEVEL_COLORS.get(r.level, "#95a5a6") for r in risk_results]

    fig, ax = plt.subplots(figsize=figsize)
    ax.scatter(ts, scores, c=colors, s=20, zorder=3)
    ax.plot(ts, scores, color="#7f8c8d", lw=0.5, alpha=0.6)
    ax.axhline(0.30, color=_LEVEL_COLORS["MEDIUM"], ls="--", lw=0.8, alpha=0.7, label="MEDIUM threshold")
    ax.axhline(0.70, color=_LEVEL_COLORS["CRITICAL"], ls="--", lw=0.8, alpha=0.7, label="CRITICAL threshold")
    patches = [mpatches.Patch(color=v, label=k) for k, v in _LEVEL_COLORS.items()]
    ax.legend(handles=patches, loc="upper left", fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_title("Risk Score Timeline")
    ax.set_xlabel("Time")
    ax.set_ylabel("Risk Score")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def plot_anomaly_scores(
    scores: np.ndarray,
    threshold: float | None = None,
    timestamps: pd.DatetimeIndex | None = None,
    figsize: tuple[int, int] = (14, 4),
) -> Figure:
    """Plot raw anomaly reconstruction errors with optional threshold line."""
    fig, ax = plt.subplots(figsize=figsize)
    x = timestamps if timestamps is not None else np.arange(len(scores))
    ax.plot(x, scores, lw=0.8, color="#3498db", label="Anomaly score")
    if threshold is not None:
        ax.axhline(threshold, color="#e74c3c", ls="--", lw=1.0, label=f"Threshold={threshold:.4f}")
    ax.fill_between(x, scores, threshold or 0, where=(scores > (threshold or 0)), color="#e74c3c", alpha=0.2)
    ax.set_title("Anomaly Scores")
    ax.set_xlabel("Time / Step")
    ax.set_ylabel("Reconstruction Error")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def plot_detector_comparison(
    metrics_dict: dict[str, dict[str, float]],
    figsize: tuple[int, int] = (10, 5),
) -> Figure:
    """Bar chart comparing precision/recall/F1 across detector methods."""
    methods = list(metrics_dict.keys())
    metrics_keys = ["Precision", "Recall", "F1"]
    x = np.arange(len(methods))
    width = 0.25

    fig, ax = plt.subplots(figsize=figsize)
    bar_colors = ["#3498db", "#2ecc71", "#e67e22"]
    for i, mk in enumerate(metrics_keys):
        vals = [metrics_dict[m].get(mk, 0.0) for m in methods]
        ax.bar(x + i * width, vals, width, label=mk, color=bar_colors[i], alpha=0.85)

    ax.set_xticks(x + width)
    ax.set_xticklabels(methods)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score")
    ax.set_title("Detector Comparison: Precision / Recall / F1")
    ax.legend()
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    return fig


def save_figure(fig: Figure, path: str) -> None:
    """Save a figure to disk and close it."""
    fig.savefig(path, dpi=100, bbox_inches="tight")
    plt.close(fig)
