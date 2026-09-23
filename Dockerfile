FROM python:3.13-slim

# libgomp1 is required by faiss-cpu; curl is needed to install uv.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv, the package manager used by this project.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency files first to reuse the Docker build cache.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Copy application code.
COPY . .

# The embedding model downloads to this cache on first use unless pre-baked.
ENV HF_HOME=/app/.cache/huggingface

EXPOSE 8000

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn main:app --host 0.0.0.0 --port 8000"]
