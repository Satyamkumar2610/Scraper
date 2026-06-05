"""
parser.py — API response parsing and bronze→silver field mapping.

This module is source-agnostic: it operates on dicts returned by any
source adapter's ``PageResult.records``.  The field-mapping tables live
here so they are easy to update when new sources are added.
"""

from __future__ import annotations

from typing import Any

from app.logger import logger


# ─── Generic extraction helpers ─────────────────────────────────────────

def extract_fields(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the ``field`` array from a Data.gov.in-style response."""
    return response_json.get("field", [])


def extract_records(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the ``records`` array from a Data.gov.in-style response."""
    return response_json.get("records", [])


def get_total_records(response_json: dict[str, Any]) -> int:
    """Return the ``total`` count from a Data.gov.in-style response."""
    return int(response_json.get("total", 0))


# ─── Schema detection ───────────────────────────────────────────────────

def detect_new_fields(
    known_fields: set[str],
    records: list[dict[str, Any]],
) -> set[str]:
    """
    Compare the keys present in *records* against *known_fields* and
    return any that are new.  This drives the schema-evolution logic.
    """
    observed: set[str] = set()
    for rec in records:
        observed.update(rec.keys())
    new = observed - known_fields
    if new:
        logger.warning("New fields detected in source data: %s", new)
    return new


# ─── Bronze → Silver mapping ────────────────────────────────────────────

# Maps known Data.gov.in field names to the standardised silver columns.
# Keys are lowercased source field ids; values are silver column names.
SILVER_FIELD_MAP: dict[str, str] = {
    "state_name": "state_name",
    "state__name": "state_name",
    "district_name": "district_name",
    "district__name": "district_name",
    "crop": "crop_name",
    "crop_name": "crop_name",
    "season": "season",
    "crop_year": "year",
    "year": "year",
    "area_": "area_hectare",
    "area": "area_hectare",
    "area__in_hectare_": "area_hectare",
    "production_": "production_tonnes",
    "production": "production_tonnes",
    "production__in_tonnes_": "production_tonnes",
    "yield": "yield_ton_per_hectare",
    "yield_": "yield_ton_per_hectare",
    "yield__tonnes_hectare_": "yield_ton_per_hectare",
}


def _safe_float(value: Any) -> float | None:
    """Coerce a value to float, returning None on failure."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return None


def map_to_silver(record: dict[str, Any]) -> dict[str, Any]:
    """
    Transform a raw/bronze record dict into a silver-layer dict with
    standardised column names and typed values.

    Unknown fields are silently dropped — the bronze layer preserves them.
    """
    silver: dict[str, Any] = {}

    for src_key, value in record.items():
        target = SILVER_FIELD_MAP.get(src_key.lower())
        if target is None:
            continue

        if target in ("area_hectare", "production_tonnes", "yield_ton_per_hectare"):
            silver[target] = _safe_float(value)
        else:
            silver[target] = str(value).strip() if value is not None else None

    return silver
