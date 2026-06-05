"""
sources/base.py — Abstract base class for all government-data source adapters.

Every new data source (Data.gov.in, DESAgri, APS DAC, state portals, …)
must subclass `BaseDataSource` and implement the abstract methods so the
rest of the pipeline (validation, storage, lineage, metrics, export)
remains source-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiscoveryResult:
    """Container for everything learned during the discovery phase."""

    source_name: str = ""
    resource_id: str = ""
    dataset_name: str = ""
    total_records: int = 0
    fields: list[dict[str, Any]] = field(default_factory=list)
    pagination_type: str = "offset"  # offset | cursor | page
    page_size_limit: int | None = None
    supported_filters: list[str] = field(default_factory=list)
    supported_sorts: list[str] = field(default_factory=list)
    rate_limit: str | None = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageResult:
    """Container for a single page fetched from the source."""

    records: list[dict[str, Any]]
    raw_json: dict[str, Any]
    request_url: str
    request_params: dict[str, Any]
    total_records: int
    offset: int
    limit: int


class BaseDataSource(ABC):
    """
    Abstract adapter that every government-data source must implement.

    Lifecycle
    ---------
    1. ``discover()``       – inspect the API, learn schema & pagination.
    2. ``get_total_records()`` – return the total count.
    3. ``fetch_page(offset, limit)`` – return a PageResult.
    4. ``fetch_metadata()``   – return arbitrary metadata dict.
    """

    @abstractmethod
    def discover(self) -> DiscoveryResult:
        """Inspect the remote API and return a DiscoveryResult."""
        ...

    @abstractmethod
    def fetch_page(self, offset: int, limit: int) -> PageResult:
        """Fetch a single page of records."""
        ...

    @abstractmethod
    def fetch_metadata(self) -> dict[str, Any]:
        """Return supplementary metadata about the dataset."""
        ...

    @abstractmethod
    def get_total_records(self) -> int:
        """Return the total number of records available remotely."""
        ...
