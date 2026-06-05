#!/usr/bin/env python3
"""
main.py — Entry-point for the Government Data Ingestion Platform.

Usage:
    python main.py discover
    python main.py init-db
    python main.py scrape [--limit 100]
    python main.py resume [--limit 100]
    python main.py status
    python main.py validate
    python main.py export-csv
    python main.py export-parquet
    python main.py export-arrow
    python main.py export-json
"""

from app.cli import main

if __name__ == "__main__":
    main()
