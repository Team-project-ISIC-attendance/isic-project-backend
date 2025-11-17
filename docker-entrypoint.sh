#!/bin/sh
set -e

# Run migrations (alembic.ini should be in /app)
echo "Running database migrations..."
cd /app && uv run alembic upgrade head || echo "Warning: Migrations failed, continuing anyway..."

# Start the application
exec uv run python -m src.main

