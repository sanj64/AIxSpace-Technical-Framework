"""Append-only, signed, hash-chained audit records."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .contracts import canonical_json, sha256_hex, utc_now
from .signing import SIGNING_ALGORITHM

GENESIS_HASH = "0" * 64


class AuditLog:
    def __init__(self, path: Path, private_key: Ed25519PrivateKey) -> None:
        self.path = path
        self.private_key = private_key
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        previous_hash = GENESIS_HASH
        sequence = 1
        if self.path.exists() and self.path.stat().st_size:
            last = self.path.read_text(encoding="utf-8").splitlines()[-1]
            previous = json.loads(last)
            previous_hash = str(previous["entry_hash"])
            sequence = int(previous["sequence"]) + 1
        body = {
            "sequence": sequence,
            "timestamp": utc_now(),
            "event_type": event_type,
            "payload": payload,
            "previous_hash": previous_hash,
        }
        entry_hash = sha256_hex(canonical_json(body))
        record = {
            **body,
            "entry_hash": entry_hash,
            "signing_algorithm": SIGNING_ALGORITHM,
            "signature": base64.b64encode(self.private_key.sign(entry_hash.encode("ascii"))).decode(
                "ascii"
            ),
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
        return record


def verify_audit(path: Path, public_key: Ed25519PublicKey) -> int:
    previous_hash = GENESIS_HASH
    expected_sequence = 1
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            record = json.loads(line)
            if int(record.get("sequence", -1)) != expected_sequence:
                raise ValueError(f"audit sequence break at line {line_number}")
            if record.get("previous_hash") != previous_hash:
                raise ValueError(f"audit hash-chain break at line {line_number}")
            body = {
                key: record[key]
                for key in ("sequence", "timestamp", "event_type", "payload", "previous_hash")
            }
            computed = sha256_hex(canonical_json(body))
            if computed != record.get("entry_hash"):
                raise ValueError(f"audit content hash mismatch at line {line_number}")
            if record.get("signing_algorithm") != SIGNING_ALGORITHM:
                raise ValueError(f"unsupported signature algorithm at line {line_number}")
            try:
                signature = base64.b64decode(record["signature"], validate=True)
                public_key.verify(signature, computed.encode("ascii"))
            except (InvalidSignature, KeyError, ValueError) as exc:
                raise ValueError(
                    f"audit signature verification failed at line {line_number}"
                ) from exc
            previous_hash = computed
            expected_sequence += 1
            count += 1
    return count
