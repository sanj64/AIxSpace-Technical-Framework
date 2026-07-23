"""The only two detectors permitted in the v0.9 commercial evaluation build."""

from __future__ import annotations

import io
from collections import deque
from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from .contracts import canonical_json, sha256_hex


@dataclass(frozen=True, slots=True)
class DetectionResult:
    score: float
    threshold: float
    anomaly: bool
    detector_evidence: dict[str, Any]
    reference_baseline: dict[str, Any]
    ranked_feature_contributions: tuple[dict[str, Any], ...]
    feasible_counterfactual: dict[str, Any]

    @property
    def margin(self) -> float:
        return self.score - self.threshold


def feature_schema_hash(features: tuple[str, ...]) -> str:
    return sha256_hex(canonical_json({"ordered_features": features}))


def _validated_matrix(values: np.ndarray, feature_count: int, name: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != feature_count or len(matrix) == 0:
        raise ValueError(f"{name} must be a non-empty 2D matrix with {feature_count} features")
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} contains NaN or infinite values")
    return matrix


class CausalZScoreDetector:
    identity = "causal_zscore:1.0.0"

    def __init__(
        self,
        features: tuple[str, ...],
        *,
        window: int = 30,
        calibration_quantile: float = 0.995,
        minimum_threshold: float = 3.0,
        degenerate_guard: bool = True,
    ) -> None:
        if window < 3:
            raise ValueError("z-score window must be at least 3")
        if not 0.5 < calibration_quantile < 1:
            raise ValueError("calibration_quantile must be between 0.5 and 1")
        self.features = features
        self.window = window
        self.calibration_quantile = calibration_quantile
        self.minimum_threshold = minimum_threshold
        # The degenerate-window guard (D1 fix) flags a genuine step against a (near-)constant
        # rolling window. It is the safe default. It can be disabled for telemetry that is
        # legitimately piecewise-constant (where it would flag ordinary stepping); such a
        # deployment accepts the documented stuck-sensor blind spot in exchange.
        self.degenerate_guard = degenerate_guard
        self.threshold: float | None = None
        self._history: deque[np.ndarray] = deque(maxlen=window)
        self._reference: dict[str, Any] = {}
        self.artifact_hash = ""

    def fit(self, train: np.ndarray) -> None:
        matrix = _validated_matrix(train, len(self.features), "training data")
        if len(matrix) < self.window:
            raise ValueError("training partition is shorter than the configured z-score window")
        self._history = deque((row.copy() for row in matrix[-self.window :]), maxlen=self.window)
        self._reference = {
            feature: {
                "median": float(np.median(matrix[:, index])),
                "training_min": float(np.min(matrix[:, index])),
                "training_max": float(np.max(matrix[:, index])),
            }
            for index, feature in enumerate(self.features)
        }

    def _raw_score(
        self, row: np.ndarray, *, update: bool
    ) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
        if len(self._history) < self.window:
            raise RuntimeError("z-score detector is not fitted")
        history = np.vstack(self._history)
        means = history.mean(axis=0)
        stds = history.std(axis=0, ddof=1)
        safe_stds = np.where(stds > 1e-12, stds, np.inf)
        z_scores = (row - means) / safe_stds
        z_scores = np.where(np.isfinite(z_scores), z_scores, 0.0)
        score = float(np.max(np.abs(z_scores)))
        if update:
            self._history.append(row.copy())
        return score, z_scores, means, stds

    def calibrate(self, calibration: np.ndarray) -> None:
        matrix = _validated_matrix(calibration, len(self.features), "calibration data")
        scores = [self._raw_score(row, update=True)[0] for row in matrix]
        self.threshold = max(
            self.minimum_threshold,
            float(np.quantile(np.asarray(scores), self.calibration_quantile)),
        )
        artifact = {
            "identity": self.identity,
            "features": self.features,
            "window": self.window,
            "calibration_quantile": self.calibration_quantile,
            "minimum_threshold": self.minimum_threshold,
            "effective_threshold": self.threshold,
            "reference": self._reference,
            "calibration_tail": [row.tolist() for row in self._history],
        }
        self.artifact_hash = sha256_hex(canonical_json(artifact))

    def score_one(self, values: np.ndarray, *, update_reference: bool = True) -> DetectionResult:
        if self.threshold is None:
            raise RuntimeError("z-score detector must be calibrated before scoring")
        row = np.asarray(values, dtype=float)
        if row.shape != (len(self.features),) or not np.isfinite(row).all():
            raise ValueError("runtime row has invalid shape or non-finite values")
        score, z_scores, means, stds = self._raw_score(row, update=update_reference)
        # A (near-)constant rolling window drives std->0, which standardises even a large real
        # step to z=0 (a stuck-sensor blind spot). Treat a genuine deviation against a
        # degenerate window as anomalous so it is neither silently missed nor committed to the
        # rolling reference. The deviation is judged against each channel's training range (or
        # its magnitude when training was also flat) so float quantisation noise does not trip
        # it. Confined to scoring: calibration thresholds/artifacts are unchanged.
        training_range = np.array(
            [
                self._reference[feature]["training_max"] - self._reference[feature]["training_min"]
                for feature in self.features
            ]
        )
        deviation_scale = np.where(
            training_range > 1e-9, training_range, np.maximum(np.abs(means), 1.0)
        )
        degenerate_reference_window = self.degenerate_guard and bool(
            np.any((stds <= 1e-12) & (np.abs(row - means) > 0.05 * deviation_scale))
        )
        anomaly = bool(score > self.threshold or degenerate_reference_window)
        responsible_index = int(np.argmax(np.abs(z_scores)))
        signed_z = float(z_scores[responsible_index])
        std = float(stds[responsible_index])
        direction = 1.0 if signed_z >= 0 else -1.0
        crossing = float(means[responsible_index] + direction * self.threshold * std)
        ranked = tuple(
            {
                "feature": self.features[index],
                "signed_z": float(z_scores[index]),
                "absolute_z": float(abs(z_scores[index])),
                "interpretation": "standardized deviation; not a causal effect",
            }
            for index in np.argsort(-np.abs(z_scores))
        )
        responsible = self.features[responsible_index]
        evidence = {
            "method": "causal rolling z-score",
            "responsible_channel": responsible,
            "raw_value": float(row[responsible_index]),
            "rolling_reference_mean": float(means[responsible_index]),
            "rolling_reference_std": std,
            "signed_z_score": signed_z,
            "threshold": self.threshold,
            "margin": score - self.threshold,
            "window": self.window,
            "exact_threshold_crossing_value": crossing,
            "score_semantics": "maximum absolute z-score; not probability or confidence",
            "degenerate_reference_window": degenerate_reference_window,
        }
        return DetectionResult(
            score=score,
            threshold=self.threshold,
            anomaly=anomaly,
            detector_evidence=evidence,
            reference_baseline=self._reference,
            ranked_feature_contributions=ranked,
            feasible_counterfactual={
                "feature": responsible,
                "nearest_non_anomalous_boundary_value": crossing,
                "condition": f"absolute z-score <= {self.threshold:.6g}",
                "limits": "mathematical threshold boundary; not a causal intervention",
            },
        )

    def update_reference(self, values: np.ndarray) -> None:
        """Commit one already-screened nominal sample to the rolling reference."""

        row = np.asarray(values, dtype=float)
        if row.shape != (len(self.features),) or not np.isfinite(row).all():
            raise ValueError("reference update row has invalid shape or non-finite values")
        self._history.append(row.copy())


class IsolationForestDetector:
    identity = "isolation_forest:1.0.0"

    def __init__(
        self,
        features: tuple[str, ...],
        *,
        seed: int = 42,
        estimators: int = 200,
        calibration_quantile: float = 0.995,
    ) -> None:
        if not 0.5 < calibration_quantile < 1:
            raise ValueError("calibration_quantile must be between 0.5 and 1")
        self.features = features
        self.seed = seed
        self.estimators = estimators
        self.calibration_quantile = calibration_quantile
        self.model = IsolationForest(
            n_estimators=estimators,
            contamination="auto",
            random_state=seed,
            n_jobs=1,
        )
        self.reference_values: np.ndarray | None = None
        self.reference_baseline: dict[str, Any] = {}
        self.threshold: float | None = None
        self.artifact_hash = ""

    def fit(self, train: np.ndarray) -> None:
        matrix = _validated_matrix(train, len(self.features), "training data")
        self.model.fit(matrix)
        self.reference_values = np.median(matrix, axis=0)
        self.reference_baseline = {
            feature: {
                "approved_reference_value": float(self.reference_values[index]),
                "training_min": float(np.min(matrix[:, index])),
                "training_max": float(np.max(matrix[:, index])),
            }
            for index, feature in enumerate(self.features)
        }

    def _score(self, matrix: np.ndarray) -> np.ndarray:
        return -self.model.decision_function(matrix)

    def calibrate(self, calibration: np.ndarray) -> None:
        matrix = _validated_matrix(calibration, len(self.features), "calibration data")
        if self.reference_values is None:
            raise RuntimeError("isolation forest is not fitted")
        self.threshold = float(np.quantile(self._score(matrix), self.calibration_quantile))
        buffer = io.BytesIO()
        joblib.dump(self.model, buffer, compress=0)
        identity = {
            "identity": self.identity,
            "features": self.features,
            "seed": self.seed,
            "estimators": self.estimators,
            "calibration_quantile": self.calibration_quantile,
            "effective_threshold": self.threshold,
            "reference": self.reference_baseline,
            "model_sha256": sha256_hex(buffer.getvalue()),
        }
        self.artifact_hash = sha256_hex(canonical_json(identity))

    def score_one(self, values: np.ndarray, *, update_reference: bool = True) -> DetectionResult:
        if self.threshold is None or self.reference_values is None:
            raise RuntimeError("isolation forest must be fitted and calibrated before scoring")
        row = np.asarray(values, dtype=float)
        if row.shape != (len(self.features),) or not np.isfinite(row).all():
            raise ValueError("runtime row has invalid shape or non-finite values")
        score = float(self._score(row.reshape(1, -1))[0])
        if not np.isfinite(score):
            raise ValueError("isolation forest produced a non-finite score")
        contributions: list[dict[str, Any]] = []
        feasible: list[dict[str, Any]] = []
        for index, feature in enumerate(self.features):
            replaced = row.copy()
            replaced[index] = self.reference_values[index]
            replacement_score = float(self._score(replaced.reshape(1, -1))[0])
            if not np.isfinite(replacement_score):
                raise ValueError("isolation forest produced a non-finite sensitivity score")
            sensitivity = score - replacement_score
            item = {
                "feature": feature,
                "actual_value": float(row[index]),
                "approved_reference_value": float(self.reference_values[index]),
                "actual_score": score,
                "replacement_score": replacement_score,
                "model_sensitivity": sensitivity,
                "interpretation": "actual-model sensitivity; not a causal effect",
            }
            contributions.append(item)
            if replacement_score <= self.threshold:
                feasible.append(item)
        contributions.sort(key=lambda item: abs(float(item["model_sensitivity"])), reverse=True)
        feasible.sort(key=lambda item: float(item["replacement_score"]))
        counterfactual: dict[str, Any]
        if feasible:
            best = feasible[0]
            counterfactual = {
                "feature": best["feature"],
                "replace_with_approved_reference": best["approved_reference_value"],
                "rescored_actual_model": best["replacement_score"],
                "result": "below_or_equal_to_threshold",
                "limits": "single-feature model sensitivity; not causal or operational advice",
            }
        else:
            counterfactual = {
                "result": "no_single_feature_reference_replacement_crossed_threshold",
                "limits": (
                    "absence of a single-feature result does not prove no feasible response exists"
                ),
            }
        return DetectionResult(
            score=score,
            threshold=self.threshold,
            anomaly=score > self.threshold,
            detector_evidence={
                "method": "Isolation Forest",
                "score": score,
                "threshold": self.threshold,
                "margin": score - self.threshold,
                "training_reference_range": self.reference_baseline,
                "sensitivity_method": (
                    "replace one feature with its approved training reference and rescore "
                    "the actual model"
                ),
                "score_semantics": "model anomaly score; not probability or confidence",
            },
            reference_baseline=self.reference_baseline,
            ranked_feature_contributions=tuple(contributions),
            feasible_counterfactual=counterfactual,
        )

    def update_reference(self, values: np.ndarray) -> None:
        """Isolation Forest uses its frozen fitted reference during operation."""

        _validated_matrix(
            np.asarray(values, dtype=float).reshape(1, -1),
            len(self.features),
            "reference update row",
        )


def build_detector(features: tuple[str, ...], detector: str, settings: dict[str, Any]) -> Any:
    if detector == "zscore":
        return CausalZScoreDetector(
            features,
            window=int(settings.get("window", 30)),
            calibration_quantile=float(settings.get("calibration_quantile", 0.995)),
            minimum_threshold=float(settings.get("minimum_z_threshold", 3.0)),
            degenerate_guard=bool(settings.get("degenerate_guard", True)),
        )
    if detector == "isolation_forest":
        return IsolationForestDetector(
            features,
            seed=int(settings.get("seed", 42)),
            estimators=int(settings.get("estimators", 200)),
            calibration_quantile=float(settings.get("calibration_quantile", 0.995)),
        )
    raise ValueError(f"unsupported detector: {detector}")
