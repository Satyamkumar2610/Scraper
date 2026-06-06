"""
cli.py — Command-line interface for the ingestion platform.

Commands
--------
  discover        Inspect the remote API and persist metadata.
  init-db         Create all PostgreSQL tables.
  scrape          Full-refresh scrape.
  resume          Resume from last incomplete run.
  status          Show job-queue statistics.
  export-csv      Export raw data to CSV.
  export-parquet  Export raw data to Parquet.
  export-arrow    Export raw data to Arrow IPC.
  export-json     Export raw data to JSONL.
"""

from __future__ import annotations

import argparse
import sys

from app.config import settings
from app.database import get_db, init_db
from app.exporters import (
    export_arrow,
    export_csv,
    export_json,
    export_parquet,
    export_xlsx,
)
from app.logger import logger
from app.scheduler import (
    get_status,
    perform_discovery,
    resume_scrape,
    start_scrape,
)
from app.sources.base import BaseDataSource


def _make_source() -> BaseDataSource:
    """Helper to instantiate the appropriate adapter."""
    from app.sources.desagri import DESAgriSource
    return DESAgriSource()


def cmd_discover(_args: argparse.Namespace) -> None:
    source = _make_source()
    result = perform_discovery(source)
    print(f"\n✓ Discovered {len(result.fields)} fields, "
          f"{result.total_records:,} total records.\n")
    print("Fields:")
    for f in result.fields:
        print(f"  • {f.get('id', '?'):30s}  ({f.get('type', '?')})")


def cmd_init_db(_args: argparse.Namespace) -> None:
    init_db()
    logger.info("All tables created (if not already present).")
    print("✓ Database initialised.")


def cmd_scrape(args: argparse.Namespace) -> None:
    source = _make_source()
    start_scrape(source, limit=args.limit)
    print("✓ Scrape complete.")


def cmd_resume(args: argparse.Namespace) -> None:
    source = _make_source()
    resume_scrape(source, limit=args.limit)
    print("✓ Resume complete.")


def cmd_status(_args: argparse.Namespace) -> None:
    stats = get_status()
    print("\n─── Job Queue Status ───")
    for k, v in stats.items():
        print(f"  {k.replace('_', ' ').title():25s} {v}")
    print()


def cmd_export_csv(_args: argparse.Namespace) -> None:
    path = export_csv()
    print(f"✓ Exported to {path}")


def cmd_export_parquet(_args: argparse.Namespace) -> None:
    path = export_parquet()
    print(f"✓ Exported to {path}")


def cmd_export_arrow(_args: argparse.Namespace) -> None:
    path = export_arrow()
    print(f"✓ Exported to {path}")


def cmd_export_json(_args: argparse.Namespace) -> None:
    path = export_json()
    print(f"✓ Exported to {path}")


def cmd_export_xlsx(_args: argparse.Namespace) -> None:
    path = export_xlsx()
    print(f"✓ Exported to {path}")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="gov-data-ingest",
        description="Production-grade Government Data Ingestion Platform",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # discover
    sub.add_parser("discover", help="Inspect the remote API and persist metadata")

    # init-db
    sub.add_parser("init-db", help="Create all PostgreSQL tables")

    # scrape
    p_scrape = sub.add_parser("scrape", help="Full-refresh scrape")
    p_scrape.add_argument(
        "--limit", type=int, default=settings.DEFAULT_PAGE_SIZE,
        help="Records per page (default: %(default)s)",
    )

    # resume
    p_resume = sub.add_parser("resume", help="Resume from last incomplete run")
    p_resume.add_argument(
        "--limit", type=int, default=settings.DEFAULT_PAGE_SIZE,
        help="Records per page (default: %(default)s)",
    )

    # status
    sub.add_parser("status", help="Show job-queue statistics")

    # exports
    sub.add_parser("export-csv", help="Export raw data to CSV")
    sub.add_parser("export-parquet", help="Export raw data to Parquet")
    sub.add_parser("export-arrow", help="Export raw data to Arrow IPC")
    sub.add_parser("export-json", help="Export raw data to JSONL")
    sub.add_parser("export-xlsx", help="Export raw data to XLSX")

    return parser


COMMAND_MAP = {
    "discover": cmd_discover,
    "init-db": cmd_init_db,
    "scrape": cmd_scrape,
    "resume": cmd_resume,
    "status": cmd_status,
    "export-csv": cmd_export_csv,
    "export-parquet": cmd_export_parquet,
    "export-arrow": cmd_export_arrow,
    "export-json": cmd_export_json,
    "export-xlsx": cmd_export_xlsx,
}


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    handler = COMMAND_MAP.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)
