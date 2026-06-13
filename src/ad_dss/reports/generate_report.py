"""Report generation: CSV log + PDF summary using matplotlib PdfPages."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.table as mtable
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd

from ad_dss.common.logging_config import get_logger
from ad_dss.common.schemas import AnomalyResult, BackupAction, Decision, RiskResult
from ad_dss.utils.visualize import (
    plot_anomaly_scores,
    plot_detector_comparison,
    plot_risk_timeline,
    plot_telemetry,
)

logger = get_logger(__name__)


def generate_report(
    run_results: dict,
    output_dir: Path | str,
) -> tuple[Path, Path]:
    """Generate CSV + PDF report from a pipeline run_results dict.

    Expected keys in run_results (all optional, gracefully handled):
      - 'anomalies': list[AnomalyResult]
      - 'risks': list[RiskResult]
      - 'decisions': list[Decision]
      - 'backups': list[BackupAction]
      - 'telemetry_df': pd.DataFrame
      - 'scores': np.ndarray
      - 'threshold': float
      - 'metrics': dict  (e.g. {'LSTM': {'Precision': 0.8, ...}})
      - 'dataset': str
      - 'seed': int
      - 'method': str

    Returns (csv_path, pdf_path).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset = run_results.get("dataset", "unknown")
    method = run_results.get("method", "unknown")
    seed = run_results.get("seed", 42)

    csv_path = output_dir / f"report_{dataset}_{method}.csv"
    pdf_path = output_dir / f"report_{dataset}_{method}.pdf"

    # ── Build combined CSV log ────────────────────────────────────────────────
    rows = _build_csv_rows(run_results)
    csv_df = pd.DataFrame(rows)
    csv_df.to_csv(csv_path, index=False)
    logger.info("CSV report saved to %s (%d rows)", csv_path, len(csv_df))

    # ── Build PDF ─────────────────────────────────────────────────────────────
    with PdfPages(str(pdf_path)) as pdf:
        # Page 1: Title / summary
        _pdf_title_page(pdf, run_results, dataset, method, seed)

        # Page 2: Telemetry
        if "telemetry_df" in run_results and run_results["telemetry_df"] is not None:
            fig = plot_telemetry(
                run_results["telemetry_df"],
                anomalies=run_results.get("anomalies"),
            )
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # Page 3: Anomaly scores
        if "scores" in run_results and run_results["scores"] is not None:
            fig = plot_anomaly_scores(
                run_results["scores"],
                threshold=run_results.get("threshold"),
            )
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # Page 4: Risk timeline
        if "risks" in run_results and run_results["risks"]:
            fig = plot_risk_timeline(run_results["risks"])
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # Page 5: Detector comparison
        if "metrics" in run_results and run_results["metrics"]:
            fig = plot_detector_comparison(run_results["metrics"])
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # Page 6: KPI table
        kpi_table = run_results.get("kpi_table")
        if kpi_table:
            _pdf_kpi_table(pdf, kpi_table)

    logger.info("PDF report saved to %s", pdf_path)
    return csv_path, pdf_path


# ── Internals ─────────────────────────────────────────────────────────────────

def _build_csv_rows(run_results: dict) -> list[dict]:
    rows: list[dict] = []

    anomalies: list[AnomalyResult] = run_results.get("anomalies", [])
    risks: list[RiskResult] = run_results.get("risks", [])
    decisions: list[Decision] = run_results.get("decisions", [])
    backups: list[BackupAction] = run_results.get("backups", [])

    for a in anomalies:
        rows.append({
            "type": "anomaly",
            "timestamp": str(a.timestamp),
            "subsystem": a.subsystem,
            "value": a.reconstruction_error,
            "flag": a.anomaly_flag,
            "score": a.score,
            "detail": "",
        })
    for r in risks:
        rows.append({
            "type": "risk",
            "timestamp": str(r.timestamp),
            "subsystem": r.subsystem,
            "value": r.score,
            "flag": 1 if r.level != "LOW" else 0,
            "score": r.score,
            "detail": f"{r.level}: {r.reason}",
        })
    for d in decisions:
        rows.append({
            "type": "decision",
            "timestamp": str(d.timestamp),
            "subsystem": "",
            "value": 0.0,
            "flag": 1,
            "score": 0.0,
            "detail": f"{d.action}: {d.reason}",
        })
    for b in backups:
        rows.append({
            "type": "backup",
            "timestamp": str(b.timestamp),
            "subsystem": b.component,
            "value": 0.0,
            "flag": int(b.activated),
            "score": 0.0,
            "detail": f"{b.component}→{b.fallback_component}: {b.reason}",
        })
    return rows


def _pdf_title_page(pdf: PdfPages, run_results: dict, dataset: str, method: str, seed: int) -> None:
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.axis("off")

    anomalies = run_results.get("anomalies", [])
    risks = run_results.get("risks", [])
    decisions = run_results.get("decisions", [])

    n_anomalies = sum(a.anomaly_flag for a in anomalies)
    n_critical = sum(1 for r in risks if r.level == "CRITICAL")
    n_safe_mode = sum(1 for d in decisions if d.action == "SAFE_MODE")

    title_text = "AD-DSS Mission Report\nAnomaly Detection & Decision Support System"
    ax.text(0.5, 0.92, title_text, ha="center", va="top", fontsize=16, fontweight="bold", transform=ax.transAxes)

    lines = [
        f"Dataset: {dataset}",
        f"Detection Method: {method}",
        f"Random Seed: {seed}",
        "",
        "── Summary ─────────────────────────",
        f"Total anomaly windows flagged : {n_anomalies}",
        f"CRITICAL risk events          : {n_critical}",
        f"SAFE_MODE activations         : {n_safe_mode}",
        f"Total telemetry points        : {len(anomalies)}",
    ]
    ax.text(0.1, 0.78, "\n".join(lines), ha="left", va="top", fontsize=11,
            fontfamily="monospace", transform=ax.transAxes)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _pdf_kpi_table(pdf: PdfPages, kpi_table: dict[str, str | float]) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.axis("off")
    ax.set_title("KPI Summary", fontsize=13, fontweight="bold", pad=20)

    cell_data = [[k, str(v)] for k, v in kpi_table.items()]
    col_labels = ["Metric", "Value"]
    tbl = ax.table(
        cellText=cell_data,
        colLabels=col_labels,
        cellLoc="left",
        loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1.2, 1.5)
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
