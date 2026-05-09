FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml ./
RUN uv sync --no-cache

COPY src ./src

EXPOSE 8080

CMD ["uv", "run", "python", "-m", "src.main"]
