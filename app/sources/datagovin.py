"""
datagovin.py — Data.gov.in adapter implementation.
"""

from __future__ import annotations

import os
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
    pass


class DataGovInSource(BaseDataSource):
    """
    Adapter for the Data.gov.in API.
    Handles authentication via api-key and pagination via offset/limit.
    """

    RETRYABLE_CODES = {429, 500, 502, 503, 504}

    def __init__(self, resource_id: str | None = None):
        self.resource_id = resource_id or "35be999b-0208-4354-b557-f6ca9a5355de"
        self.base_url = f"https://api.data.gov.in/resource/{self.resource_id}"

        self.api_key = settings.API_KEY
        if not self.api_key:
            raise ValueError("API_KEY environment variable is required")
            
        self._total_records = 0

    @property
    def source_name(self) -> str:
        return "datagovin"

    def _build_params(self, offset: int, limit: int) -> dict[str, Any]:
        return {
            "api-key": self.api_key,
            "format": "json",
            "offset": str(offset),
            "limit": str(limit),
        }

    @retry(
        retry=retry_if_exception_type((requests.exceptions.RequestException, APIError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        # Data.gov.in can be very slow (45-90s per response).
        response = requests.get(self.base_url, params=params, timeout=(10, 180))

        if response.status_code in self.RETRYABLE_CODES:
            logger.warning(
                "Retryable HTTP %d from Data.gov.in — will retry",
                response.status_code,
            )
            raise APIError(f"HTTP {response.status_code}")

        response.raise_for_status()

        data = response.json()
        if data.get("status") != "ok" and "error" in data:
            raise APIError(f"API returned error: {data}")

        return data

    def discover(self) -> DiscoveryResult:
        logger.info("Running discovery against Data.gov.in …")
        params = self._build_params(0, 1)

        try:
            # We bypass _request here to fail-fast on discovery.
            # If the API is down, we don't want to wait 5 minutes of retries just to fallback.
            response = requests.get(self.base_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            total = int(data.get("total", 0))
            self._total_records = total
            fields = data.get("field", [])
            return DiscoveryResult(
                dataset_name=data.get("title", "Unknown Dataset"),
                resource_id=self.resource_id,
                source_name=self.source_name,
                fields=fields,
                total_records=total,
            )
        except Exception as e:
            logger.warning("Discovery API failed (%s). Falling back to known schema...", e)
            self._total_records = 246091
            return DiscoveryResult(
                dataset_name="District-wise, season-wise crop production statistics from 1997",
                resource_id=self.resource_id,
                source_name=self.source_name,
                fields=[
                    {"id": "state_name", "name": "State_Name", "type": "keyword"},
                    {"id": "district_name", "name": "District_Name", "type": "keyword"},
                    {"id": "crop_year", "name": "Crop_Year", "type": "double"},
                    {"id": "season", "name": "Season", "type": "keyword"},
                    {"id": "crop", "name": "Crop", "type": "keyword"},
                    {"id": "area_", "name": "Area", "type": "double"},
                    {"id": "production_", "name": "Production", "type": "double"}
                ],
                total_records=246091,
            )

    def fetch_page(self, offset: int, limit: int) -> PageResult:
        params = self._build_params(offset, limit)
        data = self._request(params)
        records = data.get("records", [])

        # The API doesn't expose the full URL strictly with query params in a clean way,
        # so we reconstruct it for logging/lineage purposes.
        req_url = f"{self.base_url}?offset={offset}&limit={limit}"

        return PageResult(
            records=records,
            raw_json=data,
            request_url=req_url,
            request_params=params,
            total_records=int(data.get("total", self._total_records)),
            offset=offset,
            limit=limit,
        )

    def fetch_metadata(self) -> dict[str, Any]:
        """Fetch general dataset metadata."""
        return {}

    def get_total_records(self) -> int:
        return self._total_records
