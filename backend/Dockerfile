FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry

# Configure Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copy dependency files first for better caching
COPY pyproject.toml poetry.lock ./

# Install Python dependencies
ARG INSTALL_TEST_DEPS=false
RUN if [ "$INSTALL_TEST_DEPS" = "true" ]; then poetry install --no-root --no-interaction --no-ansi --no-cache --with test; else poetry install --no-root --no-interaction --no-ansi --no-cache; fi

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash mpango
RUN chown -R mpango:mpango /app
USER mpango

# Expose port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Command will be overridden in docker-compose
CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]