"""Risk prediction: anomaly results → risk level via criticality matrix + optional LogReg."""

from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np
import pandas as pd

from ad_dss.common.logging_config import get_logger
from ad_dss.common.schemas import AnomalyResult, MissionPhase, RiskResult

logger = get_logger(__name__)


class RiskPredictor:
    """Maps anomaly results to risk levels using a criticality matrix weighted by mission phase.

    Optionally trains a LogisticRegression classifier as a complement when labels are available.
    """

    def __init__(self, config: dict) -> None:
        rp_cfg = config.get("risk_predictor", config)
        self.persistence_window: int = rp_cfg.get("persistence_window", 5)
        thr = rp_cfg.get("thresholds", {})
        self.thr_low: float = float(thr.get("low", 0.30))
        self.thr_medium: float = float(thr.get("medium", 0.70))
        self.matrix: dict[str, dict[str, float]] = rp_cfg.get("criticality_matrix", {})
        # Per-subsystem deque for persistence
        self._history: dict[str, deque] = {}
        # Optional classifier
        self._classifier: Any = None

    # ── Public API ───────────────────────────────────────────────────────────

    def predict(
        self,
        anomalies: list[AnomalyResult],
        phase: MissionPhase,
    ) -> list[RiskResult]:
        """Map anomaly results for the current step to risk results."""
        if not anomalies:
            return []

        results: list[RiskResult] = []
        # Group by subsystem
        by_sub: dict[str, list[AnomalyResult]] = {}
        for a in anomalies:
            by_sub.setdefault(a.subsystem, []).append(a)

        for sub, anoms in by_sub.items():
            # Update persistence buffer
            buf = self._history.setdefault(sub, deque(maxlen=self.persistence_window))
            latest_flag = max(a.anomaly_flag for a in anoms)
            buf.append(latest_flag)

            # Persistent score: fraction of recent windows that are anomalous
            persistence_score = sum(buf) / len(buf)
            weight = self._get_weight(sub, phase.name)
            risk_score = persistence_score * weight

            if self._classifier is not None:
                risk_score = self._classifier_score(sub, anoms, phase, risk_score)

            level = self._to_level(risk_score)
            ts = anoms[-1].timestamp
            reason = self._reason(sub, phase.name, weight, persistence_score)
            results.append(
                RiskResult(level=level, score=round(risk_score, 4), reason=reason, subsystem=sub, timestamp=ts)
            )

        return results

    def train_classifier(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train an optional LogisticRegression classifier (features: anomaly scores + phase encoding)."""
        from sklearn.linear_model import LogisticRegression

        self._classifier = LogisticRegression(max_iter=500, random_state=42)
        self._classifier.fit(X, y)
        logger.info("Risk LogReg classifier trained on %d samples, classes=%s", len(X), self._classifier.classes_)

    def reset_history(self) -> None:
        """Clear persistence buffers (call at mission start or phase transition)."""
        self._history.clear()

    # ── Internals ────────────────────────────────────────────────────────────

    def _get_weight(self, subsystem: str, phase_name: str) -> float:
        sub_map = self.matrix.get(subsystem) or self.matrix.get("default") or {}
        return float(sub_map.get(phase_name, sub_map.get("Operations", 0.5)))

    def _to_level(self, score: float) -> str:
        if score >= self.thr_medium:
            return "CRITICAL"
        if score >= self.thr_low:
            return "MEDIUM"
        return "LOW"

    def _reason(self, sub: str, phase: str, weight: float, persistence: float) -> str:
        return (
            f"{sub} anomaly in {phase} phase "
            f"(criticality={weight:.2f}, persistence={persistence:.2f})"
        )

    def _classifier_score(
        self,
        sub: str,
        anoms: list[AnomalyResult],
        phase: MissionPhase,
        matrix_score: float,
    ) -> float:
        """Average matrix score with LogReg probability if classifier available."""
        try:
            avg_err = np.mean([a.reconstruction_error for a in anoms])
            phase_enc = hash(phase.name) % 5  # simple ordinal encoding
            X = np.array([[avg_err, phase_enc]])
            proba = float(self._classifier.predict_proba(X)[0, -1])
            return 0.5 * matrix_score + 0.5 * proba
        except Exception:
            return matrix_score


def aggregate_risk(risk_results: list[RiskResult]) -> RiskResult | None:
    """Return the highest-level risk from a list, for a single-decision view."""
    if not risk_results:
        return None
    order = {"LOW": 0, "MEDIUM": 1, "CRITICAL": 2}
    return max(risk_results, key=lambda r: order.get(r.level, 0))
