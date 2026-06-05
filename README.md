# 🇮🇳 Government Data Ingestion Platform

A **production-grade**, fault-tolerant Python pipeline for ingesting agricultural datasets from Government of India APIs (Data.gov.in and beyond) into PostgreSQL — with full data lineage, schema evolution, data-quality validation, and multi-format export.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI  (main.py)                          │
├─────────────────────────────────────────────────────────────────┤
│  discover │ init-db │ scrape │ resume │ status │ validate │ …  │
├──────┬──────┬────────┬──────┬──────────┬──────────┬─────────────┤
│Source│Parser│Scheduler│Lineage│Validation│ Metrics │  Exporters │
│Adaptr│      │(Orchstr)│      │          │         │             │
├──────┴──────┴────────┴──────┴──────────┴──────────┴─────────────┤
│                     SQLAlchemy  (ORM)                           │
├─────────────────────────────────────────────────────────────────┤
│                     PostgreSQL  15                              │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
API  →  Raw JSON (filesystem + DB)  →  Bronze (raw records)  →  Silver (standardised)
                                                                       ↓
                                                               Validation → Issues
                                                                       ↓
                                                               Exports (CSV / Parquet / Arrow / JSONL)
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Source Adapters** | Pluggable adapter pattern — add any GOI data source by subclassing `BaseDataSource` |
| **Auto-Discovery** | Inspects the API to learn fields, types, total records, and pagination strategy |
| **Bronze / Silver Layers** | Raw records preserved exactly; silver layer standardised & typed |
| **Data Lineage** | Every record carries a SHA-256 hash, source dataset, resource ID, and ingestion timestamp |
| **Schema Evolution** | New fields in the API are detected, logged, and catalogued without breaking the pipeline |
| **Deduplication** | `ON CONFLICT DO UPDATE` upserts on deterministic record hashes |
| **Resumability** | Crash → restart → pick up from the last successful offset, no duplicates |
| **Data Quality** | Rule-based validation (nulls, negatives, malformed names, invalid years) |
| **Metrics** | Per-run throughput, insert/update/fail counts, duration |
| **Multi-Format Export** | CSV, Parquet, Arrow IPC, JSONL |
| **Retry Logic** | Exponential back-off (up to 5 retries) for 429 / 5xx / timeouts |
| **Connection Pooling** | SQLAlchemy pool (size 20, overflow 10) for batch performance |
| **Docker** | One-command deployment with `docker compose` |
| **Alembic** | Database migrations for schema evolution |

---

## Quick Start

### 1. Clone & configure

```bash
cp .env.example .env
# Edit .env and set your API_KEY
```

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

### 3. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Initialise the database

```bash
python main.py init-db
```

### 5. Run discovery

```bash
python main.py discover
```

### 6. Scrape

```bash
python main.py scrape               # default page size (100)
python main.py scrape --limit 500   # larger pages
```

### 7. Resume after crash

```bash
python main.py resume
```

---

## All CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py discover` | Inspect the API, persist metadata and field catalogue |
| `python main.py init-db` | Create all PostgreSQL tables |
| `python main.py scrape [--limit N]` | Full-refresh scrape |
| `python main.py resume [--limit N]` | Resume from last incomplete run |
| `python main.py status` | Show job-queue statistics |
| `python main.py validate` | Run data-quality checks on the silver layer |
| `python main.py export-csv` | Export silver data to `exports/*.csv` |
| `python main.py export-parquet` | Export silver data to `exports/*.parquet` |
| `python main.py export-arrow` | Export silver data to `exports/*.arrow` |
| `python main.py export-json` | Export silver data to `exports/*.jsonl` |

---

## Docker Deployment

```bash
# One-command deployment
docker compose up --build

# Run a scrape inside Docker
docker compose run scraper scrape --limit 500

# Resume
docker compose run scraper resume

# Check status
docker compose run scraper status
```

---

## Database Schema

### Metadata Layer

- **`metadata_datasets`** — one row per logical dataset
- **`metadata_fields`** — discovered field catalogue (name + type)
- **`metadata_api_runs`** — top-level run tracking

### Job Queue

- **`scrape_jobs`** — per-offset job with status (pending / running / completed / failed)

### Storage Layers

- **`raw_responses`** — exact API response JSON + filesystem path
- **`crop_statistics_raw`** (Bronze) — one row per source record, raw JSON preserved
- **`crop_statistics_standardized`** (Silver) — standardised, typed, analytics-ready

### Quality & Observability

- **`validation_runs`** / **`data_quality_issues`** — validation results
- **`ingestion_metrics`** — per-run performance counters

---

## Sample Queries

```sql
-- Total records ingested
SELECT count(*) FROM crop_statistics_standardized;

-- Records per state
SELECT state_name, count(*)
  FROM crop_statistics_standardized
 GROUP BY state_name
 ORDER BY count(*) DESC;

-- Top crops by production
SELECT crop_name, sum(production_tonnes) as total_production
  FROM crop_statistics_standardized
 WHERE production_tonnes IS NOT NULL
 GROUP BY crop_name
 ORDER BY total_production DESC
 LIMIT 20;

-- Data quality issues summary
SELECT issue_type, severity, count(*)
  FROM data_quality_issues
 GROUP BY issue_type, severity
 ORDER BY count(*) DESC;

-- Ingestion throughput history
SELECT run_id, records_inserted, duration_seconds, throughput_per_second
  FROM ingestion_metrics
 ORDER BY created_at DESC;

-- Job queue health
SELECT status, count(*) FROM scrape_jobs GROUP BY status;
```

---

## Adding a New Data Source

1. Create `app/sources/my_source.py`
2. Subclass `BaseDataSource`
3. Implement `discover()`, `fetch_page()`, `fetch_metadata()`, `get_total_records()`
4. Register it in `cli.py` (or add a `--source` flag)

The validation, storage, lineage, metrics, and export layers work unchanged.

---

## Project Structure

```
project/
├── app/
│   ├── __init__.py
│   ├── config.py          # pydantic-settings configuration
│   ├── database.py        # SQLAlchemy engine & session
│   ├── models.py          # All ORM table definitions
│   ├── scraper.py         # Backward-compat fetch wrapper
│   ├── parser.py          # Field extraction, schema detection, bronze→silver mapping
│   ├── scheduler.py       # Pipeline orchestrator (discovery, jobs, ingest)
│   ├── logger.py          # Rotating-file structured logger
│   ├── validation.py      # Data-quality rule engine
│   ├── lineage.py         # SHA-256 record hashing & lineage enrichment
│   ├── metrics.py         # Run-level performance tracking
│   ├── exporters.py       # CSV / Parquet / Arrow / JSONL exporters
│   ├── cli.py             # argparse CLI
│   └── sources/
│       ├── __init__.py
│       ├── base.py        # BaseDataSource ABC
│       ├── datagovin.py   # Data.gov.in adapter
│       └── desagri.py     # DESAgri stub (future)
├── migrations/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── raw/                   # Raw API responses (YYYY/MM/DD/*.json)
├── exports/               # Exported files
├── logs/                  # Rotating log files
├── .env                   # Your environment variables (git-ignored)
├── .env.example           # Template
├── alembic.ini            # Alembic configuration
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── main.py                # Entry-point
└── README.md
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `API_KEY is not set` | Add your Data.gov.in API key to `.env` |
| `Connection refused` on PostgreSQL | Ensure `docker compose up -d postgres` is running |
| Scrape stops mid-way | Run `python main.py resume` to pick up where it left off |
| `HTTP 429` errors | The retry logic handles this automatically (exponential back-off) |
| New fields in API | The pipeline detects and logs them; they are stored in bronze as raw JSON |
| Duplicate records | Deduplication via `ON CONFLICT DO UPDATE` on the record hash prevents duplicates |

---

## License

Internal use — Government of India open data.
