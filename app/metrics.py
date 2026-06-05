"""
metrics.py — Per-run ingestion metrics and throughput tracking.

Call ``start_run`` at the beginning and ``finish_run`` at the end of each
ingestion pass.  Counters are accumulated in-memory via ``RunAccumulator``
and flushed to the ``ingestion_metrics`` table on completion.
"""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.logger import logger
from app.models import IngestionMetric


@dataclass
class RunAccumulator:
    """Mutable counters that live for the duration of a single run."""

    run_id: str = ""
    records_fetched: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_failed: int = 0
    _start: float = field(default_factory=time.time)

    def tick_fetched(self, n: int = 1) -> None:
        self.records_fetched += n

    def tick_inserted(self, n: int = 1) -> None:
        self.records_inserted += n

    def tick_updated(self, n: int = 1) -> None:
        self.records_updated += n

    def tick_failed(self, n: int = 1) -> None:
        self.records_failed += n

    @property
    def elapsed(self) -> float:
        return time.time() - self._start

    @property
    def throughput(self) -> float:
        e = self.elapsed
        return self.records_inserted / e if e > 0 else 0.0


def save_metrics(db: Session, acc: RunAccumulator) -> None:
    """Persist the accumulated counters to ``ingestion_metrics``."""
    metric = IngestionMetric(
        run_id=acc.run_id,
        records_fetched=acc.records_fetched,
        records_inserted=acc.records_inserted,
        records_updated=acc.records_updated,
        records_failed=acc.records_failed,
        duration_seconds=round(acc.elapsed, 2),
        throughput_per_second=round(acc.throughput, 2),
    )
    db.add(metric)
    db.commit()

    logger.info(
        "Metrics saved for run %s — fetched=%d inserted=%d updated=%d "
        "failed=%d duration=%.1fs throughput=%.1f rec/s",
        acc.run_id,
        acc.records_fetched,
        acc.records_inserted,
        acc.records_updated,
        acc.records_failed,
        acc.elapsed,
        acc.throughput,
    )
