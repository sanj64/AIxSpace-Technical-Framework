"""Mission feedback module: analyse run history and suggest config updates.

Monitors anomaly score distributions and decision outcomes across multiple
run_results dicts, flags drift, and optionally writes updated thresholds
back to config/settings.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from ad_dss.common.logging_config import get_logger
from ad_dss.common.schemas import AnomalyResult

logger = get_logger(__name__)


class MissionFeedback:
    """Analyse run history and suggest threshold / config updates.

    Args:
        config_path: Path to settings.yaml (used for read-back writes).
        window: Number of past runs to consider for drift detection.
        drift_z_threshold: Z-score above which a distribution shift is flagged.
    """

    def __init__(
        self,
        config_path: str | Path = "config/settings.yaml",
        window: int = 5,
        drift_z_threshold: float = 2.0,
    ) -> None:
        self.config_path = Path(config_path)
        self.window = window
        self.drift_z = drift_z_threshold
        self._history: list[dict] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def record(self, run_results: dict) -> None:
        """Append a completed run's results to internal history."""
        anomalies: list[AnomalyResult] = run_results.get("anomalies", [])
        scores = np.array([a.reconstruction_error for a in anomalies], dtype=np.float64)
        n_flags = int(sum(a.anomaly_flag for a in anomalies))
        self._history.append(
            {
                "n_samples": len(run_results.get("telemetry_df", [])),
                "n_flags": n_flags,
                "flag_rate": n_flags / max(len(scores), 1),
                "score_mean": float(scores.mean()) if len(scores) else 0.0,
                "score_std": float(scores.std()) if len(scores) else 0.0,
                "score_p95": float(np.percentile(scores, 95)) if len(scores) else 0.0,
                "dataset": run_results.get("dataset", "unknown"),
                "method": run_results.get("method", "unknown"),
            }
        )
        if len(self._history) > self.window:
            self._history = self._history[-self.window :]

    def analyse(self) -> dict:
        """Return a feedback summary with drift flags and threshold suggestions.

        Returns:
            dict with keys:
                - drift_detected (bool)
                - flag_rate_trend (list[float])
                - suggested_p95_threshold (float | None)
                - warnings (list[str])
                - n_runs_analysed (int)
        """
        warnings: list[str] = []
        if len(self._history) < 2:
            return {
                "drift_detected": False,
                "flag_rate_trend": [],
                "suggested_p95_threshold": None,
                "warnings": ["Not enough run history (need ≥2 runs)"],
                "n_runs_analysed": len(self._history),
            }

        flag_rates = [h["flag_rate"] for h in self._history]
        p95s = [h["score_p95"] for h in self._history]
        means = [h["score_mean"] for h in self._history]

        drift_detected = False

        # Flag-rate drift: if latest run is >drift_z std-deviations from baseline
        baseline_rates = flag_rates[:-1]
        mu_r, sigma_r = float(np.mean(baseline_rates)), float(np.std(baseline_rates))
        if sigma_r > 0:
            z_r = abs(flag_rates[-1] - mu_r) / sigma_r
            if z_r > self.drift_z:
                drift_detected = True
                warnings.append(
                    f"Flag-rate drift: latest={flag_rates[-1]:.3f}, "
                    f"baseline={mu_r:.3f}±{sigma_r:.3f} (z={z_r:.1f})"
                )

        # Score-mean drift
        baseline_means = means[:-1]
        mu_m, sigma_m = float(np.mean(baseline_means)), float(np.std(baseline_means))
        if sigma_m > 0:
            z_m = abs(means[-1] - mu_m) / sigma_m
            if z_m > self.drift_z:
                drift_detected = True
                warnings.append(
                    f"Score-mean drift: latest={means[-1]:.4f}, "
                    f"baseline={mu_m:.4f}±{sigma_m:.4f} (z={z_m:.1f})"
                )

        # Suggest updated p95 threshold as rolling mean of p95 across history
        suggested_threshold: Optional[float] = round(float(np.mean(p95s)), 6) if p95s else None

        result = {
            "drift_detected": drift_detected,
            "flag_rate_trend": flag_rates,
            "suggested_p95_threshold": suggested_threshold,
            "warnings": warnings,
            "n_runs_analysed": len(self._history),
        }

        if drift_detected:
            logger.warning(
                "MissionFeedback: drift detected across %d runs — %s",
                len(self._history),
                "; ".join(warnings),
            )
        else:
            logger.info("MissionFeedback: no drift detected across %d runs", len(self._history))

        return result

    def write_threshold_suggestion(self, subsystem: str = "default") -> bool:
        """Write the suggested p95 threshold back to config/settings.yaml.

        Returns True if the config was updated, False otherwise.
        """
        feedback = self.analyse()
        suggested = feedback.get("suggested_p95_threshold")
        if suggested is None:
            logger.warning("No threshold suggestion available — need more run history")
            return False

        try:
            with open(self.config_path) as f:
                cfg = yaml.safe_load(f)

            thresholds = cfg.setdefault("anomaly_detector", {}).setdefault("thresholds", {})
            old_val = thresholds.get(subsystem)
            thresholds[subsystem] = suggested

            with open(self.config_path, "w") as f:
                yaml.safe_dump(cfg, f, default_flow_style=False, sort_keys=False)

            logger.info(
                "MissionFeedback: updated threshold[%s] %s → %.6f in %s",
                subsystem,
                old_val,
                suggested,
                self.config_path,
            )
            return True
        except Exception as exc:
            logger.error("MissionFeedback: failed to write config: %s", exc)
            return False

    def clear_history(self) -> None:
        """Reset the internal run history."""
        self._history.clear()
