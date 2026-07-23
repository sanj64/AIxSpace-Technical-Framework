"""Historical replay pipeline implementing the commercial advisory safety boundary."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .audit import AuditLog
from .contracts import (
    Action,
    ConfigPackV1,
    Disposition,
    ExplanationPacketV1,
    RecommendationRecordV1,
    RiskLevel,
    RiskPacketV1,
    RunManifestV1,
    SystemMode,
    canonical_json,
    sha256_hex,
    to_dict,
    utc_now,
)
from .detectors import build_detector, feature_schema_hash
from .evaluation import evaluate_predictions, grouped_metrics
from .policy import RULE_SET_VERSION, decide
from .processing import AdvisoryProcessor
from .quality import FrameQualityResult, assess_frame


@dataclass(slots=True)
class ReplayResult:
    output_directory: Path
    manifest: RunManifestV1
    risk_packets: list[RiskPacketV1]
    explanations: list[ExplanationPacketV1]
    recommendations: list[RecommendationRecordV1]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strict_chronological_boundaries(row_count: int) -> tuple[int, int]:
    if row_count < 15:
        raise ValueError("at least 15 chronological rows are required for replay evaluation")
    train_end = int(row_count * 0.60)
    calibration_end = int(row_count * 0.80)
    if not 0 < train_end < calibration_end < row_count:
        raise ValueError("could not create non-empty train/calibration/test partitions")
    return train_end, calibration_end


def _new_output_directory(target: Path) -> Path:
    if target.exists():
        if any(target.iterdir()):
            raise FileExistsError(
                f"output directory {target} is not empty; choose a new directory to "
                "prevent stale evidence"
            )
        target.rmdir()
    staging = target.with_name(f".{target.name}.staging-{uuid.uuid4().hex}")
    staging.mkdir(parents=True, exist_ok=False)
    return staging


def _write_jsonl(path: Path, records: list[Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(to_dict(record), sort_keys=True, separators=(",", ":")) + "\n")


def _identity(prefix: str, run_id: str, index: int) -> str:
    return f"{prefix}-{sha256_hex(f'{run_id}:{index}:{prefix}'.encode())[:20]}"


def _quality_mode(row: pd.Series) -> tuple[SystemMode, tuple[str, ...]]:
    flags = tuple(row.get("_quality_flags", ()))
    mode = SystemMode(str(row.get("_system_mode", SystemMode.NORMAL.value)))
    return mode, flags


def _degraded_failure_run(
    *,
    staging: Path,
    output_directory: Path,
    config: ConfigPackV1,
    audit_private_key: Ed25519PrivateKey,
    reasons: tuple[str, ...],
    dataset_id: str,
    dataset_hash: str,
    dataset_license: str,
    code_commit: str,
    sbom_hash: str,
    quality: FrameQualityResult,
) -> ReplayResult:
    """Emit a signed ALERT_ONLY record when a prerequisite prevents detector execution."""

    failure_artifact = staging / "detector-unavailable.json"
    failure_artifact.write_text(
        json.dumps(
            {"detector": config.detector, "status": "UNAVAILABLE", "failed_prerequisites": reasons},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    artifact_hash = file_sha256(failure_artifact)
    feature_hash = feature_schema_hash(config.feature_columns)
    run_id = sha256_hex(
        canonical_json(
            {
                "dataset_hash": dataset_hash,
                "config_hash": config.pack_hash,
                "artifact_hash": artifact_hash,
                "degraded_reasons": reasons,
            }
        )
    )[:24]
    decision = decide(mode=SystemMode.DEGRADED, anomaly=False, risk_level=RiskLevel.NONE)
    packet = RiskPacketV1(
        schema_version="1.0.0",
        packet_id=_identity("risk", run_id, 0),
        run_id=run_id,
        event_id=f"{run_id}-prerequisite-failure",
        timestamp=utc_now(),
        subsystem="UNRESOLVED",
        detector_identity=f"{config.detector}:unavailable",
        artifact_hash=artifact_hash,
        config_hash=config.pack_hash,
        feature_schema_hash=feature_hash,
        score=None,
        threshold=None,
        margin=None,
        anomaly=False,
        data_quality_flags=tuple(sorted(set(reasons))),
        system_mode=SystemMode.DEGRADED,
    )
    explanation = ExplanationPacketV1(
        schema_version="1.0.0",
        explanation_id=_identity("explanation", run_id, 0),
        risk_packet_id=packet.packet_id,
        detector_evidence={
            "result": "not_available",
            "failed_prerequisites": reasons,
            "score_semantics": "no score was produced",
        },
        reference_baseline={},
        ranked_feature_contributions=(),
        risk_factor_decomposition={
            "risk_level": "NONE",
            "risk_value": 0.0,
            "limits": "risk was not calculated because detector prerequisites failed",
        },
        deterministic_policy_trace=decision.trace,
        feasible_counterfactual={
            "result": "repair_failed_prerequisite",
            "failed_prerequisites": reasons,
        },
        limitations=(
            "DEGRADED mode: detector and risk interpretation are unavailable.",
            "ALERT_ONLY is advisory; no command was or can be transmitted.",
        ),
        explanation_implementation_version="satish-xai:1.0.0",
    )
    recommendation = RecommendationRecordV1(
        schema_version="1.0.0",
        recommendation_id=_identity("recommendation", run_id, 0),
        risk_packet_id=packet.packet_id,
        explanation_id=explanation.explanation_id,
        action=Action.ALERT_ONLY,
        rule_set_version=RULE_SET_VERSION,
        rule_ids=("SYS-001",),
    )
    risk_path = staging / "risk-packets.jsonl"
    explanation_path = staging / "explanation-packets.jsonl"
    recommendation_path = staging / "recommendations.jsonl"
    _write_jsonl(risk_path, [packet])
    _write_jsonl(explanation_path, [explanation])
    _write_jsonl(recommendation_path, [recommendation])
    quality_path = staging / "quality-report.json"
    quality_path.write_text(
        json.dumps(
            {
                "global_flags": reasons,
                "imputations": quality.imputations,
                "dropped_signals": quality.dropped_signals,
                "causal_preprocessing": True,
                "future_value_backfill": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = RunManifestV1(
        schema_version="1.0.0",
        run_id=run_id,
        created_at=utc_now(),
        dataset_ids=(
            {"dataset_id": dataset_id, "sha256": dataset_hash, "license": dataset_license},
        ),
        split_boundaries={"status": "not_created", "reason": "failed prerequisite"},
        code_commit=code_commit,
        environment={
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "network_required": "false",
        },
        sbom_hash=sbom_hash,
        artifact_hash=artifact_hash,
        config_pack_hash=config.pack_hash,
        feature_schema_hash=feature_hash,
        seed=int(config.detector_settings.get("seed", 42)),
        metrics={
            "status": "not_computed",
            "failed_prerequisites": reasons,
            "second_person_review_required": config.second_person_review,
        },
        generated_output_hashes={
            path.name: file_sha256(path)
            for path in (
                failure_artifact,
                risk_path,
                explanation_path,
                recommendation_path,
                quality_path,
            )
        },
    )
    (staging / "run-manifest.json").write_text(
        json.dumps(to_dict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    audit = AuditLog(staging / "audit.jsonl", audit_private_key)
    audit.append(
        "DEGRADED_RECOMMENDATION_CREATED",
        {
            "risk_packet": to_dict(packet),
            "explanation_packet": to_dict(explanation),
            "recommendation": to_dict(recommendation),
            "manifest": to_dict(manifest),
        },
    )
    os.replace(staging, output_directory)
    return ReplayResult(output_directory, manifest, [packet], [explanation], [recommendation])


def run_replay(
    frame: pd.DataFrame,
    config: ConfigPackV1,
    *,
    output_directory: Path,
    audit_private_key: Ed25519PrivateKey,
    dataset_id: str,
    dataset_hash: str,
    dataset_license: str,
    code_commit: str,
    sbom_hash: str,
) -> ReplayResult:
    """Run a strict 60/20/20 replay; models never fit on calibration or test rows."""

    staging = _new_output_directory(output_directory)
    try:
        quality = assess_frame(frame, config)
        if quality.global_flags:
            return _degraded_failure_run(
                staging=staging,
                output_directory=output_directory,
                config=config,
                audit_private_key=audit_private_key,
                reasons=quality.global_flags,
                dataset_id=dataset_id,
                dataset_hash=dataset_hash,
                dataset_license=dataset_license,
                code_commit=code_commit,
                sbom_hash=sbom_hash,
                quality=quality,
            )
        working = quality.frame
        train_end, calibration_end = strict_chronological_boundaries(len(working))
        label_column = str(config.detector_settings["label_column"])
        if label_column not in working.columns:
            return _degraded_failure_run(
                staging=staging,
                output_directory=output_directory,
                config=config,
                audit_private_key=audit_private_key,
                reasons=(f"missing_label_channel:{label_column}",),
                dataset_id=dataset_id,
                dataset_hash=dataset_hash,
                dataset_license=dataset_license,
                code_commit=code_commit,
                sbom_hash=sbom_hash,
                quality=quality,
            )
        labels = pd.to_numeric(working[label_column], errors="coerce")
        if labels.isna().any() or not set(labels.unique()).issubset({0, 1}):
            raise ValueError("label column must contain only binary 0/1 values")

        train_frame = working.iloc[:train_end]
        calibration_frame = working.iloc[train_end:calibration_end]
        test_frame = working.iloc[calibration_end:].reset_index(drop=True)
        clean_train = train_frame[
            (labels.iloc[:train_end].to_numpy() == 0)
            & (train_frame["_system_mode"].to_numpy() == SystemMode.NORMAL.value)
        ]
        clean_calibration = calibration_frame[
            (labels.iloc[train_end:calibration_end].to_numpy() == 0)
            & (calibration_frame["_system_mode"].to_numpy() == SystemMode.NORMAL.value)
        ]
        if clean_train.empty or clean_calibration.empty:
            raise ValueError("normal-only training or independent calibration partition is empty")

        detector = build_detector(config.feature_columns, config.detector, config.detector_settings)
        detector.fit(clean_train.loc[:, config.feature_columns].to_numpy(dtype=float))
        detector.calibrate(clean_calibration.loc[:, config.feature_columns].to_numpy(dtype=float))
        artifact_path = staging / "detector-artifact.joblib"
        joblib.dump(detector, artifact_path, compress=3)
        artifact_hash = file_sha256(artifact_path)
        detector = joblib.load(artifact_path)
        if file_sha256(artifact_path) != artifact_hash:
            raise RuntimeError("artifact changed between calibration and replay")

        feature_hash = feature_schema_hash(config.feature_columns)
        run_id = sha256_hex(
            canonical_json(
                {
                    "dataset_hash": dataset_hash,
                    "config_hash": config.pack_hash,
                    "artifact_hash": artifact_hash,
                    "seed": int(config.detector_settings.get("seed", 42)),
                }
            )
        )[:24]
        audit = AuditLog(staging / "audit.jsonl", audit_private_key)
        audit.append(
            "RUN_STARTED",
            {
                "run_id": run_id,
                "dataset_id": dataset_id,
                "dataset_hash": dataset_hash,
                "config_pack_hash": config.pack_hash,
                "artifact_hash": artifact_hash,
                "advisory_only": True,
            },
        )

        packets: list[RiskPacketV1] = []
        explanations: list[ExplanationPacketV1] = []
        recommendations: list[RecommendationRecordV1] = []
        scores: list[float] = []
        predictions: list[bool] = []
        processor = AdvisoryProcessor(
            config=config,
            detector=detector,
            artifact_hash=artifact_hash,
            feature_schema_hash=feature_hash,
            run_id=run_id,
            evidence_scope="historical replay data",
        )

        for index, row in test_frame.iterrows():
            mode, quality_flags = _quality_mode(row)
            processed = processor.process(
                row,
                index=int(index),
                mode=mode,
                quality_flags=quality_flags,
            )
            packet = processed.risk_packet
            explanation = processed.explanation
            recommendation = processed.recommendation
            packets.append(packet)
            explanations.append(explanation)
            recommendations.append(recommendation)
            scores.append(float(packet.score) if packet.score is not None else float("-inf"))
            predictions.append(packet.anomaly)
            audit.append(
                "RECOMMENDATION_CREATED",
                {
                    "risk_packet": to_dict(packet),
                    "explanation_packet": to_dict(explanation),
                    "recommendation": to_dict(recommendation),
                },
            )

        risk_path = staging / "risk-packets.jsonl"
        explanation_path = staging / "explanation-packets.jsonl"
        recommendation_path = staging / "recommendations.jsonl"
        _write_jsonl(risk_path, packets)
        _write_jsonl(explanation_path, explanations)
        _write_jsonl(recommendation_path, recommendations)

        test_labels = labels.iloc[calibration_end:].to_numpy(dtype=int)
        finite_scores = np.asarray(scores, dtype=float)
        if not np.isfinite(finite_scores).all():
            finite_scores = np.where(np.isfinite(finite_scores), finite_scores, -1e308)
        metrics = evaluate_predictions(
            test_labels,
            np.asarray(predictions),
            finite_scores,
            test_frame[config.timestamp_column],
            rare_nominal=(
                test_frame["rare_nominal"].astype(bool).to_numpy()
                if "rare_nominal" in test_frame.columns
                else None
            ),
        )
        metrics["by_dimension"] = grouped_metrics(
            test_frame,
            test_labels,
            np.asarray(predictions),
            finite_scores,
            config.timestamp_column,
        )
        metrics["evidence_label"] = "historical replay evaluation"
        metrics["training_rows"] = len(train_frame)
        metrics["normal_training_rows_used"] = len(clean_train)
        metrics["calibration_rows"] = len(calibration_frame)
        metrics["normal_calibration_rows_used"] = len(clean_calibration)
        metrics["test_rows_untouched"] = len(test_frame)
        metrics["second_person_review_required"] = config.second_person_review

        quality_path = staging / "quality-report.json"
        quality_path.write_text(
            json.dumps(
                {
                    "global_flags": quality.global_flags,
                    "imputations": quality.imputations,
                    "dropped_signals": quality.dropped_signals,
                    "causal_preprocessing": True,
                    "future_value_backfill": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        generated_hashes = {
            path.name: file_sha256(path)
            for path in (
                artifact_path,
                risk_path,
                explanation_path,
                recommendation_path,
                quality_path,
            )
        }
        manifest = RunManifestV1(
            schema_version="1.0.0",
            run_id=run_id,
            created_at=utc_now(),
            dataset_ids=(
                {
                    "dataset_id": dataset_id,
                    "sha256": dataset_hash,
                    "license": dataset_license,
                    "modification_notice": (
                        "input was sorted chronologically; causal imputations are listed "
                        "in quality-report.json"
                    ),
                },
            ),
            split_boundaries={
                "method": "chronological_60_20_20",
                "train": [0, train_end],
                "calibration": [train_end, calibration_end],
                "test": [calibration_end, len(working)],
                "effective_row_count": len(working),
            },
            code_commit=code_commit,
            environment={
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "network_required": "false",
            },
            sbom_hash=sbom_hash,
            artifact_hash=artifact_hash,
            config_pack_hash=config.pack_hash,
            feature_schema_hash=feature_hash,
            seed=int(config.detector_settings.get("seed", 42)),
            metrics=metrics,
            generated_output_hashes=generated_hashes,
        )
        manifest_path = staging / "run-manifest.json"
        manifest_path.write_text(
            json.dumps(to_dict(manifest), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        audit.append("RUN_MANIFEST_CREATED", {"manifest": to_dict(manifest)})
        os.replace(staging, output_directory)
        return ReplayResult(output_directory, manifest, packets, explanations, recommendations)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def record_disposition(
    run_directory: Path,
    recommendation_id: str,
    disposition: Disposition,
    operator_identity: str,
    reason_code: str,
    rationale: str,
    audit_private_key: Ed25519PrivateKey,
    *,
    second_reviewer_identity: str | None = None,
    require_second_reviewer: bool = False,
) -> RecommendationRecordV1:
    manifest_path = run_directory / "run-manifest.json"
    manifest_requires_second = False
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_requires_second = bool(
            manifest.get("metrics", {}).get("second_person_review_required", False)
        )
    if require_second_reviewer or manifest_requires_second:
        if not second_reviewer_identity:
            raise ValueError("this configuration requires a second reviewer")
        if second_reviewer_identity.strip() == operator_identity.strip():
            raise ValueError("the operator and second reviewer must be different people")
    path = run_directory / "recommendations.jsonl"
    mappings = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    updated: RecommendationRecordV1 | None = None
    for index, item in enumerate(mappings):
        if item["recommendation_id"] != recommendation_id:
            continue
        current = RecommendationRecordV1(
            schema_version=item["schema_version"],
            recommendation_id=item["recommendation_id"],
            risk_packet_id=item["risk_packet_id"],
            explanation_id=item["explanation_id"],
            action=Action(item["action"]),
            rule_set_version=item["rule_set_version"],
            rule_ids=tuple(item["rule_ids"]),
            disposition=Disposition(item["disposition"]),
            operator_identity=item.get("operator_identity"),
            disposition_timestamp=item.get("disposition_timestamp"),
            reason_code=item.get("reason_code"),
            rationale=item.get("rationale"),
            second_reviewer_identity=item.get("second_reviewer_identity"),
        )
        if current.disposition is not Disposition.PENDING:
            raise ValueError("recommendation has already been disposed")
        updated = current.disposed(
            disposition,
            operator_identity,
            reason_code,
            rationale,
            second_reviewer_identity=second_reviewer_identity,
        )
        mappings[index] = to_dict(updated)
        break
    if updated is None:
        raise KeyError(f"recommendation not found: {recommendation_id}")
    temporary = path.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in mappings
        ),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    AuditLog(run_directory / "audit.jsonl", audit_private_key).append(
        "HUMAN_DISPOSITION_RECORDED", {"recommendation": to_dict(updated)}
    )
    return updated
