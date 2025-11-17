FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./

# Install dependencies
RUN uv sync --frozen

# Create data directory for SQLite database with proper permissions
RUN mkdir -p /app/data && chmod 755 /app/data

# Copy entrypoint script
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Expose port
EXPOSE 8000

# Run migrations and start the application
ENTRYPOINT ["/app/docker-entrypoint.sh"]

