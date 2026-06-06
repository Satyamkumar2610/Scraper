"""
desagri.py — DESAgri website adapter implementation.
"""

from __future__ import annotations

import re
from typing import Any
from io import StringIO

import requests
import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.logger import logger
from app.sources.base import BaseDataSource, DiscoveryResult, PageResult
import urllib3

# Suppress insecure request warnings for government sites
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class APIError(Exception):
    pass


class DESAgriSource(BaseDataSource):
    """
    Adapter for the DESAgri Website (HTML scraping).
    Chunks by State.
    """

    def __init__(self):
        self.base_url = "https://data.desagri.gov.in"
        self.session = requests.Session()
        self.session.verify = False  # Gov site SSL issues
        self._csrf_token = ""
        self._states = []
        self._total_records = 0

    @property
    def source_name(self) -> str:
        return "desagri"

    @retry(
        retry=retry_if_exception_type((requests.exceptions.RequestException, APIError)),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _fetch_token_and_states(self):
        url = f"{self.base_url}/website/crops-apy-report-web"
        logger.info("Fetching token and states from %s", url)
        res = self.session.get(url, timeout=(10, 30))
        res.raise_for_status()
        
        # Extract CSRF token
        match = re.search(r'name="_token" value="([^"]+)"', res.text)
        if match:
            self._csrf_token = match.group(1)
        else:
            raise APIError("CSRF token not found in the HTML page.")

        # Extract States using regex to avoid full BS4 parse if possible, or just use re
        # Format: <option value="35"  >Andaman and Nicobar Islands</option>
        state_block_match = re.search(r'id="fltrstates"(.*?)</select>', res.text, re.DOTALL)
        if not state_block_match:
            raise APIError("Could not find states dropdown.")
            
        options = re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', state_block_match.group(1))
        self._states = [{"id": int(val), "name": name.strip()} for val, name in options if val]
        self._total_records = len(self._states)
        logger.info("Found %d states", self._total_records)

    def discover(self) -> DiscoveryResult:
        logger.info("Running discovery against DESAgri website …")
        self._fetch_token_and_states()
        
        # To get the fields dynamically, we could do a quick post for the first state.
        # But since the user wants raw data, the fields change per state (different crops)!
        # So we just return an empty fields list and let the dynamic schema handle it per page.
        
        return DiscoveryResult(
            dataset_name="DESAgri Area, Production & Yield",
            resource_id="desagri-apy",
            source_name=self.source_name,
            fields=[],
            total_records=self._total_records,
        )

    @retry(
        retry=retry_if_exception_type((requests.exceptions.RequestException, APIError, ValueError)),
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def fetch_page(self, offset: int, limit: int) -> PageResult:
        if not self._csrf_token or not self._states:
            self._fetch_token_and_states()
            
        if offset >= len(self._states):
            return PageResult(records=[], raw_json={}, request_url="", request_params={}, total_records=self._total_records, offset=offset, limit=limit)
            
        state = self._states[offset]
        logger.info("Fetching data for State: %s (ID: %s)", state['name'], state['id'])

        data = {
            'reportformat': 'horizontal_crop_vertical_year',
            '_token': self._csrf_token,
            'fltrstates[]': str(state['id']),
            'fltrstartyear': '1997',
            'fltrendyear': '2025'
        }

        url = f"{self.base_url}/report/crop/horizontal_crop_vertical_year"
        res = self.session.post(url, data=data, timeout=(10, 300)) # 5 min timeout for big states
        res.raise_for_status()
        
        if "No Data Found" in res.text or "table" not in res.text:
            logger.warning("No data found for state %s", state['name'])
            return PageResult(
                records=[],
                raw_json={"html_length": len(res.text), "state": state['name']},
                request_url=url,
                request_params=data,
                total_records=self._total_records,
                offset=offset,
                limit=limit,
            )

        try:
            # Parse HTML table to DataFrame using StringIO
            tables = pd.read_html(StringIO(res.text))
            if not tables:
                raise ValueError("Pandas found no tables")
            df = tables[0]
            
            # Flatten multi-index columns
            if isinstance(df.columns, pd.MultiIndex):
                # Clean up tuple names: ignore 'Unnamed', join the rest
                new_cols = []
                for col_tuple in df.columns.values:
                    clean_parts = [str(p).strip() for p in col_tuple if 'Unnamed' not in str(p)]
                    # Remove duplicates in sequence (e.g. State_State_State -> State)
                    deduped = []
                    for p in clean_parts:
                        if not deduped or deduped[-1] != p:
                            deduped.append(p)
                    col_name = "_".join(deduped)
                    # Sanitize for PostgreSQL column name safety
                    col_name = re.sub(r'[^a-zA-Z0-9_]', '_', col_name)
                    col_name = re.sub(r'_+', '_', col_name).strip('_')
                    new_cols.append(col_name)
                df.columns = new_cols

            # Drop rows where everything is NaN (sub-headers sometimes parse as empty rows)
            df.dropna(how='all', inplace=True)
            
            # Convert to list of dicts
            records = df.to_dict('records')
            
            # Clean up NaN values to None for JSON/PostgreSQL
            clean_records = []
            for r in records:
                clean_r = {}
                for k, v in r.items():
                    if pd.isna(v):
                        clean_r[k] = None
                    else:
                        clean_r[k] = v
                clean_records.append(clean_r)
                
        except Exception as e:
            logger.error("Failed to parse table for state %s: %s", state['name'], e)
            raise APIError(f"Table parse failed: {e}")

        # The JSON representation is just metadata, we don't store the massive HTML text
        # to avoid blowing up PostgreSQL size limits unnecessarily, or we can store a snippet.
        return PageResult(
            records=clean_records,
            raw_json={"state": state['name'], "records_extracted": len(clean_records)},
            request_url=url,
            request_params=data,
            total_records=self._total_records,
            offset=offset,
            limit=limit,
        )

    def fetch_metadata(self) -> dict[str, Any]:
        return {"source": "desagri.gov.in HTML scraping"}

    def get_total_records(self) -> int:
        return self._total_records
