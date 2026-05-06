# ISIC Project Backend

Backend service for ISIC student identification system.

## Features

- **MQTT Integration**: Subscribes generically to hardware MQTT topics and accepts arbitrary hardware `baseTopic/deviceId/...` paths
- **Auto-registration**: Creates ISIC records on first scan
- **REST API**: Query scans, update ISIC information
- **Database**: SQLite with async SQLAlchemy
- **Migrations**: Alembic for schema management

## Architecture

- FastAPI application with async lifespan management
- MQTT client subscribes on startup, processes messages asynchronously
- Database models: `ISIC` (cards) and `ISICScan` (scan events)
- Foreign key relationship: scans reference ISIC cards

## MQTT Message Format

The backend is not coupled to a fixed `device/...` prefix. It expects hardware topics in the documented shape:

```text
<baseTopic>/<deviceId>/<topicSuffix>
```

Examples:

```text
device/ISIC-ESP8266-001/attendance
campus/isic/HW-ROOM-01/attendance
prod/readers/BLOCK-A-01/health
```

Attendance payloads accept JSON only:

```json
{
  "isic_identifier": "123456789"
}
```

The timestamp is automatically generated on the backend when the message is received. Creates ISIC record if identifier doesn't exist.

## API Endpoints

- `GET /health` - Health check
- `GET /scans?limit={n}&offset={n}` - List scans (paginated)
- `GET /scans/{scan_id}` - Get scan by ID
- `PATCH /isics/{isic_identifier}` - Update ISIC first_name/last_name

## Setup

**Requirements:**
- Python 3.13+
- Docker and Docker Compose

**Environment Variables:**
- `DATABASE_URL` - SQLite database path (default: `sqlite+aiosqlite:///./data/database.db`)
- `MQTT_BROKER_HOST` - MQTT broker hostname (default: `localhost`)
- `MQTT_BROKER_PORT` - MQTT broker port (default: `1883`)
- `MQTT_TOPIC` - MQTT topic subscription wildcard (default: `+/+/#`)
- `HTTP_HOST` - API host (required)
- `HTTP_PORT` - API port (required)

**Run with Docker Compose:**
```bash
cd ..
docker compose up --build backend mqtt
```

Starts backend on port 8000 and MQTT broker on port 1883.

Use `MQTT_TOPIC=#` if you want to consume every MQTT topic and let the backend ignore unrelated ones. The default `+/+/#` is generic enough for hardware topics without subscribing to the entire broker namespace.

**Run locally:**
```bash
uv sync
alembic upgrade head
uv run python -m src.main
```

## Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Development

**Dependencies:**
- `uv` for package management
- `ruff` for linting
- `mypy` for type checking
- `pytest` for testing

**Code Style:**
- Avoid `from __future__ import annotations`
- Avoid `TYPE_CHECKING` patterns; use direct imports
- Imports only at top of file, never inside functions
- Forward references use string literals with `# type: ignore[name-defined]` and `# noqa: F821`

**Run type checking:**
```bash
uv run mypy .
```

**Run linting:**
```bash
uv run ruff check --fix .
```

**Run tests:**
```bash
uv run pytest
```
