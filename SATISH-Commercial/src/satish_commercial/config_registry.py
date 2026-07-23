"""Atomic, signed configuration activation and rollback."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .audit import AuditLog
from .configuration import load_config, read_mapping
from .contracts import ConfigPackV1, utc_now


@dataclass(frozen=True, slots=True)
class RegressionResult:
    passed: bool
    evidence_hash: str
    summary: str


RegressionValidator = Callable[[ConfigPackV1], RegressionResult]


class ConfigRegistry:
    def __init__(self, root: Path, audit_private_key: Ed25519PrivateKey) -> None:
        self.root = root
        self.packs = root / "packs"
        self.current = root / "current.json"
        self.audit = AuditLog(root / "change-history.jsonl", audit_private_key)
        self.packs.mkdir(parents=True, exist_ok=True)

    def activate(
        self,
        candidate_path: Path,
        public_key_path: Path,
        regression_validator: RegressionValidator,
    ) -> ConfigPackV1:
        pack = load_config(candidate_path, public_key_path)
        regression = regression_validator(pack)
        if not regression.passed:
            raise ValueError(f"configuration regression rejected: {regression.summary}")
        if len(regression.evidence_hash) != 64:
            raise ValueError("configuration regression must provide a SHA-256 evidence hash")
        installed_path = self.packs / f"{pack.pack_hash}.json"
        if not installed_path.exists():
            temporary_pack = installed_path.with_suffix(f".tmp-{uuid.uuid4().hex}")
            temporary_pack.write_text(
                json.dumps(read_mapping(candidate_path), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_pack, installed_path)
        previous_hash = None
        if self.current.exists():
            previous_hash = json.loads(self.current.read_text(encoding="utf-8"))["pack_hash"]
        pointer = {
            "pack_hash": pack.pack_hash,
            "pack_id": pack.pack_id,
            "activated_at": utc_now(),
            "previous_pack_hash": previous_hash,
            "regression_evidence_hash": regression.evidence_hash,
            "regression_summary": regression.summary,
            "author": pack.author,
            "independent_approver": pack.independent_approver,
            "effective_at": pack.effective_at,
            "expires_at": pack.expires_at,
        }
        temporary_pointer = self.current.with_suffix(f".tmp-{uuid.uuid4().hex}")
        temporary_pointer.write_text(
            json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary_pointer, self.current)
        self.audit.append("CONFIG_PACK_ACTIVATED", pointer)
        return pack

    def rollback(self, pack_hash: str, public_key_path: Path) -> ConfigPackV1:
        target = self.packs / f"{pack_hash}.json"
        if not target.is_file():
            raise FileNotFoundError("rollback target is not an installed configuration pack")
        pack = load_config(target, public_key_path)
        if not self.current.exists():
            raise FileNotFoundError("there is no active configuration to roll back")
        previous = json.loads(self.current.read_text(encoding="utf-8"))
        pointer = {
            "pack_hash": pack.pack_hash,
            "pack_id": pack.pack_id,
            "activated_at": utc_now(),
            "previous_pack_hash": previous["pack_hash"],
            "rollback": True,
            "author": pack.author,
            "independent_approver": pack.independent_approver,
            "effective_at": pack.effective_at,
            "expires_at": pack.expires_at,
        }
        temporary = self.current.with_suffix(f".tmp-{uuid.uuid4().hex}")
        temporary.write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, self.current)
        self.audit.append("CONFIG_PACK_ROLLED_BACK", pointer)
        return pack
