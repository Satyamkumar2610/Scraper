"""
exporters.py — Export dynamic raw data to CSV, Parquet, Arrow, and JSON.

All exports write to ``exports/`` with timestamped filenames.
Supports optional SQL-level filtering and incremental extraction
via ``since`` (datetime) and ``where`` (dict of column=value filters).
"""

from __future__ import annotations

import datetime
import os
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine
from app.logger import logger


def _build_query(
    since: datetime.datetime | None = None,
    where: dict[str, Any] | None = None,
) -> str:
    """Build a SELECT query with optional WHERE clauses."""
    clauses: list[str] = []
    if since:
        clauses.append(f"ingested_at >= '{since.isoformat()}'")
    if where:
        for col, val in where.items():
            safe_val = str(val).replace("'", "''")
            clauses.append(f"{col} = '{safe_val}'")

    sql = "SELECT * FROM crop_statistics_raw"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return sql


def _ensure_export_dir() -> str:
    os.makedirs(settings.EXPORT_DIR, exist_ok=True)
    return settings.EXPORT_DIR


def _timestamped_name(extension: str) -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"crop_statistics_raw_{ts}.{extension}"


# ─── Public export functions ─────────────────────────────────────────

def export_csv(
    since: datetime.datetime | None = None,
    where: dict[str, Any] | None = None,
) -> str:
    """Export to CSV.  Returns the output file path."""
    out_dir = _ensure_export_dir()
    path = os.path.join(out_dir, _timestamped_name("csv"))

    sql = _build_query(since, where)
    df = pd.read_sql(text(sql), con=engine)
    df.to_csv(path, index=False)

    logger.info("Exported %d rows to %s", len(df), path)
    return path


def export_parquet(
    since: datetime.datetime | None = None,
    where: dict[str, Any] | None = None,
) -> str:
    """Export to Parquet.  Returns the output file path."""
    out_dir = _ensure_export_dir()
    path = os.path.join(out_dir, _timestamped_name("parquet"))

    sql = _build_query(since, where)
    df = pd.read_sql(text(sql), con=engine)
    df.to_parquet(path, index=False, engine="pyarrow")

    logger.info("Exported %d rows to %s", len(df), path)
    return path


def export_arrow(
    since: datetime.datetime | None = None,
    where: dict[str, Any] | None = None,
) -> str:
    """Export to Arrow IPC (Feather v2).  Returns the output file path."""
    out_dir = _ensure_export_dir()
    path = os.path.join(out_dir, _timestamped_name("arrow"))

    sql = _build_query(since, where)
    df = pd.read_sql(text(sql), con=engine)
    df.to_feather(path)

    logger.info("Exported %d rows to %s", len(df), path)
    return path


def export_json(
    since: datetime.datetime | None = None,
    where: dict[str, Any] | None = None,
) -> str:
    """Export to newline-delimited JSON.  Returns the output file path."""
    out_dir = _ensure_export_dir()
    path = os.path.join(out_dir, _timestamped_name("jsonl"))

    sql = _build_query(since, where)
    df = pd.read_sql(text(sql), con=engine)
    df.to_json(path, orient="records", lines=True, force_ascii=False)

    logger.info("Exported %d rows to %s", len(df), path)
    return path


def export_xlsx(
    since: datetime.datetime | None = None,
    where: dict[str, Any] | None = None,
) -> str:
    """Export to XLSX format. Returns the output file path."""
    out_dir = _ensure_export_dir()
    path = os.path.join(out_dir, _timestamped_name("xlsx"))

    sql = _build_query(since, where)
    df = pd.read_sql(text(sql), con=engine)
    df.to_excel(path, index=False, engine="openpyxl")

    logger.info("Exported %d rows to %s", len(df), path)
    return path
