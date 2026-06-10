# Staging backend image (Python 3.11 to match pyproject constraint >=3.11)
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_INSTALLER_MAX_WORKERS=2 \
    PIP_DEFAULT_TIMEOUT=120

# Replace default sources with Aliyun mirrors (optimized for China)
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list

# System dependencies required by asyncpg/psycopg builds and healthcheck probing
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry in global env (virtualenv disabled above)
# Use Aliyun PyPI mirror for China network optimization
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com poetry==2.2.1

# Install only runtime dependencies first for better layer caching
COPY pyproject.toml poetry.lock ./

# Poetry 2.x source is configured in pyproject.toml [[tool.poetry.source]] (aliyun mirror).
# The lockfile has been regenerated to match. See ai-ledger report for details.
# POETRY_INSTALLER_MAX_WORKERS=2 and PIP_DEFAULT_TIMEOUT=120 set above for stability.
# requests.max-retries is set to 3 for transient network failure resilience.
RUN poetry config requests.max-retries 3
RUN poetry install --no-root --only main --no-ansi

# Copy source code
COPY . .

# Fix Windows CRLF line endings and make entrypoint executable
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

# Run as non-root for staging hardening
RUN useradd --create-home --shell /bin/bash mpango \
    && chown -R mpango:mpango /app
USER mpango

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
  CMD curl -fsS http://localhost:8000/health/live || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
