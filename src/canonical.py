"""Deterministic Canonical JSON serialization (OSIRIS-CANONICAL-JSON-V1 / RFC 8785 subset)."""
from typing import Any
import json


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize object to deterministic canonical JSON bytes."""
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":")
    ).encode("utf-8")


def canonical_json_dumps(obj: Any) -> str:
    """Serialize object to deterministic canonical JSON string."""
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":")
    )
