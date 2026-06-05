"""
lineage.py — Record-level data lineage via deterministic hashing.

Every source record is assigned a SHA-256 hash derived from a sorted,
canonical JSON representation of its fields.  This hash is used as the
deduplication key across bronze and silver layers and enables full
traceability from any analytics row back to the raw API response.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_record_hash(record: dict[str, Any]) -> str:
    """
    Return a deterministic SHA-256 hex digest for a source record.

    The record dict is serialised with sorted keys and no whitespace
    so that logically identical payloads always produce the same hash
    regardless of key ordering in the original JSON.
    """
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def enrich_with_lineage(
    record: dict[str, Any],
    *,
    source_dataset: str,
    source_resource_id: str,
    source_system: str,
) -> dict[str, Any]:
    """
    Return a copy of *record* augmented with lineage columns.

    These columns are written alongside the record in both the bronze
    and silver tables so that every value is traceable to its source.
    """
    return {
        **record,
        "source_dataset": source_dataset,
        "source_resource_id": source_resource_id,
        "source_system": source_system,
        "source_record_hash": compute_record_hash(record),
    }
