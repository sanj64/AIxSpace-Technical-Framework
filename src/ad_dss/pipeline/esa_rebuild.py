"""Command-line ESA reproducibility rebuild workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ad_dss.data.esa_reproducible import (
    FileEvidence,
    RebuildManifest,
    ReproducibilityError,
    compare_unverified_inputs,
    hash_outputs,
    validate_esa_layout,
    verify_archives,
)


def _relative_evidence(root: Path, evidence: list[FileEvidence]) -> list[FileEvidence]:
    relative: list[FileEvidence] = []
    for item in evidence:
        path = Path(item.path)
        try:
            display_path = path.relative_to(root).as_posix()
        except ValueError:
            display_path = path.as_posix()
        relative.append(
            FileEvidence(
                path=display_path,
                sha256=item.sha256,
                size_bytes=item.size_bytes,
                rows=item.rows,
                columns=item.columns,
            )
        )
    return relative


def audit(root: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence = _relative_evidence(root, validate_esa_layout(root))
    archive_evidence = _relative_evidence(root, verify_archives(root))
    comparisons = compare_unverified_inputs(root)
    report = {
        "zenodo_record": "12528696",
        "esa_files": [item.__dict__ for item in evidence],
        "esa_archives": [item.__dict__ for item in archive_evidence],
        "unverified_input_comparisons": comparisons,
        "conclusion": (
            "segments_clean and dataset_clean are preserved as unverified historical inputs. "
            "The active pipeline does not train from them."
        ),
    }
    out = output_dir / "provenance_audit.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return out


def verify(root: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_files = _relative_evidence(root, verify_archives(root) + validate_esa_layout(root))
    manifest = RebuildManifest(
        zenodo_record="12528696",
        source_files=source_files,
        split_boundaries=None,
        scaler_fit_partition="not fit; local ESA checkout contains metadata only",
        seed=42,
        generated_outputs={},
        limitations=[
            "This local checkout contains ESA labels, channel metadata, and telecommands only.",
            "Per-channel telemetry values required for model training are not present.",
            "No active model metrics are claimed until the full ESA telemetry payload is available.",
        ],
    )
    out = output_dir / "run_manifest.json"
    out.write_text(manifest.to_json(), encoding="utf-8")
    return out


def dry_run(root: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = verify(root, output_dir)
    try:
        manifest_display = manifest_path.relative_to(root).as_posix()
    except ValueError:
        manifest_display = manifest_path.as_posix()
    summary = {
        "status": "verified_metadata_only",
        "manifest": manifest_display,
        "active_training_performed": False,
        "reason": "complete ESA telemetry values are not present in this checkout",
    }
    out = output_dir / "dry_run_summary.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return out


def full_rebuild(root: Path, output_dir: Path) -> Path:
    telemetry_candidates = list((root / "data/raw").glob("ESA-M*/**/*channel*.pkl"))
    telemetry_candidates += list((root / "data/raw").glob("ESA-M*/**/*telemetry*.csv"))
    if not telemetry_candidates:
        verify(root, output_dir)
        raise ReproducibilityError(
            "Full ESA telemetry values are not present. "
            "Install the complete Zenodo 12528696 payload before training active models."
        )
    raise ReproducibilityError(
        "Telemetry payload detected but no active model trainer has been approved for this layout."
    )


def write_metrics_placeholder(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / "metrics_not_generated.csv"
    pd.DataFrame(
        [
            {
                "metric": "active_model_metrics",
                "value": "not_generated",
                "reason": "complete verified ESA telemetry payload required",
            }
        ]
    ).to_csv(out, index=False)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="ESA reproducibility rebuild workflow")
    parser.add_argument(
        "command",
        choices=["audit", "verify", "dry-run", "full-rebuild", "metrics-placeholder"],
    )
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output-dir", default="artifacts/esa_rebuild", help="Evidence output folder")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = (root / args.output_dir).resolve()
    if args.command == "audit":
        path = audit(root, output_dir)
    elif args.command == "verify":
        path = verify(root, output_dir)
    elif args.command == "dry-run":
        path = dry_run(root, output_dir)
    elif args.command == "metrics-placeholder":
        path = write_metrics_placeholder(output_dir)
    else:
        path = full_rebuild(root, output_dir)
    generated = hash_outputs([path])
    print(json.dumps({"output": path.as_posix(), "sha256": generated.get(path.as_posix())}, indent=2))


if __name__ == "__main__":
    main()
