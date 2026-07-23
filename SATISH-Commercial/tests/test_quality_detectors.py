from __future__ import annotations

import numpy as np
import pandas as pd

from satish_commercial.contracts import SystemMode
from satish_commercial.detectors import CausalZScoreDetector, IsolationForestDetector
from satish_commercial.quality import assess_frame


def test_preprocessing_never_backfills_from_the_future(signed_config) -> None:
    config, *_ = signed_config
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z", "2026-01-01T00:02:00Z"],
            "temperature": [np.nan, 5.0, np.nan],
            "voltage": [20.0, 20.0, 20.0],
            "anomaly_label": [0, 0, 0],
        }
    )
    result = assess_frame(frame, config)
    assert np.isnan(result.frame.loc[0, "temperature"])
    assert result.frame.loc[2, "temperature"] == 5.0
    assert result.frame.loc[0, "_system_mode"] == SystemMode.DEGRADED.value
    assert result.frame.loc[2, "_system_mode"] == SystemMode.DEGRADED.value
    assert {item["method"] for item in result.imputations} == {"causal_forward_fill"}


def test_zscore_explanation_is_exact_and_not_probability() -> None:
    train = np.column_stack([np.linspace(0, 1, 40), np.linspace(10, 11, 40)])
    calibration = np.column_stack([np.linspace(1.1, 1.4, 12), np.linspace(11.1, 11.4, 12)])
    detector = CausalZScoreDetector(
        ("a", "b"), window=10, calibration_quantile=0.9, minimum_threshold=2.0
    )
    detector.fit(train)
    detector.calibrate(calibration)
    result = detector.score_one(np.array([8.0, 11.5]))
    assert result.detector_evidence["responsible_channel"] == "a"
    assert "exact_threshold_crossing_value" in result.detector_evidence
    assert "not probability or confidence" in result.detector_evidence["score_semantics"]
    assert result.ranked_feature_contributions[0]["interpretation"].endswith("not a causal effect")


def test_isolation_forest_rescores_actual_model() -> None:
    rng = np.random.default_rng(4)
    train = rng.normal(size=(100, 2))
    calibration = rng.normal(size=(30, 2))
    detector = IsolationForestDetector(("a", "b"), seed=3, estimators=20, calibration_quantile=0.9)
    detector.fit(train)
    detector.calibrate(calibration)
    result = detector.score_one(np.array([8.0, 0.0]))
    assert result.ranked_feature_contributions
    assert all(
        item["interpretation"].endswith("not a causal effect")
        for item in result.ranked_feature_contributions
    )
    assert result.detector_evidence["sensitivity_method"].startswith("replace one feature")
