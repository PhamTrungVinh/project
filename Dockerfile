FROM python:3.13-slim

# libgomp1 cần cho faiss-cpu, curl cần để cài uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Cài uv (package manager dùng cho toàn bộ project)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy trước 2 file này để tận dụng Docker layer cache - chỉ re-run uv sync
# khi pyproject.toml/uv.lock thay đổi, không phải mỗi lần sửa code Python
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy toàn bộ code
COPY . .

# Model embedding sẽ tự tải về HF cache lần đầu chạy nếu chưa có (cần mạng);
# nên mount volume ~/.cache/huggingface hoặc pre-bake nếu muốn build offline-ready.
ENV HF_HOME=/app/.cache/huggingface

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]