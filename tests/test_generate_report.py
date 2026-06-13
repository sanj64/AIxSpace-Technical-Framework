"""Tests for reports/generate_report.py."""

from pathlib import Path

import numpy as np
import pandas as pd

from ad_dss.common.schemas import AnomalyResult, BackupAction, Decision, RiskResult
from ad_dss.reports.generate_report import generate_report


def _make_run_results(n: int = 40) -> dict:
    idx = pd.date_range("2025-01-01", periods=n, freq="s")
    df = pd.DataFrame({"ch0": np.random.default_rng(0).standard_normal(n)}, index=idx)

    anomalies = [
        AnomalyResult(
            timestamp=idx[i],
            subsystem="EPS",
            reconstruction_error=0.1 * i,
            anomaly_flag=int(i > 30),
            score=0.1 * i / n,
        )
        for i in range(n)
    ]
    risks = [
        RiskResult(level="LOW", score=0.2, reason="test", subsystem="EPS", timestamp=idx[10]),
        RiskResult(level="CRITICAL", score=0.9, reason="high!", subsystem="EPS", timestamp=idx[35]),
    ]
    decisions = [Decision(action="SAFE_MODE", reason="critical", timestamp=idx[35])]
    backups = [
        BackupAction(
            component="primary_power",
            fallback_component="backup_battery",
            activated=True,
            reason="test",
            timestamp=idx[35],
        )
    ]

    return {
        "dataset": "test",
        "method": "lstm",
        "seed": 42,
        "anomalies": anomalies,
        "risks": risks,
        "decisions": decisions,
        "backups": backups,
        "telemetry_df": df,
        "scores": np.random.default_rng(1).random(n),
        "threshold": 0.7,
        "metrics": {
            "LSTM": {"Precision": 0.85, "Recall": 0.80, "F1": 0.82},
        },
        "kpi_table": {"F1": "0.82", "Precision": "0.85"},
    }


def test_generate_report_creates_csv_and_pdf(tmp_path: Path) -> None:
    results = _make_run_results()
    csv_path, pdf_path = generate_report(results, tmp_path)
    assert csv_path.exists()
    assert pdf_path.exists()
    assert csv_path.suffix == ".csv"
    assert pdf_path.suffix == ".pdf"


def test_csv_contains_all_event_types(tmp_path: Path) -> None:
    results = _make_run_results()
    csv_path, _ = generate_report(results, tmp_path)
    df = pd.read_csv(csv_path)
    event_types = set(df["type"].unique())
    assert "anomaly" in event_types
    assert "risk" in event_types
    assert "decision" in event_types
    assert "backup" in event_types


def test_csv_row_count(tmp_path: Path) -> None:
    results = _make_run_results(n=40)
    csv_path, _ = generate_report(results, tmp_path)
    df = pd.read_csv(csv_path)
    # 40 anomalies + 2 risks + 1 decision + 1 backup = 44
    assert len(df) == 44


def test_report_with_minimal_results(tmp_path: Path) -> None:
    """Report should not crash with empty optional fields."""
    results = {"dataset": "minimal", "method": "zscore", "seed": 0}
    csv_path, pdf_path = generate_report(results, tmp_path)
    assert csv_path.exists()
    assert pdf_path.exists()
