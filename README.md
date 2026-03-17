# everest

`everest` is a batch-processing application for two existing upstream parsers:

- `fedresurs`: find bankruptcy data by `INN`
- `kad.arbitr`: find case document data by arbitration case number

The parser implementations already exist in this repository and are reused as-is through thin adapters. The application layer adds configuration, retries, persistence, batch execution, resume support, logging, and deployment packaging around those parsers.

## Stack

- Python 3.11+
- Requests
- BeautifulSoup
- OpenPyXL
- SQLAlchemy 2.x
- SQLite for quick local runs
- PostgreSQL for Docker / production-like runs
- Docker + Docker Compose

## What the app does

`fedresurs` mode:
- input column contains `INN`
- output persisted per row:
  - `inn`
  - `case_number`
  - `latest_date`
  - `status`
  - `error_message`

`kad` mode:
- input column contains case numbers
- output persisted per row:
  - `case_number`
  - `latest_date`
  - `document_name`
  - `document_title_or_description`
  - `status`
  - `error_message`

## Project structure

```text
app/
  adapters/         parser-facing adapters
  domain/           shared DTOs and domain exceptions
  parsers/          existing parser implementations
  repositories/     SQLAlchemy repositories
  services/         batch orchestration
  cli.py            CLI entrypoint
  config.py         env-based configuration
  db.py             SQLAlchemy engine/session setup
  excel.py          XLSX reader and validation
  execution.py      retry, backoff, and rate limiting
  logging_utils.py  stdout-friendly logging
  models.py         ORM models
tests/
```

## Setup

### Local Python environment

Using Poetry:

```bash
poetry install
```

Using `pip`:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Local run

SQLite works by default, so no DB service is required for a quick run.

1. Create an `.env` from the example:

```bash
cp .env.example .env
```

2. Run the batch command:

```bash
poetry run everest --source fedresurs --input ./input/fedresurs.xlsx --sheet Sheet1 --column INN
```

Or:

```bash
python -m app.cli --source kad --input ./input/kad.xlsx --sheet Sheet1 --column CASE_NUMBER
```

## Docker run

Build the image:

```bash
docker build -t everest:latest .
```

Show CLI help inside the container:

```bash
docker run --rm everest:latest --help
```

Run against a local SQLite file mounted from the host:

```bash
docker run --rm \
  -v "$(pwd):/app" \
  -e DATABASE_URL=sqlite:///./everest.db \
  everest:latest \
  --source fedresurs \
  --input ./input/fedresurs.xlsx \
  --sheet Sheet1 \
  --column INN
```

## Docker Compose

`docker-compose.yml` provides:

- `db`: PostgreSQL 16
- `app`: the batch application configured to use PostgreSQL through `DATABASE_URL`

Start PostgreSQL in the background:

```bash
docker compose up -d db
```

Run an actual batch job against PostgreSQL:

```bash
docker compose run --rm app \
  --source fedresurs \
  --input ./input/fedresurs.xlsx \
  --sheet Sheet1 \
  --column INN
```

KAD example:

```bash
docker compose run --rm app \
  --source kad \
  --input ./input/kad.xlsx \
  --sheet Sheet1 \
  --column CASE_NUMBER \
  --resume
```

## Environment variables

The app loads configuration from environment variables and also supports a local `.env` file.

Core settings:

```dotenv
DATABASE_URL=sqlite:///./everest.db
SOURCE_MODE=fedresurs
WORKER_COUNT=1
REQUEST_DELAY_SECONDS=0.0
RETRY_ATTEMPTS=3
RETRY_BACKOFF_BASE_SECONDS=1.0
RETRY_BACKOFF_MULTIPLIER=2.0
LOG_LEVEL=INFO
PROXY_URL=
USER_AGENT=
```

Meaning:

- `DATABASE_URL`: SQLAlchemy URL. Examples:
  - `sqlite:///./everest.db`
  - `postgresql+psycopg://everest:everest@db:5432/everest`
- `SOURCE_MODE`: default CLI source if `--source` is omitted
- `WORKER_COUNT`: conservative bounded concurrency
- `REQUEST_DELAY_SECONDS`: minimum delay between requests across workers
- `RETRY_ATTEMPTS`: retry count for transient network failures
- `RETRY_BACKOFF_BASE_SECONDS`: first retry delay
- `RETRY_BACKOFF_MULTIPLIER`: exponential backoff multiplier
- `LOG_LEVEL`: logging level, for example `INFO` or `DEBUG`
- `PROXY_URL`: optional outbound proxy setting for future HTTP client wiring
- `USER_AGENT`: optional user-agent override used by request header creation

## Input Excel format

The reader expects:

- `.xlsx` files only
- first row is the header row
- a named column passed with `--column`
- empty rows in that column are skipped

Fedresurs example:

| INN |
|---|
| 231138771115 |
| 7707083893 |

KAD example:

| CASE_NUMBER |
|---|
| A32-28873/2024 |
| A40-12345/2024 |

## CLI usage

General form:

```bash
python -m app.cli \
  --source fedresurs|kad \
  --input path/to/file.xlsx \
  --sheet Sheet1 \
  --column INN_OR_CASE_COLUMN \
  --resume \
  --limit 100
```

Fedresurs examples:

```bash
python -m app.cli \
  --source fedresurs \
  --input ./input/fedresurs.xlsx \
  --sheet Sheet1 \
  --column INN
```

```bash
python -m app.cli \
  --source fedresurs \
  --input ./input/fedresurs.xlsx \
  --sheet Sheet1 \
  --column INN \
  --worker-count 2 \
  --request-delay-seconds 1.5 \
  --retry-attempts 4 \
  --retry-backoff-base-seconds 2 \
  --retry-backoff-multiplier 2 \
  --resume
```

KAD example:

```bash
python -m app.cli \
  --source kad \
  --input ./input/kad.xlsx \
  --sheet Sheet1 \
  --column CASE_NUMBER \
  --resume
```

## Retries, resume, and logging

Retries:

- only transient network failures are retried
- retries use exponential backoff
- permanent validation and malformed-response errors are not retried
- anti-bot / blocking suspicion is treated as a permanent failure

Resume:

- each row is persisted before and after processing
- the DB stores statuses:
  - `processing`
  - `success`
  - `not_found`
  - `temporary_failure`
  - `permanent_failure`
- `--resume` skips rows already in terminal states:
  - `success`
  - `not_found`
  - `permanent_failure`
- `processing` and `temporary_failure` rows are retried on the next run

Logging:

- logs go to stdout with timestamp, level, and message
- each row logs its result
- retry attempts log attempt number, delay, and error
- this format is Docker-friendly and works well with container log collection

## Testing

Run non-integration tests:

```bash
pytest -m "not integration"
```

Run parser unit tests only:

```bash
pytest tests/test_parsers.py
```

The integration tests call live external services and require network access.
