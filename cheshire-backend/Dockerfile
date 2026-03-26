# ─────────────────────────────────────────────────────────────
# Stage 1: Build
# Installs system build deps, Poetry, and all Python packages
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS build

WORKDIR /app

# Install system packages needed to compile Python libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (used only to export requirements, not to install)
ENV POETRY_VERSION=2.3.2
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION" "poetry-plugin-export"

# Copy dependency files first for better Docker cache use
COPY pyproject.toml poetry.lock ./

# Export production dependencies, strip out heavy NVIDIA/PyTorch GPU packages,
# install the CPU versions of PyTorch first, then install the rest.
RUN poetry export --without dev --without-hashes -f requirements.txt -o requirements.txt \
    && sed -i -e '/^nvidia-/d' requirements.txt \
    && sed -i -e 's/^\(torch==[0-9.]*\)/\1+cpu/g' requirements.txt \
    && sed -i -e 's/^\(torchvision==[0-9.]*\)/\1+cpu/g' requirements.txt \
    && sed -i -e 's/^\(torchaudio==[0-9.]*\)/\1+cpu/g' requirements.txt \
    && sed -i -e '/^triton==/d' requirements.txt \
    && pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu \
    && rm -f requirements.txt



# ─────────────────────────────────────────────────────────────
# Stage 2: Run
# Lean runtime image — no Poetry, no build-essential
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS run

WORKDIR /app

# Install only the runtime system libraries needed by Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from the build stage
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin

# Copy application source
COPY src ./src

EXPOSE 8000

# Optional healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/healthcheck || exit 1

# Run backend server directly — no poetry needed at runtime
CMD ["uvicorn", "server:api", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]