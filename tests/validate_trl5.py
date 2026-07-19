"""Validation evidence script — measures KPIs across datasets and detectors.

Run:
    python tests/validate_trl5.py
"""

from __future__ import annotations

import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["MPLBACKEND"] = "Agg"

sys.path.insert(0, "src")

from datetime import datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from ad_dss.common.seed import set_seed  # noqa: E402
from ad_dss.core.mission_engine import MissionEngine  # noqa: E402
from ad_dss.models.anomaly_detector import AnomalyDetector  # noqa: E402


def load_config() -> dict:
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


def compute_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict:
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {
        "TP": tp,
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "Precision": round(prec, 3),
        "Recall": round(rec, 3),
        "F1": round(f1, 3),
    }


def detection_latency(label: pd.Series, pred: pd.Series, t0: int) -> int:
    """Samples from fault onset (t0) to first true positive."""
    after_t0 = pred.iloc[t0:]
    tp_indices = after_t0[after_t0 == 1].index.tolist()
    return int(tp_indices[0] - t0) if tp_indices else 9999


def false_alarm_rate_per_hour(y_true: pd.Series, y_pred: pd.Series, duration_s: int) -> float:
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    hours = duration_s / 3600.0
    return round(fp / hours, 1) if hours > 0 else 0.0


# ─── Thermal Failure Scenario ─────────────────────────────────────────────────


def generate_thermal_data(cfg: dict) -> pd.DataFrame:
    fs = cfg["failure_scenario"]
    sim = fs["simulation"]
    ana = fs["anomaly"]
    np.random.seed(int(sim["seed"]))
    n = int(sim["duration_seconds"])
    start = datetime.fromisoformat(sim["start_time"])
    timestamps = [start + timedelta(seconds=i) for i in range(n)]

    T_base = 35 + np.random.normal(0, 0.4, n)
    T_ambient = 28 + np.random.normal(0, 0.3, n)
    sun = (np.sin(np.linspace(0, 3 * np.pi, n)) > 0).astype(int)
    bus_v = 7.8 + np.random.normal(0, 0.02, n)
    bus_c = 0.9 + 0.2 * sun + np.random.normal(0, 0.03, n)
    t0 = int(ana["t0_index"])
    ramp = np.zeros(n)
    ramp[t0:] = np.linspace(0, float(ana["ramp_amplitude"]), n - t0)
    T_comp = T_base + 0.8 * sun + ramp + np.random.normal(0, 0.25, n)
    label = np.zeros(n, dtype=int)
    label[t0:] = 1

    df = pd.DataFrame(
        {
            "T_component": T_comp,
            "T_ambient": T_ambient,
            "bus_voltage": bus_v,
            "bus_current": bus_c,
            "label_anomaly": label,
        },
        index=pd.DatetimeIndex(timestamps),
    )
    return df


def rule_detector(df: pd.DataFrame, cfg: dict) -> pd.Series:
    rd = cfg["failure_scenario"]["detectors"]["rule"]
    dT = df["T_component"].diff().fillna(0)
    rapid = dT.rolling(int(rd["rapid_rise_window_s"]), min_periods=1).sum() > float(
        rd["rapid_rise_delta"]
    )
    return ((df["T_component"] > float(rd["thr_T"])) | rapid).astype(int)


def zscore_detector(df: pd.DataFrame, cfg: dict) -> pd.Series:
    zd = cfg["failure_scenario"]["detectors"]["zscore"]
    win = int(zd["window_s"])
    minp = int(zd["min_periods"])
    zt = float(zd["z_thresh"])
    mu = df["T_component"].rolling(win, min_periods=minp).mean()
    sigma = df["T_component"].rolling(win, min_periods=minp).std().replace(0, 1e-6)
    return ((df["T_component"] - mu) / sigma > zt).astype(int)


def run_thermal_validation(cfg: dict) -> dict:
    print("\n=== 1. Thermal Failure Scenario ===")
    t0 = int(cfg["failure_scenario"]["anomaly"]["t0_index"])
    n = int(cfg["failure_scenario"]["simulation"]["duration_seconds"])

    df = generate_thermal_data(cfg)
    numeric_df = df[["T_component", "T_ambient", "bus_voltage", "bus_current"]]

    rule_pred = rule_detector(df, cfg)
    z_pred = zscore_detector(df, cfg)
    combined_pred = ((rule_pred == 1) | (z_pred == 1)).astype(int)

    # LSTM on thermal data
    print("  Training LSTM AE on thermal data...")
    t_start = time.perf_counter()
    det_lstm = AnomalyDetector(cfg, method="lstm")
    det_lstm.window_size = 10
    det_lstm.epochs = 8
    det_lstm.train(numeric_df)
    lstm_results = det_lstm.detect(numeric_df, subsystem="Thermal")
    lstm_series = pd.Series(0, index=range(len(df)))
    for r in lstm_results:
        pos = df.index.get_loc(r.timestamp) if r.timestamp in df.index else 0
        lstm_series.iloc[int(pos)] = r.anomaly_flag
    lstm_elapsed = time.perf_counter() - t_start

    # IF on thermal data
    det_if = AnomalyDetector(cfg, method="isolation_forest")
    det_if.train(numeric_df)
    if_results = det_if.detect(numeric_df, subsystem="Thermal")
    if_series = pd.Series([r.anomaly_flag for r in if_results], index=range(len(if_results)))

    y = df["label_anomaly"].reset_index(drop=True)
    results = {}
    print(
        f"\n  {'Detector':<18} {'Precision':>10} {'Recall':>8} {'F1':>8} {'FAR/hr':>8} {'Latency':>10}"
    )
    print("  " + "-" * 65)

    for name, pred in [
        ("Rule-based", rule_pred.reset_index(drop=True)),
        ("Z-score", z_pred.reset_index(drop=True)),
        ("Combined", combined_pred.reset_index(drop=True)),
        ("LSTM AE", lstm_series),
        ("Isolation Forest", if_series.reindex(range(len(y)), fill_value=0)),
    ]:
        m = compute_metrics(y, pred)
        lat = detection_latency(y, pred, t0)
        far = false_alarm_rate_per_hour(y, pred, n)
        print(
            f"  {name:<18} {m['Precision']:>10.3f} {m['Recall']:>8.3f} {m['F1']:>8.3f} {far:>8.1f} {lat:>10d}"
        )
        results[name] = {**m, "FAR_per_hr": far, "Latency_samples": lat}

    print(f"\n  LSTM AE training time: {lstm_elapsed:.1f}s")

    # Save CSV
    Path("data/artifacts").mkdir(parents=True, exist_ok=True)
    df_out = df.copy()
    df_out["alert_rule"] = rule_pred.values
    df_out["alert_z"] = z_pred.values
    df_out["alert_combined"] = combined_pred.values
    df_out.to_csv("data/artifacts/failure_scenario_thermal.csv")
    print("  Thermal CSV saved to data/artifacts/failure_scenario_thermal.csv")

    # Save comparison metrics
    comp_df = pd.DataFrame(results).T
    comp_df.to_csv("data/artifacts/comparison_metrics_thermal.csv")
    print("  Metrics saved to data/artifacts/comparison_metrics_thermal.csv")

    return results


# ─── Dataset-level validation ─────────────────────────────────────────────────


def run_dataset_validation(cfg: dict, data_path: Path, method: str = "zscore") -> dict:
    print(f"\n=== 2. Dataset: {data_path.name} (method={method}) ===")
    engine = MissionEngine("config/settings.yaml")

    # Run 1
    set_seed(42)
    t_start = time.perf_counter()
    results1 = engine.run_batch(data_path, method=method, train=True)
    elapsed1 = time.perf_counter() - t_start

    # Run 2 — same seed, should be identical
    set_seed(42)
    results2 = engine.run_batch(data_path, method=method, train=True)

    n_anomalies1 = sum(a.anomaly_flag for a in results1["anomalies"])
    n_anomalies2 = sum(a.anomaly_flag for a in results2["anomalies"])
    reproducible = n_anomalies1 == n_anomalies2

    print(f"  Samples: {len(results1['telemetry_df']):,}")
    print(f"  Anomalies flagged (run 1): {n_anomalies1:,}")
    print(f"  Anomalies flagged (run 2): {n_anomalies2:,}")
    print(f"  Reproducible:  {'YES' if reproducible else 'NO'}")
    print(f"  Runtime (run 1): {elapsed1:.2f}s")
    print(f"  CRITICAL events: {sum(1 for r in results1['risks'] if r.level=='CRITICAL')}")
    print(f"  SAFE_MODE actions: {sum(1 for d in results1['decisions'] if d.action=='SAFE_MODE')}")

    # Save report
    csv_p, pdf_p = engine.generate_and_save_report(results1, Path("data/artifacts/reports"))
    print(f"  Report: {csv_p.name}, {pdf_p.name}")

    return {
        "samples": len(results1["telemetry_df"]),
        "anomalies": n_anomalies1,
        "reproducible": reproducible,
        "runtime_s": round(elapsed1, 2),
    }


# ─── Robustness: missing data injection ──────────────────────────────────────


def run_robustness_check(cfg: dict) -> None:
    print("\n=== 3. Robustness: 20% Missing Data Injection ===")
    from ad_dss.telemetry.handler import TelemetryHandler

    h = TelemetryHandler("config/settings.yaml")
    df = h.generate_synthetic(n_points=200, seed=99)

    # Inject 20% NaN randomly
    df_num = df.select_dtypes(include="number")
    mask = np.random.default_rng(0).random(df_num.shape) < 0.20
    df_missing = df_num.mask(mask)
    print(f"  NaNs injected: {int(mask.sum())} / {df_num.size} ({100*mask.mean():.1f}%)")

    try:
        det = AnomalyDetector(cfg, method="zscore")
        results = det.detect(df_missing, subsystem="EPS")
        print(f"  Zscore on missing data: OK, {len(results)} results, no crash")
    except Exception as exc:
        print(f"  FAILED: {exc}")

    try:
        det2 = AnomalyDetector(cfg, method="isolation_forest")
        det2.train(df_missing.fillna(0))
        results2 = det2.detect(df_missing.fillna(0), subsystem="EPS")
        print(f"  IsolationForest on missing data: OK, {len(results2)} results")
    except Exception as exc:
        print(f"  FAILED: {exc}")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = load_config()
    set_seed(42)

    thermal_metrics = run_thermal_validation(cfg)

    datasets = [
        Path("data/raw/segments_clean.csv"),
        Path("data/raw/dataset_clean.csv"),
    ]
    dataset_results = {}
    for ds in datasets:
        if ds.exists():
            dataset_results[ds.name] = run_dataset_validation(cfg, ds, method="zscore")
        else:
            print(f"\nSkipping {ds} (not found)")

    run_robustness_check(cfg)

    # ─── Summary Table ────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VALIDATION EVIDENCE SUMMARY")
    print("=" * 70)

    combined = thermal_metrics.get("Combined", {})
    lstm = thermal_metrics.get("LSTM AE", {})

    kpi_rows = [
        (
            "F1 (Combined, thermal)",
            f"{combined.get('F1', 0):.3f}",
            ">= 0.80",
            "PASS" if combined.get("F1", 0) >= 0.80 else "FAIL",
        ),
        (
            "Precision (Combined, thermal)",
            f"{combined.get('Precision', 0):.3f}",
            ">= 0.75",
            "PASS" if combined.get("Precision", 0) >= 0.75 else "FAIL",
        ),
        (
            "Recall (Combined, thermal)",
            f"{combined.get('Recall', 0):.3f}",
            ">= 0.85",
            "PASS" if combined.get("Recall", 0) >= 0.85 else "FAIL",
        ),
        (
            "FAR/hr (Combined)",
            f"{combined.get('FAR_per_hr', 0):.1f}",
            "<= 5.0",
            "PASS" if combined.get("FAR_per_hr", 0) <= 5.0 else "FAIL",
        ),
        (
            "Detection Latency (Combined, samples)",
            f"{combined.get('Latency_samples', 999)}",
            "<= 30",
            "PASS" if combined.get("Latency_samples", 999) <= 30 else "FAIL",
        ),
    ]

    for ds_name, dr in dataset_results.items():
        kpi_rows.append(
            (
                f"Runtime ({ds_name})",
                f"{dr['runtime_s']}s",
                "<= 120s",
                "PASS" if dr["runtime_s"] <= 120 else "FAIL",
            )
        )
        kpi_rows.append(
            (
                f"Reproducibility ({ds_name})",
                "YES" if dr["reproducible"] else "NO",
                "100%",
                "PASS" if dr["reproducible"] else "FAIL",
            )
        )

    print(f"\n{'KPI':<45} {'Measured':>10} {'Target':>10} {'Status':>6}")
    print("-" * 75)
    passes = 0
    for row in kpi_rows:
        status_icon = "PASS" if row[3] == "PASS" else "FAIL"
        print(f"{row[0]:<45} {row[1]:>10} {row[2]:>10} {status_icon:>6}")
        if row[3] == "PASS":
            passes += 1

    print(f"\nResult: {passes}/{len(kpi_rows)} KPI targets met")

    # Save KPI CSV
    kpi_df = pd.DataFrame(kpi_rows, columns=["KPI", "Measured", "Target", "Status"])
    kpi_df.to_csv("data/artifacts/validation_kpis.csv", index=False)
    print("KPI table saved to data/artifacts/validation_kpis.csv")
