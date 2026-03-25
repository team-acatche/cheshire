FROM python:3.12-slim

WORKDIR /app

# Install system packages needed by some Python libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=2.3.2
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

# Make Poetry install packages directly into the container Python
ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copy dependency files first for better Docker cache use
COPY pyproject.toml poetry.lock ./

# Install Python dependencies
RUN poetry install --no-root && rm -rf $POETRY_CACHE_DIR

# Copy application source
COPY src ./src

EXPOSE 8000

# Optional healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/healthcheck || exit 1

# Run backend server.py
CMD ["poetry", "run", "uvicorn", "server:api", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]