# Base Python image
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base
FROM base AS builder
# Create workdir
WORKDIR /volcanoz

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copy files
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --all-groups

COPY ./app ./app
COPY ./data ./data

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-groups

FROM base
COPY --from=builder /volcanoz /volcanoz
ENV PATH="/volcanoz/.venv/bin:$PATH"
WORKDIR /volcanoz
CMD ["uv", "run","app/train.py"]
