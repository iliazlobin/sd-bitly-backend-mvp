# syntax=docker/dockerfile:1

# ---- Builder stage ----
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1

WORKDIR /build

COPY pyproject.toml ./
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install .

# ---- Runtime stage ----
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

COPY --from=builder /install /usr/local
COPY src/ src/
COPY alembic.ini .
COPY alembic/ alembic/

WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "src.bitly.main:app", "--host", "0.0.0.0", "--port", "8000"]
