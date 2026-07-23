"""Loopback-only synthetic telemetry service using the commercial advisory processor."""

from __future__ import annotations

import argparse
import copy
import json
import math
import queue
import secrets
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import joblib
import numpy as np
import pandas as pd

from .audit import AuditLog
from .configuration import load_config
from .contracts import (
    LiveControlV1,
    LiveMonitorUpdateV1,
    LiveTelemetrySampleV1,
    SystemMode,
    require_v1,
    sha256_hex,
    to_dict,
    utc_now,
)
from .detectors import CausalZScoreDetector, feature_schema_hash
from .pipeline import file_sha256
from .processing import AdvisoryProcessor
from .quality import assess_sample
from .signing import load_private_key

ALLOWED_SCENARIOS = {
    "normal",
    "thermal_rise",
    "voltage_sag",
    "payload_spike",
    "missing_channel",
    "stale_stream",
}
ALLOWED_SPEEDS = {0.5, 1.0, 2.0}
LIVE_SCHEMA_VERSION = "1.0.0"
# Provenance labels stamped into every sample, audit entry, snapshot, and checkpoint so the
# stream never misrepresents its source. Synthetic is the default; recorded replay is opt-in.
SYNTHETIC_SOURCE = "seeded_synthetic_local"
REPLAY_SOURCE = "esa_adb_mission1_replay"
SYNTHETIC_EVIDENCE_SCOPE = "local synthetic live stream"
REPLAY_EVIDENCE_SCOPE = "ESA-ADB Mission1 historical replay"


def _append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(to_dict(value), sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    staging = path.with_suffix(path.suffix + ".tmp")
    staging.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    staging.replace(path)


def recover_interrupted_sessions(output_root: Path, private_key: Any) -> list[str]:
    """Close clean checkpoints left ACTIVE by an interrupted local process."""
    recovered: list[str] = []
    if not output_root.is_dir():
        return recovered
    for session_directory in sorted(output_root.glob("live-*")):
        checkpoint_path = session_directory / "live-session.json"
        manifest_path = session_directory / "run-manifest.json"
        if (
            not session_directory.is_dir()
            or manifest_path.exists()
            or not checkpoint_path.is_file()
        ):
            continue
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("status") != "ACTIVE":
            continue
        session_id = str(checkpoint.get("session_id", ""))
        if session_id != session_directory.name:
            continue
        audit_path = session_directory / "audit.jsonl"
        AuditLog(audit_path, private_key).append(
            "LIVE_SESSION_INTERRUPTED_RECOVERED",
            {
                "session_id": session_id,
                "sample_count": int(checkpoint.get("sample_count", 0)),
                "reason": "previous local process ended without normal shutdown",
            },
        )
        files = [
            "telemetry.jsonl",
            "risk-packets.jsonl",
            "explanation-packets.jsonl",
            "recommendations.jsonl",
            "audit.jsonl",
        ]
        checkpoint.update(
            {
                "status": "INTERRUPTED",
                "updated_at": utc_now(),
                "recovery_reason": "previous local process ended without normal shutdown",
                "generated_output_hashes": {
                    name: file_sha256(session_directory / name)
                    for name in files
                    if (session_directory / name).is_file()
                },
            }
        )
        _write_json_atomic(checkpoint_path, checkpoint)
        _write_json_atomic(manifest_path, checkpoint)
        recovered.append(session_id)
    return recovered


class SyntheticTelemetryGenerator:
    def __init__(
        self,
        features: tuple[str, ...],
        seed: int = 42,
        *,
        baselines: dict[str, float] | None = None,
        noise_scales: dict[str, float] | None = None,
    ) -> None:
        self.features = features
        self.seed = seed
        self.source = SYNTHETIC_SOURCE
        self.baselines = baselines or {}
        self.noise_scales = noise_scales or {}
        self.rng = np.random.default_rng(seed)
        self.logical_time = datetime.now(UTC).replace(microsecond=0)
        self.step = 0
        self.scenario = "normal"
        self.injection_remaining = 0

    @property
    def available_scenarios(self) -> list[str]:
        return sorted(ALLOWED_SCENARIOS)

    def reset(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self.logical_time = datetime.now(UTC).replace(microsecond=0)
        self.step = 0
        self.scenario = "normal"
        self.injection_remaining = 0

    def select(self, scenario: str) -> None:
        if scenario not in ALLOWED_SCENARIOS:
            raise ValueError("unsupported synthetic scenario")
        self.scenario = scenario

    def inject(self) -> None:
        if self.scenario == "normal":
            raise ValueError("select a non-normal scenario before injection")
        self.injection_remaining = (
            8 if self.scenario not in {"missing_channel", "stale_stream"} else 1
        )

    def next_sample(self, sequence: int) -> LiveTelemetrySampleV1:
        self.step += 1
        self.logical_time += timedelta(seconds=1)
        phase = self.step / 9.0
        values: dict[str, float | None] = {}
        defaults = {
            "battery_temperature_c": 21.0,
            "bus_voltage_v": 28.2,
            "payload_current_a": 5.4,
        }
        for index, feature in enumerate(self.features):
            baseline = self.baselines.get(feature, defaults.get(feature, 10.0 + index))
            scale = self.noise_scales.get(feature, 0.025)
            periodic = scale * 0.2 * math.sin(phase * (0.7 + index * 0.1))
            values[feature] = float(baseline + periodic + self.rng.normal(0.0, scale))

        active = self.injection_remaining > 0
        progress = 8 - self.injection_remaining if active else 0
        if active and self.scenario == "thermal_rise" and "battery_temperature_c" in values:
            values["battery_temperature_c"] = float(
                self.baselines.get("battery_temperature_c", 21.0) + 6.0 + progress * 4.5
            )
        elif active and self.scenario == "voltage_sag" and "bus_voltage_v" in values:
            values["bus_voltage_v"] = float(
                self.baselines.get("bus_voltage_v", 28.2) - 1.0 - progress * 0.5
            )
        elif active and self.scenario == "payload_spike" and "payload_current_a" in values:
            values["payload_current_a"] = float(
                self.baselines.get("payload_current_a", 5.4) + 1.5 + progress * 0.8
            )
        elif active and self.scenario == "missing_channel":
            values.pop(self.features[0], None)
        elif active and self.scenario == "stale_stream":
            self.logical_time += timedelta(seconds=301)

        if active:
            self.injection_remaining -= 1
        return LiveTelemetrySampleV1(
            schema_version=LIVE_SCHEMA_VERSION,
            sequence=sequence,
            timestamp=self.logical_time.isoformat().replace("+00:00", "Z"),
            source=self.source,
            mission_phase="COMMISSIONING",
            channel_order=self.features,
            channel_values=values,
        )


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


INJECTED_SCENARIO = "injected_demonstration_excursion"
_INJECTION_LENGTH = 8
# The labelled demonstration excursion overshoots the observed range by this fraction of the
# span so the z-score clearly exceeds the calibrated threshold regardless of local variance.
# The config's physical-bounds envelope is widened to keep the injected value in-bounds (real
# telemetry never reaches there, so real-data quality handling is unchanged).
_INJECTION_OVERSHOOT = 1.0


class ReplayTelemetrySource:
    """Stream a pre-aligned recorded telemetry frame as live samples (no synthesis).

    Emitted values are the recorded third-party telemetry replayed in original order; only
    the displayed clock is advanced by one window span on each loop wrap so timestamps stay
    strictly monotonic for the causal quality layer. Recorded data carries its own labelled
    events, so scenario *selection* is disabled; an operator may inject a single, clearly
    labelled demonstration excursion (an in-range step on one channel) to exercise the
    detector and explanation path — it is never presented as a real recorded anomaly.
    """

    def __init__(
        self,
        features: tuple[str, ...],
        frame: pd.DataFrame,
        *,
        source: str = REPLAY_SOURCE,
        timestamp_column: str = "timestamp",
        mission_phase_column: str = "mission_phase",
        seed: int = 0,
    ) -> None:
        self.features = features
        self.source = source
        self.seed = seed
        self.scenario = "recorded_replay"
        timestamps = list(pd.to_datetime(frame[timestamp_column], utc=True))
        if not timestamps:
            raise ValueError("replay telemetry frame is empty")
        step = timestamps[1] - timestamps[0] if len(timestamps) > 1 else timedelta(seconds=1)
        self._timestamps = timestamps
        self._span = (timestamps[-1] - timestamps[0]) + step
        records = frame.to_dict("records")
        self._values = [
            {feature: _finite_or_none(record.get(feature)) for feature in features}
            for record in records
        ]
        self._phases = [str(record.get(mission_phase_column, "OPERATIONS")) for record in records]
        self._cursor = 0
        self._cycle = 0
        # Precompute a per-channel in-range excursion target (near the observed maximum) for
        # the labelled demonstration injection, and pick the highest-variance channel so the
        # z-score responds clearly. Values are drawn from the channel's own recorded range, so
        # the injected sample stays inside the physical-bounds envelope.
        self._injection_remaining = 0
        self._injection_channel = features[0]
        self._injection_low = 0.0
        self._injection_high = 1.0
        best_variance = -1.0
        for feature in features:
            column = np.array(
                [value[feature] for value in self._values if value[feature] is not None],
                dtype=float,
            )
            if column.size == 0:
                continue
            variance = float(np.var(column))
            if variance > best_variance:
                best_variance = variance
                self._injection_channel = feature
                self._injection_low = float(np.min(column))
                self._injection_high = float(np.max(column))

    @property
    def available_scenarios(self) -> list[str]:
        return []

    def reset(self) -> None:
        self._cursor = 0
        self._cycle = 0
        self._injection_remaining = 0
        self.scenario = "recorded_replay"

    def select(self, scenario: str) -> None:
        raise ValueError("scenario selection is not available for recorded replay")

    def inject(self) -> None:
        """Arm a short, clearly labelled demonstration excursion on one channel."""

        self._injection_remaining = _INJECTION_LENGTH

    def next_sample(self, sequence: int) -> LiveTelemetrySampleV1:
        index = self._cursor
        stamp = self._timestamps[index] + self._span * self._cycle
        values = dict(self._values[index])
        if self._injection_remaining > 0:
            # Overlay a clearly labelled, in-range demonstration excursion: drive the channel to
            # whichever observed extreme is farther from its current value, guaranteeing a large
            # deviation from the rolling reference whenever the operator triggers it. The value
            # stays inside the channel's own recorded range (hence the physical-bounds envelope),
            # and the scenario label rides on stream_health so the UI marks it injected.
            current = values.get(self._injection_channel)
            midpoint = (self._injection_low + self._injection_high) / 2.0
            span = max(self._injection_high - self._injection_low, 1e-9)
            values[self._injection_channel] = (
                self._injection_high + _INJECTION_OVERSHOOT * span
                if current is None or current <= midpoint
                else self._injection_low - _INJECTION_OVERSHOOT * span
            )
            self.scenario = INJECTED_SCENARIO
            self._injection_remaining -= 1
        else:
            self.scenario = "recorded_replay"
        sample = LiveTelemetrySampleV1(
            schema_version=LIVE_SCHEMA_VERSION,
            sequence=sequence,
            timestamp=stamp.isoformat().replace("+00:00", "Z"),
            source=self.source,
            mission_phase=self._phases[index],
            channel_order=self.features,
            channel_values=values,
        )
        self._cursor += 1
        if self._cursor >= len(self._timestamps):
            self._cursor = 0
            self._cycle += 1
        return sample


class LiveSessionEngine:
    def __init__(
        self,
        *,
        evidence_directory: Path,
        config_path: Path,
        public_key_path: Path,
        private_key_path: Path,
        artifact_path: Path,
        manifest_path: Path,
        output_root: Path,
        telemetry_path: Path | None = None,
    ) -> None:
        self.config = load_config(config_path, public_key_path)
        if self.config.detector != "zscore":
            raise ValueError("live evaluation currently requires the approved zscore detector")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_hash = file_sha256(artifact_path)
        expected_feature_hash = feature_schema_hash(self.config.feature_columns)
        failures: list[str] = []
        if artifact_hash != str(manifest.get("artifact_hash", "")):
            failures.append("artifact_hash_mismatch")
        if self.config.pack_hash != str(manifest.get("config_pack_hash", "")):
            failures.append("config_hash_mismatch")
        if expected_feature_hash != str(manifest.get("feature_schema_hash", "")):
            failures.append("feature_schema_hash_mismatch")
        detector = joblib.load(artifact_path)
        if not isinstance(detector, CausalZScoreDetector):
            failures.append("detector_type_mismatch")
        if failures:
            raise ValueError("live prerequisite verification failed: " + ", ".join(failures))

        self.evidence_directory = evidence_directory
        self.artifact_path = artifact_path
        self.artifact_hash = artifact_hash
        self.feature_hash = expected_feature_hash
        self.detector_template = detector
        self.output_root = output_root
        self.private_key = load_private_key(private_key_path)
        recover_interrupted_sessions(self.output_root, self.private_key)
        self.session_id = (
            f"live-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
        )
        self.run_id = sha256_hex(
            f"{self.session_id}:{artifact_hash}:{self.config.pack_hash}".encode()
        )[:24]
        self.session_directory = output_root / self.session_id
        self.session_directory.mkdir(parents=True, exist_ok=False)
        self.audit = AuditLog(self.session_directory / "audit.jsonl", self.private_key)
        self.generator: SyntheticTelemetryGenerator | ReplayTelemetrySource
        if telemetry_path is not None:
            self.generator = ReplayTelemetrySource(
                self.config.feature_columns,
                pd.read_csv(telemetry_path),
                timestamp_column=self.config.timestamp_column,
                seed=int(self.config.detector_settings.get("seed", 42)),
            )
            self.evidence_scope = REPLAY_EVIDENCE_SCOPE
        else:
            calibration_tail = np.vstack(detector._history)
            baselines = {
                feature: float(calibration_tail[:, index].mean())
                for index, feature in enumerate(self.config.feature_columns)
            }
            noise_scales = {
                feature: max(float(calibration_tail[:, index].std(ddof=1)) * 0.12, 1e-4)
                for index, feature in enumerate(self.config.feature_columns)
            }
            self.generator = SyntheticTelemetryGenerator(
                self.config.feature_columns,
                seed=int(self.config.detector_settings.get("seed", 42)),
                baselines=baselines,
                noise_scales=noise_scales,
            )
            self.evidence_scope = SYNTHETIC_EVIDENCE_SCOPE
        self.source = self.generator.source
        self.processor = self._new_processor()
        self.sequence = 0
        self.previous_timestamp = None
        self.speed = 1.0
        self.paused = False
        self.started_at = utc_now()
        self.last_update: LiveMonitorUpdateV1 | None = None
        self.history: deque[LiveMonitorUpdateV1] = deque(maxlen=900)
        self.subscribers: set[queue.Queue[LiveMonitorUpdateV1]] = set()
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.finalized = False
        self.processing_ms: deque[float] = deque(maxlen=900)
        self.audit.append(
            "LIVE_SESSION_STARTED",
            {
                "session_id": self.session_id,
                "run_id": self.run_id,
                "source": self.source,
                "artifact_hash": artifact_hash,
                "config_hash": self.config.pack_hash,
                "advisory_only": True,
            },
        )
        self._write_checkpoint("ACTIVE")

    def _new_processor(self) -> AdvisoryProcessor:
        return AdvisoryProcessor(
            config=self.config,
            detector=copy.deepcopy(self.detector_template),
            artifact_hash=self.artifact_hash,
            feature_schema_hash=self.feature_hash,
            run_id=self.run_id,
            evidence_scope=self.evidence_scope,
        )

    def start(self) -> None:
        self.worker = threading.Thread(target=self._run, name="satish-live-generator", daemon=True)
        self.worker.start()

    def _run(self) -> None:
        while not self.stop_event.is_set():
            with self.lock:
                paused = self.paused
                speed = self.speed
            if not paused:
                started = time.perf_counter()
                self._tick()
                with self.lock:
                    self.processing_ms.append((time.perf_counter() - started) * 1000.0)
            self.stop_event.wait(1.0 / speed if not paused else 0.2)

    def _tick(self) -> None:
        with self.lock:
            self.sequence += 1
            sample = self.generator.next_sample(self.sequence)
            quality = assess_sample(
                timestamp=sample.timestamp,
                channel_order=sample.channel_order,
                channel_values=sample.channel_values,
                mission_phase=sample.mission_phase,
                config=self.config,
                previous_timestamp=self.previous_timestamp,
            )
            if quality.timestamp is not None and (
                self.previous_timestamp is None or quality.timestamp > self.previous_timestamp
            ):
                self.previous_timestamp = quality.timestamp
            processed = self.processor.process(
                quality.row,
                index=self.sequence,
                mode=quality.mode,
                quality_flags=quality.flags,
            )
            audit_entry = self.audit.append(
                "LIVE_RECOMMENDATION_CREATED",
                {
                    "sample": to_dict(sample),
                    "risk_packet": to_dict(processed.risk_packet),
                    "explanation_packet": to_dict(processed.explanation),
                    "recommendation": to_dict(processed.recommendation),
                },
            )
            update = LiveMonitorUpdateV1(
                schema_version=LIVE_SCHEMA_VERSION,
                session_id=self.session_id,
                sequence=self.sequence,
                emitted_at=utc_now(),
                stream_health={
                    "state": "PAUSED" if self.paused else "LIVE",
                    "source": self.source,
                    "speed": self.speed,
                    "scenario": self.generator.scenario,
                    "reference_update": (
                        "frozen"
                        if processed.risk_packet.anomaly or quality.mode is SystemMode.DEGRADED
                        else "nominal_sample_committed"
                    ),
                },
                sample=sample,
                risk_packet=processed.risk_packet,
                explanation=processed.explanation,
                recommendation=processed.recommendation,
                audit_entry_hash=str(audit_entry["entry_hash"]),
            )
            _append_jsonl(self.session_directory / "telemetry.jsonl", sample)
            _append_jsonl(self.session_directory / "risk-packets.jsonl", processed.risk_packet)
            _append_jsonl(
                self.session_directory / "explanation-packets.jsonl", processed.explanation
            )
            _append_jsonl(
                self.session_directory / "recommendations.jsonl", processed.recommendation
            )
            self.last_update = update
            self.history.append(update)
            for subscriber in tuple(self.subscribers):
                try:
                    subscriber.put_nowait(update)
                except queue.Full:
                    self.subscribers.discard(subscriber)
            self._write_checkpoint("ACTIVE")

    def subscribe(self) -> queue.Queue[LiveMonitorUpdateV1]:
        subscriber: queue.Queue[LiveMonitorUpdateV1] = queue.Queue(maxsize=32)
        with self.lock:
            self.subscribers.add(subscriber)
            if self.last_update is not None:
                subscriber.put_nowait(self.last_update)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[LiveMonitorUpdateV1]) -> None:
        with self.lock:
            self.subscribers.discard(subscriber)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "schema_version": LIVE_SCHEMA_VERSION,
                "session_id": self.session_id,
                "service_state": "STOPPING"
                if self.stop_event.is_set()
                else ("PAUSED" if self.paused else "LIVE"),
                "source": self.source,
                "artifact_hash": self.artifact_hash,
                "config_hash": self.config.pack_hash,
                "feature_schema_hash": self.feature_hash,
                "latest": to_dict(self.last_update) if self.last_update else None,
                "history": [to_dict(item) for item in self.history],
                "available_scenarios": self.generator.available_scenarios,
                "allowed_speeds": sorted(ALLOWED_SPEEDS),
            }

    def health(self) -> dict[str, Any]:
        with self.lock:
            timings = sorted(self.processing_ms)
            p95 = timings[min(len(timings) - 1, int(len(timings) * 0.95))] if timings else 0.0
            return {
                "status": "ok" if not self.stop_event.is_set() else "stopping",
                "binding": "127.0.0.1-only",
                "session_id": self.session_id,
                "sequence": self.sequence,
                "artifact_verified": True,
                "config_verified": True,
                "audit_signing": "active",
                "processing_p95_ms": round(p95, 3),
            }

    def control(self, control: LiveControlV1) -> dict[str, Any]:
        require_v1(control.schema_version)
        if control.session_id != self.session_id:
            raise ValueError("control session identifier does not match the active session")
        with self.lock:
            if control.action == "pause":
                self.paused = True
            elif control.action == "resume":
                self.paused = False
            elif control.action == "reset":
                self.generator.reset()
                self.processor = self._new_processor()
                self.previous_timestamp = None
            elif control.action == "set_speed":
                if control.speed not in ALLOWED_SPEEDS:
                    raise ValueError("speed must be 0.5, 1.0, or 2.0")
                self.speed = float(control.speed)
            elif control.action == "select_scenario":
                if control.scenario is None:
                    raise ValueError("scenario is required")
                self.generator.select(control.scenario)
            elif control.action == "inject":
                self.generator.inject()
            else:
                raise ValueError("unsupported control action")
            entry = self.audit.append("LIVE_CONTROL_APPLIED", to_dict(control))
            self._write_checkpoint("ACTIVE")
            return {
                "accepted": True,
                "action": control.action,
                "scenario": self.generator.scenario,
                "speed": self.speed,
                "paused": self.paused,
                "audit_entry_hash": entry["entry_hash"],
            }

    def _write_checkpoint(self, status: str) -> None:
        files = [
            "telemetry.jsonl",
            "risk-packets.jsonl",
            "explanation-packets.jsonl",
            "recommendations.jsonl",
            "audit.jsonl",
        ]
        hashes = {
            name: file_sha256(self.session_directory / name)
            for name in files
            if (self.session_directory / name).is_file()
        }
        checkpoint = {
            "schema_version": LIVE_SCHEMA_VERSION,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "status": status,
            "started_at": self.started_at,
            "updated_at": utc_now(),
            "source": self.source,
            "seed": self.generator.seed,
            "sample_count": self.sequence,
            "artifact_hash": self.artifact_hash,
            "config_pack_hash": self.config.pack_hash,
            "feature_schema_hash": self.feature_hash,
            "generated_output_hashes": hashes,
            "advisory_only": True,
            "command_execution": False,
        }
        _write_json_atomic(self.session_directory / "live-session.json", checkpoint)

    def finalize(self) -> None:
        with self.lock:
            if self.finalized:
                return
            self.stop_event.set()
            self.audit.append(
                "LIVE_SESSION_FINALIZED",
                {"session_id": self.session_id, "sample_count": self.sequence},
            )
            self._write_checkpoint("FINALIZED")
            manifest = json.loads(
                (self.session_directory / "live-session.json").read_text(encoding="utf-8")
            )
            _write_json_atomic(self.session_directory / "run-manifest.json", manifest)
            self.finalized = True


class LiveRequestHandler(BaseHTTPRequestHandler):
    server: LiveHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _authorized(self) -> bool:
        return self.headers.get("Authorization", "") == f"Bearer {self.server.internal_token}"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/v1/live/health":
            self._json(HTTPStatus.OK, self.server.engine.health())
            return
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        if path == "/api/v1/live/snapshot":
            self._json(HTTPStatus.OK, self.server.engine.snapshot())
        elif path == "/api/v1/live/events":
            self._events()
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _events(self) -> None:
        subscriber = self.server.engine.subscribe()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            while not self.server.engine.stop_event.is_set():
                try:
                    update = subscriber.get(timeout=10)
                    payload = json.dumps(to_dict(update), separators=(",", ":"))
                    self.wfile.write(f"id: {update.sequence}\ndata: {payload}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.server.engine.unsubscribe(subscriber)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        if path == "/api/v1/live/shutdown":
            self._json(HTTPStatus.ACCEPTED, {"accepted": True})
            threading.Thread(target=self.server.stop_cleanly, daemon=True).start()
            return
        if path != "/api/v1/live/control":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 4096:
                raise ValueError("control body size is invalid")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("control body must be an object")
            allowed = {"schema_version", "session_id", "action", "scenario", "speed"}
            unknown = sorted(set(body) - allowed)
            if unknown:
                raise ValueError("unknown control fields: " + ", ".join(unknown))
            control = LiveControlV1(
                schema_version=str(body.get("schema_version", "")),
                session_id=str(body.get("session_id", "")),
                action=str(body.get("action", "")),
                scenario=str(body["scenario"]) if body.get("scenario") is not None else None,
                speed=float(body["speed"]) if body.get("speed") is not None else None,
            )
            self._json(HTTPStatus.OK, self.server.engine.control(control))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})


class LiveHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], engine: LiveSessionEngine, token: str) -> None:
        super().__init__(address, LiveRequestHandler)
        self.engine = engine
        self.internal_token = token

    def stop_cleanly(self) -> None:
        self.engine.finalize()
        self.shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SATISH loopback-only live synthetic service")
    parser.add_argument("--evidence-directory", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--public-key", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--token", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument(
        "--telemetry",
        type=Path,
        default=None,
        help="optional pre-aligned recorded telemetry CSV to replay instead of synthesising",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.host != "127.0.0.1":
        raise ValueError("live service may bind only to 127.0.0.1")
    if len(args.token) < 24:
        raise ValueError("internal token is too short")
    evidence = args.evidence_directory.resolve()
    engine = LiveSessionEngine(
        evidence_directory=evidence,
        config_path=args.config.resolve(),
        public_key_path=args.public_key.resolve(),
        private_key_path=args.private_key.resolve(),
        artifact_path=evidence / "detector-artifact.joblib",
        manifest_path=evidence / "run-manifest.json",
        output_root=args.output_root.resolve(),
        telemetry_path=args.telemetry.resolve() if args.telemetry else None,
    )
    server = LiveHTTPServer((args.host, args.port), engine, args.token)
    engine.start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        engine.finalize()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
