"""Generate an unsigned SATISH config pack for the ESA-ADB Mission1 replay.

Consumes the ``*.meta.json`` emitted by ``build_esa_dataset.py`` (feature order, subsystem
map, observed-range bounds) and writes an unsigned config mapping that satisfies
``configuration.validate_unsigned_config``. Sign it with:

    python -m satish_commercial.cli config sign esa-config.unsigned.json \
        --private-key keys/demo-private.pem --output signed-evaluation-config.json

The physical bounds are an observed-range envelope, not a vendor or flight specification.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from satish_commercial.configuration import FIXED_RULES, validate_unsigned_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an unsigned ESA-ADB SATISH config pack")
    parser.add_argument("meta", type=Path, help="path to the *.meta.json from build_esa_dataset.py")
    parser.add_argument("--out", type=Path, required=True, help="unsigned config JSON output path")
    parser.add_argument("--author", default="esa-adapter@satish.local")
    parser.add_argument("--approver", default="reviewer@satish.local")
    parser.add_argument("--customer-id", default="esa-adb-mission1-demo")
    parser.add_argument("--window", type=int, default=10, help="z-score rolling window")
    parser.add_argument("--valid-days", type=int, default=365)
    args = parser.parse_args(argv)

    meta = json.loads(args.meta.read_text(encoding="utf-8"))
    features = [str(name) for name in meta["feature_columns"]]
    subsystem_lookup = {str(k): str(v) for k, v in meta["subsystem_lookup"].items()}
    bounds = {
        str(k): {"min": float(v["min"]), "max": float(v["max"])}
        for k, v in meta["physical_bounds"].items()
    }
    subsystems = sorted(set(subsystem_lookup.values()))

    now = datetime.now(UTC)
    mapping = {
        "schema_version": "1.0.0",
        "pack_id": "esa-adb-mission1",
        "customer_id": args.customer_id,
        "detector": "zscore",
        "timestamp_column": "timestamp",
        "feature_columns": features,
        "subsystem_lookup": subsystem_lookup,
        "physical_bounds": bounds,
        "detector_settings": {
            "label_column": str(meta.get("label_column", "anomaly_label")),
            "window": int(args.window),
            "calibration_quantile": 0.995,
            "minimum_z_threshold": 3.0,
            "seed": 42,
            "max_gap_seconds": 600,
            "persistence_horizon": 3,
            # ESA-ADB telemetry is legitimately piecewise-constant; the degenerate-window guard
            # would flag ordinary stepping and flood alerts. Disable it for this replay and
            # accept the documented stuck-sensor blind spot of the base causal z-score.
            "degenerate_guard": False,
        },
        "risk_thresholds": {"medium": 1.0, "critical": 1.5},
        "criticality_weights": {**{name: 1.0 for name in subsystems}, "DEFAULT": 1.0},
        "mission_phase_weights": {"DEFAULT": 1.0, "OPERATIONS": 1.0},
        "deterministic_rules": [dict(rule) for rule in FIXED_RULES],
        "branding": {
            "product_name": "SATISH — ESA-ADB Mission1 replay",
            "data_provenance": "third-party ESA Anomaly Detection Benchmark (Mission1)",
            "endorsement": "not affiliated with, endorsed by, or certified by ESA",
        },
        "author": args.author,
        "independent_approver": args.approver,
        "effective_at": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(days=args.valid_days)).isoformat().replace("+00:00", "Z"),
        "second_person_review": True,
    }

    validate_unsigned_config(mapping)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"unsigned_config": str(args.out), "features": len(features)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
