"""Fail-closed release gate evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .contracts import require_v1


@dataclass(frozen=True, slots=True)
class GateResult:
    name: str
    approved: bool
    reasons: tuple[str, ...]


def check_release_record(path: Path) -> list[GateResult]:
    mapping = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(mapping, dict):
        raise ValueError("release record must be an object")
    require_v1(str(mapping.get("schema_version", "")))
    gates = mapping.get("gates")
    if not isinstance(gates, dict) or not gates:
        raise ValueError("release record contains no gates")
    results: list[GateResult] = []
    for name, raw in gates.items():
        gate: dict[str, Any] = raw if isinstance(raw, dict) else {}
        reasons: list[str] = []
        if gate.get("status") != "APPROVED":
            reasons.append(f"status is {gate.get('status', 'MISSING')}, not APPROVED")
        approvers = gate.get("approvers", [])
        if not isinstance(approvers, list) or not approvers:
            reasons.append("no accountable approver is named")
        evidence = gate.get("evidence", [])
        if not isinstance(evidence, list) or not evidence:
            reasons.append("no evidence is attached")
        else:
            for evidence_path in evidence:
                resolved = (path.parent / str(evidence_path)).resolve()
                if not resolved.is_file():
                    reasons.append(f"evidence file is missing: {evidence_path}")
        results.append(GateResult(str(name), not reasons, tuple(reasons)))
    return results
