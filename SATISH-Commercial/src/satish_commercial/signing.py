"""Ed25519 signing helpers for governed configuration and audit records."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .contracts import canonical_json, sha256_hex

SIGNING_ALGORITHM = "Ed25519"


def generate_keypair(private_path: Path, public_path: Path) -> None:
    if private_path.exists() or public_path.exists():
        raise FileExistsError("refusing to overwrite an existing signing key")
    private_key = Ed25519PrivateKey.generate()
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise TypeError("the key is not an Ed25519 private key")
    return key


def load_public_key(path: Path) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        raise TypeError("the key is not an Ed25519 public key")
    return key


def signed_payload(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in mapping.items()
        if key not in {"pack_hash", "signature", "signing_algorithm"}
    }


def sign_mapping(mapping: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    payload = signed_payload(mapping)
    payload_bytes = canonical_json(payload)
    result = dict(payload)
    result["pack_hash"] = sha256_hex(payload_bytes)
    result["signing_algorithm"] = SIGNING_ALGORITHM
    result["signature"] = base64.b64encode(private_key.sign(payload_bytes)).decode("ascii")
    return result


def verify_mapping(mapping: dict[str, Any], public_key: Ed25519PublicKey) -> None:
    if mapping.get("signing_algorithm") != SIGNING_ALGORITHM:
        raise ValueError("unsupported or missing signing algorithm")
    payload_bytes = canonical_json(signed_payload(mapping))
    expected_hash = sha256_hex(payload_bytes)
    if mapping.get("pack_hash") != expected_hash:
        raise ValueError("configuration hash does not match its canonical payload")
    try:
        signature = base64.b64decode(str(mapping["signature"]), validate=True)
        public_key.verify(signature, payload_bytes)
    except (InvalidSignature, KeyError, ValueError) as exc:
        raise ValueError("configuration signature verification failed") from exc
