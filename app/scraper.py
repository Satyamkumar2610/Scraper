"""
scraper.py — Thin orchestration wrapper kept for backward compatibility.

The real HTTP logic lives in the source adapters (``app.sources.*``).
This module provides a convenience ``fetch_page`` that delegates to the
currently-active source so that older call-sites continue to work.
"""

from __future__ import annotations

from app.sources.base import PageResult
from app.sources.datagovin import DataGovInSource

_default_source: DataGovInSource | None = None


def _get_source() -> DataGovInSource:
    global _default_source
    if _default_source is None:
        _default_source = DataGovInSource()
    return _default_source


def fetch_page(offset: int, limit: int) -> PageResult:
    """Convenience wrapper — delegates to ``DataGovInSource.fetch_page``."""
    return _get_source().fetch_page(offset, limit)
