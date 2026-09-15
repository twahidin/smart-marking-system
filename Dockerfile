# --- stage 1: build the SPA ---
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- stage 2: python runtime ---
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    STORAGE_DIR=/data SMS_STATIC_DIR=/app/web/dist
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev
COPY alembic.ini ./
COPY --from=web /web/dist ./web/dist
RUN mkdir -p /data
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync sms serve --host 0.0.0.0 --port ${PORT:-8000}"]
