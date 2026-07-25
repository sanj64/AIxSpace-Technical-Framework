"""Command-line ESA reproducibility rebuild workflow."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from ad_dss.data.esa_reproducible import (
    FileEvidence,
    RebuildManifest,
    ReproducibilityError,
    compare_unverified_inputs,
    hash_outputs,
    sha256_file,
    train_mission1_xgboost_candidate,
    train_mission1_zscore,
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


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _code_commit(root: Path) -> str:
    git = shutil.which("git")
    if git is None:
        return "UNCOMMITTED"
    try:
        result = subprocess.run(
            [git, "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "UNCOMMITTED"
    return result.stdout.strip()


def _ensure_under_root(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ReproducibilityError(f"refusing to clean path outside repo root: {resolved}") from exc
    return resolved


def clean(root: Path, *, archive_generated: bool = False) -> Path:
    """Remove local generated clutter while preserving raw data and committed evidence."""
    targets = [
        root / ".pytest_cache",
        root / ".pytest-tmp",
        root / ".ruff_cache",
        root / ".mypy_cache",
        root / "build",
        root / "dist",
    ]
    targets.extend(root.glob("**/__pycache__"))
    if archive_generated:
        targets.extend((root / "artifacts").glob("esa_rebuild_tmp*"))
    removed: list[str] = []
    preserved = {
        (root / "data" / "raw" / "ESA-Mission1.zip").resolve().as_posix(),
        (root / "artifacts" / "esa_rebuild").resolve().as_posix(),
        (root / "archive").resolve().as_posix(),
    }
    for target in sorted({item for item in targets}, key=lambda value: value.as_posix()):
        if not target.exists():
            continue
        resolved = _ensure_under_root(root, target)
        if resolved.as_posix() in preserved:
            continue
        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()
        removed.append(_display_path(root, resolved))
    report = {
        "status": "clean_complete",
        "removed": removed,
        "preserved": sorted(_display_path(root, Path(item)) for item in preserved),
        "raw_esa_archive_preserved": (root / "data" / "raw" / "ESA-Mission1.zip").exists(),
        "committed_evidence_preserved": (root / "artifacts" / "esa_rebuild").exists(),
    }
    out = root / "artifacts" / "esa_rebuild" / "clean_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return out


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


def full_rebuild(
    root: Path,
    output_dir: Path,
    source_zip: Path | None,
    channel_limit: int | None,
) -> Path:
    if source_zip is None:
        source_zip = root / "data" / "raw" / "ESA-Mission1.zip"
    if not source_zip.exists():
        raise ReproducibilityError(
            "Full rebuild requires the real ESA-Mission1.zip archive at "
            f"{(root / 'data' / 'raw' / 'ESA-Mission1.zip').as_posix()} "
            "or an explicit --source-zip path. It will not use synthetic data or archived CSVs."
        )
    outputs = train_mission1_zscore(
        source_zip=source_zip,
        output_dir=output_dir,
        channel_limit=channel_limit,
    )
    generated = hash_outputs(outputs.values())
    output_hashes = {_display_path(root, Path(path)): digest for path, digest in generated.items()}
    manifest = {
        "zenodo_record": "12528696",
        "active_training_performed": True,
        "source_zip": _display_path(root, source_zip),
        "source_zip_hash": sha256_file(source_zip),
        "code_commit": _code_commit(root),
        "outputs": {key: _display_path(root, value) for key, value in outputs.items()},
        "output_hashes": output_hashes,
        "training_policy": (
            "Channelwise Z-score baseline fit on finite, non-labelled samples in the "
            "chronological training partition; thresholds calibrated on finite, non-labelled "
            "validation samples; metrics evaluated on untouched chronological test samples."
        ),
    }
    out = output_dir / "full_rebuild_manifest.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return out


def xgboost_candidate(
    root: Path,
    output_dir: Path,
    source_zip: Path | None,
    channel_limit: int | None,
    max_rows_per_partition: int,
) -> Path:
    if source_zip is None:
        source_zip = root / "data" / "raw" / "ESA-Mission1.zip"
    if not source_zip.exists():
        raise ReproducibilityError(
            "XGBoost candidate training requires the real ESA-Mission1.zip archive at "
            f"{(root / 'data' / 'raw' / 'ESA-Mission1.zip').as_posix()} "
            "or an explicit --source-zip path."
        )
    outputs = train_mission1_xgboost_candidate(
        source_zip=source_zip,
        output_dir=output_dir,
        channel_limit=channel_limit,
        max_rows_per_partition=max_rows_per_partition,
    )
    generated = hash_outputs(outputs.values())
    manifest = {
        "zenodo_record": "12528696",
        "active_training_performed": False,
        "research_candidate_trained": True,
        "status": "RESEARCH_GATED_NOT_ACTIVE_V0_9",
        "source_zip": _display_path(root, source_zip),
        "source_zip_hash": sha256_file(source_zip),
        "code_commit": _code_commit(root),
        "outputs": {key: _display_path(root, value) for key, value in outputs.items()},
        "output_hashes": {_display_path(root, Path(path)): digest for path, digest in generated.items()},
        "explanation_policy": (
            "XGBoost feature attributions are model sensitivity evidence only; they are "
            "not causal, probabilistic confidence, certainty, or flight validation claims."
        ),
        "release_gate": (
            "This candidate cannot become an active v0.9 detector unless it beats the "
            "Z-score baseline on recorded acceptance metrics and receives model-risk approval."
        ),
    }
    out = output_dir / "xgboost_candidate_manifest.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return out


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
        choices=[
            "audit",
            "verify",
            "dry-run",
            "clean",
            "full-rebuild",
            "xgboost-candidate",
            "metrics-placeholder",
        ],
    )
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output-dir", default="artifacts/esa_rebuild", help="Evidence output folder")
    parser.add_argument("--source-zip", default=None, help="Path to ESA-Mission1.zip")
    parser.add_argument(
        "--channel-limit",
        type=int,
        default=None,
        help="Optional channel limit for smoke testing; omit for all Mission 1 channels",
    )
    parser.add_argument(
        "--max-rows-per-partition",
        type=int,
        default=250_000,
        help="Deterministic cap per train/validation/test partition for XGBoost research runs",
    )
    parser.add_argument(
        "--archive-generated",
        action="store_true",
        help="Allow clean to remove temporary generated rebuild folders; committed evidence is preserved",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = (root / args.output_dir).resolve()
    if args.command == "audit":
        path = audit(root, output_dir)
    elif args.command == "verify":
        path = verify(root, output_dir)
    elif args.command == "dry-run":
        path = dry_run(root, output_dir)
    elif args.command == "clean":
        path = clean(root, archive_generated=args.archive_generated)
    elif args.command == "metrics-placeholder":
        path = write_metrics_placeholder(output_dir)
    elif args.command == "xgboost-candidate":
        source_zip = Path(args.source_zip).resolve() if args.source_zip else None
        path = xgboost_candidate(
            root,
            output_dir,
            source_zip,
            args.channel_limit,
            args.max_rows_per_partition,
        )
    else:
        source_zip = Path(args.source_zip).resolve() if args.source_zip else None
        path = full_rebuild(root, output_dir, source_zip, args.channel_limit)
    generated = hash_outputs([path])
    print(json.dumps({"output": path.as_posix(), "sha256": generated.get(path.as_posix())}, indent=2))


if __name__ == "__main__":
    main()
