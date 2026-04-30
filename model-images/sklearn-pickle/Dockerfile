FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV MODEL_PATH=/models/model.pkl \
    PYTHONPATH=/app/src \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "sklearn_pickle_server.app:app", "--host", "0.0.0.0", "--port", "8000"]
