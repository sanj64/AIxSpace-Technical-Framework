"""Shared single-sample advisory processing for replay and live operation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .contracts import (
    ConfigPackV1,
    Disposition,
    ExplanationPacketV1,
    RecommendationRecordV1,
    RiskPacketV1,
    SystemMode,
    sha256_hex,
    utc_now,
)
from .detectors import DetectionResult
from .policy import RULE_SET_VERSION, decide
from .risk import calculate_risk


def record_identity(prefix: str, run_id: str, index: int) -> str:
    return f"{prefix}-{sha256_hex(f'{run_id}:{index}:{prefix}'.encode())[:20]}"


@dataclass(frozen=True, slots=True)
class ProcessedSample:
    risk_packet: RiskPacketV1
    explanation: ExplanationPacketV1
    recommendation: RecommendationRecordV1


class AdvisoryProcessor:
    """Apply the approved quality/detector/risk/policy path to one ordered sample."""

    def __init__(
        self,
        *,
        config: ConfigPackV1,
        detector: Any,
        artifact_hash: str,
        feature_schema_hash: str,
        run_id: str,
        evidence_scope: str,
    ) -> None:
        self.config = config
        self.detector = detector
        self.artifact_hash = artifact_hash
        self.feature_schema_hash = feature_schema_hash
        self.run_id = run_id
        self.evidence_scope = evidence_scope
        self.consecutive_anomalies = 0

    def process(
        self,
        row: pd.Series,
        *,
        index: int,
        mode: SystemMode,
        quality_flags: tuple[str, ...] = (),
    ) -> ProcessedSample:
        detection: DetectionResult | None = None
        values: np.ndarray | None = None
        if mode is SystemMode.NORMAL:
            try:
                values = row.loc[list(self.config.feature_columns)].to_numpy(dtype=float)
                detection = self.detector.score_one(values, update_reference=False)
            except (ValueError, RuntimeError) as exc:
                mode = SystemMode.DEGRADED
                quality_flags = (
                    *quality_flags,
                    f"detector_output_failure:{type(exc).__name__}",
                )

        if detection is None:
            anomaly = False
            self.consecutive_anomalies = 0
            detector_evidence: dict[str, Any] = {
                "method": self.config.detector,
                "result": "not_available",
                "failed_prerequisites": quality_flags,
                "score_semantics": "no score was produced",
            }
            reference_baseline: dict[str, Any] = {}
            ranked: tuple[dict[str, Any], ...] = ()
            counterfactual = {
                "result": "not_available_in_degraded_mode",
                "limits": "repair the failed prerequisite before interpreting detector behavior",
            }
            score = threshold = margin = None
            subsystem = "UNRESOLVED"
        else:
            anomaly = detection.anomaly
            self.consecutive_anomalies = self.consecutive_anomalies + 1 if anomaly else 0
            detector_evidence = detection.detector_evidence
            reference_baseline = detection.reference_baseline
            ranked = detection.ranked_feature_contributions
            counterfactual = detection.feasible_counterfactual
            score = detection.score
            threshold = detection.threshold
            margin = detection.margin
            responsible_feature = (
                str(ranked[0]["feature"]) if ranked else self.config.feature_columns[0]
            )
            subsystem = self.config.subsystem_lookup[responsible_feature]
            if not anomaly and values is not None:
                self.detector.update_reference(values)

        phase = str(row.get("mission_phase", "DEFAULT"))
        phase_weight = self.config.mission_phase_weights.get(
            phase, self.config.mission_phase_weights.get("DEFAULT", 1.0)
        )
        criticality = self.config.criticality_weights.get(
            subsystem, self.config.criticality_weights.get("DEFAULT", 1.0)
        )
        risk = calculate_risk(
            anomaly=anomaly,
            consecutive_anomalies=self.consecutive_anomalies,
            criticality_weight=criticality,
            mission_phase=phase,
            mission_phase_weight=phase_weight,
            medium_threshold=self.config.risk_thresholds["medium"],
            critical_threshold=self.config.risk_thresholds["critical"],
            persistence_horizon=int(self.config.detector_settings.get("persistence_horizon", 3)),
        )
        decision = decide(mode=mode, anomaly=anomaly, risk_level=risk.level)
        raw_timestamp = row.get(self.config.timestamp_column)
        timestamp = utc_now() if pd.isna(raw_timestamp) else pd.Timestamp(raw_timestamp).isoformat()
        packet = RiskPacketV1(
            schema_version="1.0.0",
            packet_id=record_identity("risk", self.run_id, index),
            run_id=self.run_id,
            event_id=f"{self.run_id}-event-{index:08d}",
            timestamp=timestamp,
            subsystem=subsystem,
            detector_identity=self.detector.identity,
            artifact_hash=self.artifact_hash,
            config_hash=self.config.pack_hash,
            feature_schema_hash=self.feature_schema_hash,
            score=score,
            threshold=threshold,
            margin=margin,
            anomaly=anomaly,
            data_quality_flags=tuple(sorted(set(quality_flags))),
            system_mode=mode,
        )
        explanation = ExplanationPacketV1(
            schema_version="1.0.0",
            explanation_id=record_identity("explanation", self.run_id, index),
            risk_packet_id=packet.packet_id,
            detector_evidence=detector_evidence,
            reference_baseline=reference_baseline,
            ranked_feature_contributions=ranked,
            risk_factor_decomposition={**risk.decomposition, "risk_level": risk.level.value},
            deterministic_policy_trace=decision.trace,
            feasible_counterfactual=counterfactual,
            limitations=(
                "Advisory recommendation only; no command was or can be transmitted.",
                "Detector output is not probability, confidence, certainty, or causal effect.",
                (
                    "TRL 4 partial; evidence is limited to the approved "
                    f"{self.evidence_scope} and configuration."
                ),
                "Anomalous and degraded samples do not update the detector reference.",
                *(
                    ("Failed prerequisites limit this explanation; system mode is DEGRADED.",)
                    if mode is SystemMode.DEGRADED
                    else ()
                ),
            ),
            explanation_implementation_version="satish-xai:1.1.0",
        )
        recommendation = RecommendationRecordV1(
            schema_version="1.0.0",
            recommendation_id=record_identity("recommendation", self.run_id, index),
            risk_packet_id=packet.packet_id,
            explanation_id=explanation.explanation_id,
            action=decision.action,
            rule_set_version=RULE_SET_VERSION,
            rule_ids=decision.rule_ids,
            disposition=Disposition.PENDING,
        )
        return ProcessedSample(packet, explanation, recommendation)
