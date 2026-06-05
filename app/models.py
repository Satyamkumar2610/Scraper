"""
models.py — SQLAlchemy ORM models for the ingestion platform.

Tables
------
Metadata layer    : metadata_datasets, metadata_fields, metadata_api_runs
Job queue         : scrape_jobs
Raw storage       : raw_responses
Bronze layer      : crop_statistics_raw
Silver layer      : crop_statistics_standardized
Data quality      : validation_runs, data_quality_issues
Observability     : ingestion_metrics
"""

from __future__ import annotations

import datetime
import enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.database import Base


# ─── Enums ──────────────────────────────────────────────────────────────────

class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class RunStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


# ─── Metadata layer ────────────────────────────────────────────────────────

class MetadataDataset(Base):
    """One row per logical dataset we ingest."""
    __tablename__ = "metadata_datasets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(String(256), unique=True, nullable=False, index=True)
    dataset_name = Column(String(512), nullable=True)
    resource_id = Column(String(256), nullable=False)
    source_name = Column(String(128), nullable=False)  # e.g. "datagovin"
    discovered_at = Column(DateTime, server_default=func.now())


class MetadataField(Base):
    """Discovered fields for a dataset (schema catalogue)."""
    __tablename__ = "metadata_fields"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(String(256), nullable=False, index=True)
    field_name = Column(String(256), nullable=False)
    field_type = Column(String(128), nullable=True)
    discovered_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("dataset_id", "field_name", name="uq_dataset_field"),
    )


class MetadataApiRun(Base):
    """Top-level record for each ingestion run."""
    __tablename__ = "metadata_api_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), unique=True, nullable=False, index=True)
    source_name = Column(String(128), nullable=False)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    status = Column(Enum(RunStatus), default=RunStatus.running)


# ─── Job queue ──────────────────────────────────────────────────────────────

class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=True, index=True)
    offset_value = Column(Integer, nullable=False, index=True)
    status = Column(Enum(JobStatus), default=JobStatus.pending, nullable=False)
    records_fetched = Column(Integer, default=0)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "offset_value", name="uq_run_offset"),
    )


# ─── Raw response storage (DB mirror of filesystem JSONs) ──────────────────

class RawResponse(Base):
    __tablename__ = "raw_responses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, index=True)
    request_url = Column(Text, nullable=False)
    request_params = Column(JSON, nullable=True)
    response_json = Column(JSON, nullable=False)
    file_path = Column(Text, nullable=True)  # path under raw/
    created_at = Column(DateTime, server_default=func.now())


# ─── Bronze layer (raw records, one row per source record) ──────────────────

class CropStatisticRaw(Base):
    """
    Bronze table — preserves every field exactly as the API returned it.
    Columns are intentionally TEXT so no data is lost to type coercion.
    New fields detected during schema evolution are added as nullable columns.
    """
    __tablename__ = "crop_statistics_raw"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_record_hash = Column(String(64), unique=True, nullable=False, index=True)
    raw_json = Column(JSON, nullable=False)
    source_dataset = Column(String(256), nullable=True)
    source_resource_id = Column(String(256), nullable=True)
    source_system = Column(String(128), nullable=True)
    ingested_at = Column(DateTime, server_default=func.now())


# ─── Silver layer (standardised, analytics-ready) ──────────────────────────

class CropStatisticStandardized(Base):
    """
    Silver table — cleaned, typed, and standardised for analytics.
    Fields are mapped from the bronze layer and normalised.
    """
    __tablename__ = "crop_statistics_standardized"

    id = Column(Integer, primary_key=True, autoincrement=True)
    state_name = Column(String(256), nullable=True, index=True)
    district_name = Column(String(256), nullable=True, index=True)
    crop_name = Column(String(256), nullable=True, index=True)
    season = Column(String(128), nullable=True)
    year = Column(String(64), nullable=True, index=True)
    area_hectare = Column(Float, nullable=True)
    production_tonnes = Column(Float, nullable=True)
    yield_ton_per_hectare = Column(Float, nullable=True)

    # Lineage columns
    source_dataset = Column(String(256), nullable=True)
    source_resource_id = Column(String(256), nullable=True)
    source_record_hash = Column(String(64), unique=True, nullable=False, index=True)
    source_system = Column(String(128), nullable=True)
    ingested_at = Column(DateTime, server_default=func.now())
    api_response_timestamp = Column(DateTime, nullable=True)


# ─── Data quality layer ─────────────────────────────────────────────────────

class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, index=True)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    total_records = Column(Integer, default=0)
    issues_found = Column(Integer, default=0)
    status = Column(Enum(RunStatus), default=RunStatus.running)


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    validation_run_id = Column(Integer, index=True)
    record_hash = Column(String(64), nullable=True, index=True)
    field_name = Column(String(256), nullable=True)
    issue_type = Column(String(128), nullable=False)
    issue_detail = Column(Text, nullable=True)
    severity = Column(String(32), default="warning")  # info / warning / error
    created_at = Column(DateTime, server_default=func.now())


# ─── Observability / metrics ────────────────────────────────────────────────

class IngestionMetric(Base):
    __tablename__ = "ingestion_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, index=True)
    records_fetched = Column(Integer, default=0)
    records_inserted = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    duration_seconds = Column(Float, default=0.0)
    throughput_per_second = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=func.now())
