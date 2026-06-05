"""
validation.py — Data-quality checks for ingested records.

Runs a battery of rule-based checks against the silver layer and logs
every issue to the ``data_quality_issues`` table so that data stewards
can review, filter, and act on problems without blocking ingestion.
"""

from __future__ import annotations

import datetime
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.logger import logger
from app.models import (
    CropStatisticStandardized,
    DataQualityIssue,
    RunStatus,
    ValidationRun,
)


# ─── Individual check functions ─────────────────────────────────────────

def _check_nulls(
    record: CropStatisticStandardized,
    issues: list[dict[str, Any]],
) -> None:
    """Flag critical fields that are NULL."""
    for col in ("state_name", "district_name", "crop_name", "year"):
        if getattr(record, col, None) is None:
            issues.append({
                "record_hash": record.source_record_hash,
                "field_name": col,
                "issue_type": "null_value",
                "issue_detail": f"{col} is null",
                "severity": "warning",
            })


def _check_negative_numbers(
    record: CropStatisticStandardized,
    issues: list[dict[str, Any]],
) -> None:
    """Production, area, and yield should never be negative."""
    for col in ("area_hectare", "production_tonnes", "yield_ton_per_hectare"):
        val = getattr(record, col, None)
        if val is not None and val < 0:
            issues.append({
                "record_hash": record.source_record_hash,
                "field_name": col,
                "issue_type": "negative_value",
                "issue_detail": f"{col} = {val}",
                "severity": "error",
            })


_YEAR_RE = re.compile(r"^\d{4}(-\d{2,4})?$")  # e.g. "2020" or "2020-21"


def _check_year(
    record: CropStatisticStandardized,
    issues: list[dict[str, Any]],
) -> None:
    """Year should match a reasonable pattern."""
    yr = record.year
    if yr is not None and not _YEAR_RE.match(str(yr).strip()):
        issues.append({
            "record_hash": record.source_record_hash,
            "field_name": "year",
            "issue_type": "invalid_year",
            "issue_detail": f"year = '{yr}'",
            "severity": "warning",
        })


def _check_malformed_names(
    record: CropStatisticStandardized,
    issues: list[dict[str, Any]],
) -> None:
    """State and district names shouldn't contain digits or odd chars."""
    for col in ("state_name", "district_name"):
        val = getattr(record, col, None)
        if val and re.search(r"\d", str(val)):
            issues.append({
                "record_hash": record.source_record_hash,
                "field_name": col,
                "issue_type": "malformed_name",
                "issue_detail": f"{col} = '{val}' contains digits",
                "severity": "info",
            })


# ─── Public API ─────────────────────────────────────────────────────────

def run_validation(db: Session, run_id: str | None = None) -> int:
    """
    Validate every row in ``crop_statistics_standardized`` and persist
    issues to ``data_quality_issues``.

    Returns the number of issues found.
    """
    run_id = run_id or uuid.uuid4().hex[:16]
    vr = ValidationRun(run_id=run_id, status=RunStatus.running)
    db.add(vr)
    db.commit()

    logger.info("Validation run %s started", run_id)

    total = 0
    issue_count = 0
    batch: list[DataQualityIssue] = []

    # Stream in chunks of 5000 to keep memory flat
    query = db.query(CropStatisticStandardized).yield_per(5000)

    for record in query:
        total += 1
        issues: list[dict[str, Any]] = []

        _check_nulls(record, issues)
        _check_negative_numbers(record, issues)
        _check_year(record, issues)
        _check_malformed_names(record, issues)

        for iss in issues:
            batch.append(
                DataQualityIssue(validation_run_id=vr.id, **iss)
            )
            issue_count += 1

        # Flush in batches of 1000
        if len(batch) >= 1000:
            db.bulk_save_objects(batch)
            db.commit()
            batch.clear()

    # Remaining
    if batch:
        db.bulk_save_objects(batch)
        db.commit()

    vr.total_records = total
    vr.issues_found = issue_count
    vr.status = RunStatus.completed
    vr.completed_at = datetime.datetime.utcnow()
    db.commit()

    logger.info(
        "Validation run %s complete — %d records checked, %d issues found",
        run_id,
        total,
        issue_count,
    )
    return issue_count
