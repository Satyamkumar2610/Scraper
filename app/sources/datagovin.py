"""
sources/datagovin.py — Adapter for the Data.gov.in REST API.

Handles discovery, pagination (offset/limit), retry, and raw-response
construction so the pipeline only sees `DiscoveryResult` / `PageResult`.
"""

from __future__ import annotations

from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.logger import logger
from app.sources.base import BaseDataSource, DiscoveryResult, PageResult


class APIError(Exception):
    """Raised on retryable HTTP status codes so tenacity can intercept."""


class DataGovInSource(BaseDataSource):
    """
    Concrete source adapter for https://api.data.gov.in.

    Pagination model: ``offset`` / ``limit`` query params.
    Authentication:   ``api-key`` query param.
    """

    RETRYABLE_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.API_KEY
        self.base_url = base_url or settings.DATAGOVIN_BASE_URL
        self.resource_id = resource_id or settings.DATAGOVIN_RESOURCE_ID

        if not self.api_key:
            raise ValueError(
                "API_KEY is not set. Add it to .env or pass it explicitly."
            )

        # Cached after first discovery call
        self._discovery: DiscoveryResult | None = None

    # ── Internal request helper (with retries) ─────────────────────────

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (requests.exceptions.RequestException, APIError)
        ),
        reraise=True,
    )
    def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a GET request with retry + exponential back-off."""
        response = requests.get(self.base_url, params=params, timeout=60)

        if response.status_code in self.RETRYABLE_CODES:
            logger.warning(
                "Retryable HTTP %s from Data.gov.in — will retry",
                response.status_code,
            )
            raise APIError(f"HTTP {response.status_code}")

        if response.status_code != 200:
            logger.error(
                "Non-retryable HTTP %s: %s",
                response.status_code,
                response.text[:500],
            )
            response.raise_for_status()

        return response.json()

    def _base_params(self) -> dict[str, Any]:
        return {
            "api-key": self.api_key,
            "format": "json",
        }

    # ── Public interface ────────────────────────────────────────────────

    def discover(self) -> DiscoveryResult:
        """Fetch a single record to learn schema, total count, fields."""
        logger.info("Running discovery against Data.gov.in …")
        params = {**self._base_params(), "offset": 0, "limit": 1}
        data = self._request(params)

        fields = data.get("field", [])
        total = int(data.get("total", 0))
        version = data.get("version", "unknown")

        # Attempt to extract any filter / sort hints from the response.
        supported_filters: list[str] = []
        supported_sorts: list[str] = []
        for f in fields:
            fid = f.get("id", "")
            if fid:
                supported_filters.append(fid)
                supported_sorts.append(fid)

        self._discovery = DiscoveryResult(
            source_name="datagovin",
            resource_id=self.resource_id,
            dataset_name=data.get("title", "Unknown Dataset"),
            total_records=total,
            fields=fields,
            pagination_type="offset",
            page_size_limit=None,  # Data.gov.in has no documented hard cap
            supported_filters=supported_filters,
            supported_sorts=supported_sorts,
            rate_limit=None,
            extra_metadata={"version": version, "status": data.get("status", "")},
        )

        logger.info(
            "Discovery complete — %d fields, %d total records, version=%s",
            len(fields),
            total,
            version,
        )
        return self._discovery

    def fetch_page(self, offset: int, limit: int) -> PageResult:
        """Fetch a single page of records at the given offset."""
        params = {**self._base_params(), "offset": offset, "limit": limit}
        logger.info("Fetching offset %d (limit %d)", offset, limit)

        data = self._request(params)
        records = data.get("records", [])

        logger.info("Received %d records for offset %d", len(records), offset)

        return PageResult(
            records=records,
            raw_json=data,
            request_url=self.base_url,
            request_params=params,
            total_records=int(data.get("total", 0)),
            offset=offset,
            limit=limit,
        )

    def fetch_metadata(self) -> dict[str, Any]:
        """Return supplementary metadata about the dataset."""
        if self._discovery is None:
            self.discover()
        assert self._discovery is not None
        return self._discovery.extra_metadata

    def get_total_records(self) -> int:
        """Return the total number of records available."""
        if self._discovery is None:
            self.discover()
        assert self._discovery is not None
        return self._discovery.total_records
