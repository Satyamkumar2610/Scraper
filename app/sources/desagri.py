"""
sources/desagri.py — Stub adapter for the DESAgri data source.

This is a placeholder for future integration with the Directorate of
Economics and Statistics (DESAgri) agricultural data systems.  The class
satisfies the `BaseDataSource` interface but raises `NotImplementedError`
for all methods.
"""

from __future__ import annotations

from typing import Any

from app.sources.base import BaseDataSource, DiscoveryResult, PageResult


class DESAgriSource(BaseDataSource):
    """
    Future adapter for DESAgri / APS-DAC data.

    Implement this class when the DESAgri API specification becomes
    available.  The rest of the pipeline (validation, storage, lineage,
    metrics, export) will work without changes.
    """

    def discover(self) -> DiscoveryResult:
        raise NotImplementedError("DESAgri source is not yet implemented.")

    def fetch_page(self, offset: int, limit: int) -> PageResult:
        raise NotImplementedError("DESAgri source is not yet implemented.")

    def fetch_metadata(self) -> dict[str, Any]:
        raise NotImplementedError("DESAgri source is not yet implemented.")

    def get_total_records(self) -> int:
        raise NotImplementedError("DESAgri source is not yet implemented.")
