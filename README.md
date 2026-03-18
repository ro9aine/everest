# everest

`everest` reads INNs from an `.xlsx` file, queries `fedresurs`, derives the bankruptcy case number, then queries `kad.arbitr` and persists the results.

## What it does

For each non-empty value from the selected Excel column:

1. `FedResursParser.find_persons(inn)`
2. takes the first matched person
3. `FedResursParser.get_bankruptcy_info(guid)`
4. takes `legalCases[0].number`
5. `KadParser.search_by_number(number)`
6. takes the first KAD card
7. `KadParser.get_card_info(card)`
8. stores data in two tables

Persisted tables:

- `fedresurs_lookup_results`
  - `id`
  - `inn` (unique)
  - `timestamp`
- `kad_arbitr_lookup_results`
  - `id`
  - `number` (unique)
  - `reg_date`
  - `document_name`

Current KAD mapping:

- `document_name` <- `ResultText`
- `reg_date` <- `RegDate`

## Stack

- Python 3.11+
- Requests
- BeautifulSoup
- OpenPyXL
- SQLAlchemy 2.x
- SQLite or PostgreSQL
- Docker + Docker Compose

## Project structure

```text
app/
  parsers/          source parsers and retry wrappers
  repositories/     SQLAlchemy repositories
  services/         batch orchestration
  cli.py            CLI entrypoint
  config.py         env-based configuration
  db.py             SQLAlchemy engine/session setup
  excel.py          XLSX reader and validation
  logging_utils.py  stdout logging
  models.py         ORM models
tests/
```

## Local setup

Using Poetry:

```bash
poetry install --with dev
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

SQLite works by default.

```bash
poetry run everest --input ./sample.xlsx --column INN
```

Or:

```bash
python -m app.cli --input ./sample.xlsx --column INN
```

## Docker

Build:

```bash
docker build -t everest:latest .
```

Show help:

```bash
docker run --rm everest:latest --help
```

Run with a mounted local file:

```bash
docker run --rm \
  -v "$(pwd):/app" \
  -e DATABASE_URL=sqlite:///./everest.db \
  everest:latest \
  --input /app/sample.xlsx \
  --column INN
```

## Docker Compose

Start PostgreSQL:

```bash
docker compose up -d db
```

Run the app:

```bash
docker compose run --rm --build app --input /app/sample.xlsx --column INN
```

If you use another workbook:

```bash
docker compose run --rm --build app --input /app/your-file.xlsx --column INN
```

## Environment variables

Supported settings:

```dotenv
DATABASE_URL=sqlite:///./everest.db
LOG_LEVEL=INFO
USER_AGENT=
RETRY_ATTEMPTS=3
RETRY_BACKOFF_SECONDS=1.0
RETRY_BACKOFF_MULTIPLIER=2.0
```

Meaning:

- `DATABASE_URL`: SQLAlchemy URL
- `LOG_LEVEL`: logging level
- `USER_AGENT`: optional override for generated request headers
- `RETRY_ATTEMPTS`: retry count for transient parser request failures
- `RETRY_BACKOFF_SECONDS`: initial retry delay
- `RETRY_BACKOFF_MULTIPLIER`: delay multiplier between attempts

## Retries and logging

Retries are implemented through parser wrapper classes:

- retries `requests.ConnectionError`
- retries `requests.Timeout`
- retries `HTTP 429`
- retries `HTTP 5xx`
- does not retry non-transient errors like `HTTP 404`

Logging:

- one line per processed row
- failures are logged without stack traces in normal batch flow
- final summary prints `total`, `success`, `failed`, `skipped`

## Testing

Run all default tests:

```bash
poetry run pytest
```

Run parser tests only:

```bash
poetry run pytest tests/test_parsers.py
```

Run integration tests:

```bash
poetry run test-integration
```

Integration tests hit live external services and require outbound network access.
