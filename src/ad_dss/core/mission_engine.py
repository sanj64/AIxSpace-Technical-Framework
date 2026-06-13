"""Mission Engine: orchestrates the full AD-DSS pipeline in batch and replay modes."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Generator

import numpy as np
import pandas as pd
import yaml

from ad_dss.common.logging_config import get_logger
from ad_dss.common.schemas import MissionEvent, MissionPhase
from ad_dss.common.seed import set_seed
from ad_dss.data.preprocessing import clean
from ad_dss.decision.backup_strategy import BackupStrategyManager
from ad_dss.decision.decision_logic import DecisionEngine
from ad_dss.models.anomaly_detector import AnomalyDetector
from ad_dss.models.risk_predictor import RiskPredictor, aggregate_risk
from ad_dss.reports.generate_report import generate_report
from ad_dss.telemetry.handler import TelemetryHandler

logger = get_logger(__name__)


class MissionEngine:
    """Orchestrates the full AD-DSS pipeline.

    Data flow (matches the architecture doc):
      config → handler.load() → preprocessing.clean() → anomaly_detector.detect()
      → risk_predictor.predict() → decision_engine.decide()
      → backup_strategy.evaluate() → visualize + generate_report
    """

    def __init__(self, config_path: str | Path = "config/settings.yaml") -> None:
        config_path = Path(config_path)
        with open(config_path) as f:
            self.config: dict = yaml.safe_load(f)

        seed = self.config.get("seed", 42)
        set_seed(seed)

        self.handler = TelemetryHandler(config_path)
        self._detector: AnomalyDetector | None = None
        self._risk_predictor = RiskPredictor(self.config)
        self._decision_engine = DecisionEngine(self.config)
        self._backup_manager = BackupStrategyManager(self.config)
        self._phases: list[MissionPhase] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def run_batch(
        self,
        data_path: str | Path,
        method: str = "lstm",
        train: bool = True,
    ) -> dict:
        """Run the full pipeline on a dataset; return structured results dict.

        Args:
            data_path: Path to CSV/JSON telemetry file.
            method: Anomaly detector backend — 'lstm', 'isolation_forest', or 'zscore'.
            train: If True, train the detector on this data (unsupervised).

        Returns:
            dict with keys: anomalies, risks, decisions, backups, telemetry_df,
                            scores, threshold, method, dataset, seed, kpi_table.
        """
        t_start = time.perf_counter()
        data_path = Path(data_path)
        logger.info("run_batch: data=%s method=%s", data_path, method)

        df_raw = self.handler.load(data_path)
        df_clean = clean(df_raw)
        if df_clean.empty:
            raise ValueError(f"No numeric columns found in {data_path}")

        phases = self._build_phases(len(df_clean))

        # Score / detect subsystems — train per subsystem for consistency
        subsystems = self._infer_subsystems(df_clean)
        all_anomalies = []
        all_scores = []
        for sub in subsystems:
            sub_cols = [c for c in df_clean.columns if c.startswith(sub + "_") or c.startswith(sub)]
            sub_df = df_clean[sub_cols] if sub_cols else df_clean
            detector = self._build_fresh_detector(method)
            if train:
                detector.train(sub_df)
            results = detector.detect(sub_df, subsystem=sub)
            all_anomalies.extend(results)
            scores_arr = np.array([r.reconstruction_error for r in results])
            if len(scores_arr):
                all_scores.append(scores_arr)
        # Keep last detector for threshold reference
        self._detector = detector  # type: ignore[possibly-undefined]

        combined_scores = np.concatenate(all_scores) if all_scores else np.array([])
        threshold = (
            float(detector._threshold or np.percentile(combined_scores, 95))
            if len(combined_scores)
            else 0.0
        )

        # Risk + decision + backup (step through timeline)
        all_risks = []
        all_decisions = []
        all_backups = []
        self._risk_predictor.reset_history()

        # Group anomalies by timestamp step
        if all_anomalies:
            ts_groups: dict = {}
            for a in all_anomalies:
                ts_groups.setdefault(str(a.timestamp), []).append(a)

            for ts_key, anoms in ts_groups.items():
                phase = self._phase_for_ts(ts_key, df_clean.index, phases)  # type: ignore[arg-type]
                risks = self._risk_predictor.predict(anoms, phase)
                all_risks.extend(risks)
                top_risk = aggregate_risk(risks)
                if top_risk:
                    decision = self._decision_engine.decide(top_risk, phase)
                    all_decisions.append(decision)
                    backups = self._backup_manager.evaluate(decision, top_risk)
                    all_backups.extend(backups)

        elapsed = time.perf_counter() - t_start
        seed = self.config.get("seed", 42)

        # KPI table
        n_flags = sum(a.anomaly_flag for a in all_anomalies)
        n_critical = sum(1 for r in all_risks if r.level == "CRITICAL")
        kpi_table = {
            "Dataset": str(data_path.name),
            "Method": method,
            "Total telemetry samples": len(df_clean),
            "Anomalies flagged": n_flags,
            "CRITICAL risk events": n_critical,
            "SAFE_MODE activations": sum(1 for d in all_decisions if d.action == "SAFE_MODE"),
            "Runtime (s)": f"{elapsed:.2f}",
            "Seed": seed,
        }

        logger.info(
            "run_batch complete: %d anomalies, %d risks, %.2fs",
            len(all_anomalies),
            len(all_risks),
            elapsed,
        )

        return {
            "anomalies": all_anomalies,
            "risks": all_risks,
            "decisions": all_decisions,
            "backups": all_backups,
            "telemetry_df": df_clean,
            "scores": combined_scores,
            "threshold": threshold,
            "method": method,
            "dataset": data_path.stem,
            "seed": seed,
            "phases": phases,
            "kpi_table": kpi_table,
            "runtime_s": elapsed,
        }

    def run_replay(
        self,
        data_path: str | Path,
        method: str = "lstm",
        train: bool = True,
        window_step: int = 1,
    ) -> Generator[MissionEvent, None, None]:
        """Replay mode: yield one MissionEvent per timestep for the Streamlit app.

        Trains the detector on the full dataset first (offline training),
        then streams events through the pipeline step by step.
        """
        data_path = Path(data_path)
        logger.info("run_replay: data=%s method=%s", data_path, method)

        df_raw = self.handler.load(data_path)
        df_clean = clean(df_raw)
        if df_clean.empty:
            raise ValueError(f"No numeric columns in {data_path}")

        phases = self._build_phases(len(df_clean))
        subsystems = self._infer_subsystems(df_clean)

        # Train and pre-score each subsystem independently
        sub_detections: dict[str, list] = {}
        last_detector = None
        for sub in subsystems:
            sub_cols = [c for c in df_clean.columns if c.startswith(sub + "_") or c.startswith(sub)]
            sub_df = df_clean[sub_cols] if sub_cols else df_clean
            detector = self._build_fresh_detector(method)
            if train:
                logger.info("run_replay: training %s detector for %s...", method, sub)
                detector.train(sub_df)
            sub_detections[sub] = detector.detect(sub_df, subsystem=sub)
            last_detector = detector

        detector = last_detector or self._build_fresh_detector(method)  # type: ignore[assignment]
        window_size = detector.window_size if hasattr(detector, "window_size") else 1
        n = len(df_clean)
        self._risk_predictor.reset_history()

        for step in range(0, n, window_step):
            ts = df_clean.index[step]
            phase = self._phase_for_index(step, n, phases)

            # Collect anomalies for this step (aligned by window offset)
            step_anomalies = []
            for sub, detections in sub_detections.items():
                # LSTM detections start at window_size-1; align
                det_idx = max(0, step - (window_size - 1))
                if det_idx < len(detections):
                    step_anomalies.append(detections[det_idx])

            # Risk → decision → backup
            risks = self._risk_predictor.predict(step_anomalies, phase) if step_anomalies else []
            top_risk = aggregate_risk(risks)
            decision = self._decision_engine.decide(top_risk, phase) if top_risk else None
            backups = (
                self._backup_manager.evaluate(decision, top_risk) if (decision and top_risk) else []
            )

            snap = {col: float(df_clean.iloc[step][col]) for col in df_clean.columns}

            yield MissionEvent(
                step=step,
                timestamp=ts,
                phase=phase,
                telemetry_snapshot=snap,
                anomaly_flags=step_anomalies,
                risk=top_risk,
                decision=decision,
                backups=backups,
            )

    def generate_and_save_report(
        self, run_results: dict, output_dir: str | Path | None = None
    ) -> tuple[Path, Path]:
        """Save the CSV + PDF report for a batch run."""
        if output_dir is None:
            output_dir = Path(self.config.get("paths", {}).get("reports", "data/artifacts/reports"))
        return generate_report(run_results, output_dir)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _build_fresh_detector(self, method: str) -> AnomalyDetector:
        """Return a new untrained detector with current config."""
        return AnomalyDetector(self.config, method=method)

    def _build_phases(self, n_samples: int) -> list[MissionPhase]:
        phase_cfgs = self.config.get("mission_phases", [])
        phases = []
        for p in phase_cfgs:
            start = int(p["fraction_start"] * n_samples)
            end = int(p["fraction_end"] * n_samples)
            phases.append(
                MissionPhase(name=p["name"], start_idx=start, end_idx=max(end, start + 1))
            )
        if not phases:
            phases = [MissionPhase("Operations", 0, n_samples)]
        self._phases = phases
        return phases

    def _infer_subsystems(self, df: pd.DataFrame) -> list[str]:
        seen: list[str] = []
        for col in df.columns:
            if "_" in col:
                prefix = col.split("_")[0]
                if prefix not in seen:
                    seen.append(prefix)
        return seen if seen else ["default"]

    def _phase_for_index(self, idx: int, n: int, phases: list[MissionPhase]) -> MissionPhase:
        for phase in phases:
            if phase.start_idx <= idx < phase.end_idx:
                return phase
        return phases[-1]

    def _phase_for_ts(
        self, ts_key: str, index: pd.DatetimeIndex, phases: list[MissionPhase]
    ) -> MissionPhase:
        try:
            pos = index.get_loc(pd.Timestamp(ts_key))
            if isinstance(pos, slice):
                pos = pos.start
            return self._phase_for_index(int(pos), len(index), phases)
        except Exception:
            return phases[-1] if phases else MissionPhase("Operations", 0, 1)


# ── CLI entrypoint ────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="AD-DSS Mission Engine")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings.yaml")
    parser.add_argument(
        "--data", default=None, help="Path to telemetry CSV (overrides config default)"
    )
    parser.add_argument("--method", default="lstm", choices=["lstm", "isolation_forest", "zscore"])
    parser.add_argument("--validate", action="store_true", help="Run validation suite")
    parser.add_argument("--no-report", action="store_true", help="Skip report generation")
    args = parser.parse_args()

    engine = MissionEngine(args.config)

    if args.validate:
        _run_validation(engine, args.method)
        return

    data_path = (
        args.data
        or engine.config.get("paths", {}).get("data_raw", "data/raw") + "/segments_clean.csv"
    )
    data_path = Path(data_path)
    if not data_path.exists():
        logger.error("Data file not found: %s", data_path)
        return

    results = engine.run_batch(data_path, method=args.method)

    if not args.no_report:
        csv_p, pdf_p = engine.generate_and_save_report(results)
        logger.info("Report: CSV=%s PDF=%s", csv_p, pdf_p)

    kpi = results.get("kpi_table", {})
    print("\n-- Pipeline complete ------------------")
    for k, v in kpi.items():
        print(f"  {k:<35} {v}")


def _run_validation(engine: MissionEngine, method: str) -> None:
    """Run KPI measurement across available datasets."""

    datasets = {
        "segments_clean": Path("data/raw/segments_clean.csv"),
        "dataset_clean": Path("data/raw/dataset_clean.csv"),
    }

    all_results = {}
    for name, path in datasets.items():
        if not path.exists():
            logger.warning("Validation dataset not found: %s", path)
            continue
        logger.info("Validating on %s ...", name)
        try:
            results = engine.run_batch(path, method=method)
            all_results[name] = results
            csv_p, pdf_p = engine.generate_and_save_report(results)
            logger.info("  Report saved: %s", pdf_p)
        except Exception as exc:
            logger.error("  Failed on %s: %s", name, exc)

    print("\n-- Validation Summary -----------------")
    for name, results in all_results.items():
        kpi = results.get("kpi_table", {})
        print(f"\nDataset: {name}")
        for k, v in kpi.items():
            print(f"  {k:<35} {v}")


if __name__ == "__main__":
    main()
