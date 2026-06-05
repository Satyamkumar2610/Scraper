"""
scheduler.py — Pipeline orchestrator: discovery → jobs → ingest → metrics.

Public entry-points
-------------------
- ``perform_discovery(source)``  — inspect API, persist metadata & schema.
- ``start_scrape(source, limit)`` — full-refresh scrape.
- ``resume_scrape(source, limit)`` — resume from last successful offset.
- ``get_status()``                — print job queue statistics.
"""

from __future__ import annotations

import datetime
import json
import os
import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.database import get_db, init_db, engine
from app.lineage import compute_record_hash
from app.logger import logger
from app.metrics import RunAccumulator, save_metrics
from app.models import (
    JobStatus,
    MetadataApiRun,
    MetadataDataset,
    MetadataField,
    RawResponse,
    RunStatus,
    ScrapeJob,
    get_dynamic_raw_table
)
from app.parser import detect_new_fields
from app.sources.base import BaseDataSource, DiscoveryResult


# ═══════════════════════════════════════════════════════════════════════
#  DISCOVERY
# ═══════════════════════════════════════════════════════════════════════

def perform_discovery(source: BaseDataSource) -> DiscoveryResult:
    """
    Run the discovery phase for *source*, create all tables, and persist
    the discovered metadata / field catalogue.
    """
    logger.info("Starting discovery …")
    result = source.discover()

    # Ensure all ORM tables exist
    init_db()

    with get_db() as db:
        # Upsert dataset record
        ds = db.query(MetadataDataset).filter_by(
            dataset_id=result.resource_id,
        ).first()
        if ds is None:
            ds = MetadataDataset(
                dataset_id=result.resource_id,
                dataset_name=result.dataset_name,
                resource_id=result.resource_id,
                source_name=result.source_name,
            )
            db.add(ds)
            db.commit()

        # Persist fields
        for f in result.fields:
            fname = f.get("id", f.get("name", ""))
            ftype = f.get("type", "unknown")
            exists = (
                db.query(MetadataField)
                .filter_by(dataset_id=result.resource_id, field_name=fname)
                .first()
            )
            if not exists:
                db.add(MetadataField(
                    dataset_id=result.resource_id,
                    field_name=fname,
                    field_type=ftype,
                ))
        db.commit()

    # Generate dynamic table explicitly using discovered fields
    fields_set = {f.get("id", f.get("name", "")) for f in result.fields if f.get("id") or f.get("name")}
    table = get_dynamic_raw_table(fields_set)
    table.create(engine, checkfirst=True)

    logger.info(
        "Discovery complete — %d fields, %d total records",
        len(result.fields),
        result.total_records,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════
#  RAW RESPONSE STORAGE (filesystem + DB)
# ═══════════════════════════════════════════════════════════════════════

def _save_raw_to_filesystem(
    raw_json: dict[str, Any],
    offset: int,
) -> str:
    """Write the raw JSON to ``raw/YYYY/MM/DD/offset_NNNNNN.json``."""
    now = datetime.datetime.utcnow()
    dir_path = os.path.join(
        settings.RAW_DIR,
        now.strftime("%Y"),
        now.strftime("%m"),
        now.strftime("%d"),
    )
    os.makedirs(dir_path, exist_ok=True)
    filename = f"offset_{offset:06d}.json"
    filepath = os.path.join(dir_path, filename)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(raw_json, fh, ensure_ascii=False)
    return filepath


# ═══════════════════════════════════════════════════════════════════════
#  SINGLE-JOB EXECUTION
# ═══════════════════════════════════════════════════════════════════════

def _run_single_job(
    db: Session,
    job: ScrapeJob,
    source: BaseDataSource,
    limit: int,
    discovery: DiscoveryResult,
    acc: RunAccumulator,
    known_fields: set[str],
) -> None:
    """Execute one job: fetch → raw → dynamic raw fields → mark complete."""

    job.status = JobStatus.running
    job.started_at = datetime.datetime.utcnow()
    db.commit()

    try:
        # ── Fetch ───────────────────────────────────────────────────
        page = source.fetch_page(job.offset_value, limit)
        acc.tick_fetched(len(page.records))

        # ── Raw storage ─────────────────────────────────────────────
        filepath = _save_raw_to_filesystem(page.raw_json, job.offset_value)

        # Redact API key before storing params in DB
        safe_params = {
            k: ("***" if k == "api-key" else v)
            for k, v in page.request_params.items()
        }
        raw_row = RawResponse(
            job_id=job.id,
            request_url=page.request_url,
            request_params=safe_params,
            response_json=page.raw_json,
            file_path=filepath,
        )
        db.add(raw_row)

        # ── Schema evolution check ──────────────────────────────────
        new_fields = detect_new_fields(known_fields, page.records)
        if new_fields:
            for nf in new_fields:
                known_fields.add(nf)
                exists = (
                    db.query(MetadataField)
                    .filter_by(
                        dataset_id=discovery.resource_id,
                        field_name=nf,
                    )
                    .first()
                )
                if not exists:
                    db.add(MetadataField(
                        dataset_id=discovery.resource_id,
                        field_name=nf,
                        field_type="unknown",
                    ))
                # Alter table to add new field safely
                try:
                    db.execute(text(f"ALTER TABLE crop_statistics_raw ADD COLUMN {nf} TEXT"))
                except Exception as e:
                    db.rollback()
                    logger.warning(f"Failed to add column {nf}, it might already exist: {e}")

        # ── Dynamic Raw Upsert ─────────────────────────────────────────
        inserted = 0
        table = get_dynamic_raw_table(known_fields)
        
        for rec in page.records:
            rec_hash = compute_record_hash(rec)
            
            # Map values exactly as strings (pure raw extraction)
            row_data = {
                "source_record_hash": rec_hash,
                "source_dataset": discovery.dataset_name,
                "source_resource_id": discovery.resource_id,
                "source_system": discovery.source_name,
            }
            for k, v in rec.items():
                if k in known_fields:
                    row_data[k] = str(v) if v is not None else None

            # Bronze upsert (ON CONFLICT DO UPDATE)
            bronze_stmt = pg_insert(table).values(**row_data)
            
            # Set up update dict for on_conflict
            set_dict = {"ingested_at": datetime.datetime.utcnow()}
            for k in rec.keys():
                if k in known_fields:
                    set_dict[k] = getattr(bronze_stmt.excluded, k)
                    
            bronze_stmt = bronze_stmt.on_conflict_do_update(
                index_elements=["source_record_hash"],
                set_=set_dict,
            )
            db.execute(bronze_stmt)
            inserted += 1

        acc.tick_inserted(inserted)

        # ── Mark complete ───────────────────────────────────────────
        job.status = JobStatus.completed
        job.records_fetched = len(page.records)
        job.completed_at = datetime.datetime.utcnow()
        job.error_message = None
        db.commit()

        logger.info(
            "Offset %d — inserted/updated %d records",
            job.offset_value,
            inserted,
        )

    except Exception as exc:
        db.rollback()
        job.status = JobStatus.failed
        job.error_message = str(exc)[:2000]
        db.commit()
        acc.tick_failed(1)
        logger.error("Offset %d failed: %s", job.offset_value, exc)


# ═══════════════════════════════════════════════════════════════════════
#  FULL SCRAPE
# ═══════════════════════════════════════════════════════════════════════

def start_scrape(
    source: BaseDataSource,
    limit: int | None = None,
) -> None:
    """Full-refresh scrape: discover → create jobs → execute them all."""
    limit = limit or settings.DEFAULT_PAGE_SIZE
    discovery = perform_discovery(source)
    total = discovery.total_records
    run_id = uuid.uuid4().hex[:16]
    known_fields = {f.get("id", "") for f in discovery.fields if f.get("id")}

    logger.info(
        "Starting scrape run %s — %d records, page size %d",
        run_id,
        total,
        limit,
    )

    acc = RunAccumulator(run_id=run_id)

    with get_db() as db:
        # Register the API run
        db.add(MetadataApiRun(
            run_id=run_id,
            source_name=discovery.source_name,
            status=RunStatus.running,
        ))
        db.commit()

        for offset in range(0, total, limit):
            # Skip already-completed jobs (idempotent)
            existing = (
                db.query(ScrapeJob)
                .filter_by(run_id=run_id, offset_value=offset)
                .first()
            )
            if existing and existing.status == JobStatus.completed:
                continue

            if existing is None:
                job = ScrapeJob(
                    run_id=run_id,
                    offset_value=offset,
                    status=JobStatus.pending,
                )
                db.add(job)
                db.commit()
                db.refresh(job)
            else:
                job = existing

            _run_single_job(db, job, source, limit, discovery, acc, known_fields)

        # Finalise run
        api_run = db.query(MetadataApiRun).filter_by(run_id=run_id).first()
        if api_run:
            api_run.status = RunStatus.completed
            api_run.completed_at = datetime.datetime.utcnow()

        save_metrics(db, acc)

    logger.info("Scrape run %s finished", run_id)


# ═══════════════════════════════════════════════════════════════════════
#  RESUME
# ═══════════════════════════════════════════════════════════════════════

def resume_scrape(
    source: BaseDataSource,
    limit: int | None = None,
) -> None:
    """
    Resume an interrupted run.  Re-runs pending / running / failed jobs,
    then continues with any offsets not yet queued.
    """
    limit = limit or settings.DEFAULT_PAGE_SIZE
    discovery = perform_discovery(source)
    total = discovery.total_records
    known_fields = {f.get("id", "") for f in discovery.fields if f.get("id")}

    # Try to find the most recent incomplete run
    with get_db() as db:
        last_run = (
            db.query(MetadataApiRun)
            .filter(MetadataApiRun.status != RunStatus.completed)
            .order_by(MetadataApiRun.started_at.desc())
            .first()
        )
        run_id = last_run.run_id if last_run else uuid.uuid4().hex[:16]

    logger.info("Resuming run %s — %d total records", run_id, total)
    acc = RunAccumulator(run_id=run_id)

    with get_db() as db:
        # Ensure api_run row exists
        if not db.query(MetadataApiRun).filter_by(run_id=run_id).first():
            db.add(MetadataApiRun(
                run_id=run_id,
                source_name=discovery.source_name,
                status=RunStatus.running,
            ))
            db.commit()

        # 1. Re-run incomplete jobs
        incomplete = (
            db.query(ScrapeJob)
            .filter(
                ScrapeJob.run_id == run_id,
                ScrapeJob.status.in_([
                    JobStatus.pending,
                    JobStatus.running,
                    JobStatus.failed,
                ]),
            )
            .order_by(ScrapeJob.offset_value)
            .all()
        )
        logger.info("Retrying %d incomplete jobs", len(incomplete))
        for job in incomplete:
            _run_single_job(db, job, source, limit, discovery, acc, known_fields)

        # 2. Queue remaining offsets
        max_job = (
            db.query(ScrapeJob)
            .filter_by(run_id=run_id)
            .order_by(ScrapeJob.offset_value.desc())
            .first()
        )
        start_offset = (max_job.offset_value + limit) if max_job else 0
        for offset in range(start_offset, total, limit):
            job = ScrapeJob(
                run_id=run_id,
                offset_value=offset,
                status=JobStatus.pending,
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            _run_single_job(db, job, source, limit, discovery, acc, known_fields)

        # Finalise
        api_run = db.query(MetadataApiRun).filter_by(run_id=run_id).first()
        if api_run:
            api_run.status = RunStatus.completed
            api_run.completed_at = datetime.datetime.utcnow()
        save_metrics(db, acc)

    logger.info("Resume run %s finished", run_id)


# ═══════════════════════════════════════════════════════════════════════
#  STATUS
# ═══════════════════════════════════════════════════════════════════════

def get_status() -> dict[str, int]:
    """Print and return a summary of the job queue."""
    with get_db() as db:
        total = db.query(ScrapeJob).count()
        completed = db.query(ScrapeJob).filter_by(status=JobStatus.completed).count()
        failed = db.query(ScrapeJob).filter_by(status=JobStatus.failed).count()
        pending = db.query(ScrapeJob).filter_by(status=JobStatus.pending).count()
        running = db.query(ScrapeJob).filter_by(status=JobStatus.running).count()

    stats = {
        "total": total,
        "completed": completed,
        "failed": failed,
        "pending": pending,
        "running_or_crashed": running,
    }

    logger.info("─── Job Queue Status ───")
    for k, v in stats.items():
        logger.info("  %s: %d", k.replace("_", " ").title(), v)

    return stats
