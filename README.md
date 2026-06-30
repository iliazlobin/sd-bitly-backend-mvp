# Bitly URL Shortener MVP

[![Lint](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/lint.yml/badge.svg)](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/lint.yml)
[![CI](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/ci.yml/badge.svg)](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/ci.yml)
[![Functional](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/functional.yml/badge.svg)](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/functional.yml)

A REST API that shortens long URLs into 7-character codes, redirects on lookup with Redis caching, and tracks click counts. Built on FastAPI, PostgreSQL, and Redis.

## Quickstart

```bash
docker compose up --build -d
curl -sf http://localhost:8010/healthz
# {"status":"healthy"}
```

Create a short URL, then redirect:

```bash
curl -sf http://localhost:8010/api/urls \
  -H "Content-Type: application/json" \
  -d '{"long_url":"https://example.com/hello"}'
# {"short_code":"0000001","short_url":"http://localhost:8010/0000001",...}

curl -sI http://localhost:8010/0000001
# HTTP/1.1 301 Moved Permanently
# Location: https://example.com/hello
```

## API Reference

### `POST /api/urls` — Create a short URL

Create an auto-generated short code or specify a custom alias.

```
Request:  {"long_url": "https://example.com/path",
           "custom_alias": "my-link",          // optional, 1–20 base62 chars
           "expires_at": "2026-12-31T23:59:59Z"}  // optional, ISO 8601

Response: 201 {"short_code": "0000001",
               "short_url": "http://localhost:8010/0000001",
               "long_url": "https://example.com/path",
               "clicks": 0,
               "created_at": "2026-06-29T12:00:00Z",
               "expires_at": null}
```

Status codes: `201` created, `409` alias taken, `422` validation error, `429` rate limited.

### `GET /{short_code}` — Redirect to original URL

Resolves the short code and redirects. Cached in Redis for 24 hours.

```
Response: 301 Moved Permanently
  Location: https://example.com/path
  Cache-Control: private, max-age=90
```

Status codes: `301` success, `404` not found, `410` expired.

### `GET /api/urls/{short_code}/stats` — Click statistics

Returns click count and metadata for a short URL.

```
Response: 200 {"short_code": "0000001",
               "long_url": "https://example.com/path",
               "clicks": 42,
               "created_at": "2026-06-29T12:00:00Z",
               "expires_at": null}
```

Status codes: `200` success, `404` not found.

### `GET /healthz` — Health check

```
Response: 200 {"status": "healthy"}
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://bitly:bitly@db:5432/bitly` | PostgreSQL connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string |
| `RATE_LIMIT_REQUESTS` | `10` | Max POST /api/urls requests per IP per window |
| `RATE_LIMIT_WINDOW_S` | `1` | Rate-limit window duration in seconds |
| `APP_PORT` | `8010` | Host port for the application |

All variables are set in `.env.example`. For local development, change the host in `DATABASE_URL` and `REDIS_URL` to `localhost`.

## Testing

```bash
# Unit tests (pure functions — no services needed)
pytest tests/unit/ -v

# Functional tests (requires PostgreSQL and Redis)
pytest tests/functional/ -v

# Black-box acceptance tests (requires a running instance)
API_BASE_URL=http://localhost:8010 pytest verify/acceptance/ -v
```

Functional tests use in-memory SQLite and fakeredis — no external services required. Acceptance tests hit the real API over HTTP.

## Project Layout

```
sd-bitly-backend-mvp/
├── src/bitly/
│   ├── main.py            # FastAPI app factory, lifespan, /healthz
│   ├── config.py          # pydantic-settings
│   ├── database.py        # Async SQLAlchemy engine + session
│   ├── redis.py           # Async Redis client
│   ├── models/url.py      # SQLAlchemy URL model
│   ├── schemas/url.py     # Pydantic request/response schemas
│   ├── routers/
│   │   ├── urls.py        # POST /api/urls, GET /api/urls/{code}/stats
│   │   └── redirect.py    # GET /{short_code}
│   └── services/
│       ├── url_service.py # Business logic (create, lookup, stats, canonicalize)
│       ├── codec.py       # base62 encode/decode
│       └── rate_limiter.py # Fixed-window rate limiter (Redis)
├── tests/
│   ├── unit/              # Pure-function unit tests
│   └── functional/        # Integration tests (SQLite + fakeredis)
├── verify/acceptance/     # Black-box acceptance suite (one file per FR)
├── alembic/               # Database migrations
├── docker-compose.yml     # Compose stack (app + Postgres + Redis)
├── Dockerfile             # Multi-stage build on python:3.12-slim
├── pyproject.toml         # Project metadata and dependencies
├── SPEC.md                # Engineering specification
├── DESIGN.md              # Design document
└── DEPLOY.md              # Deployment guide
```

## Limitations

This is an MVP. It omits:

- **No authentication.** All endpoints are public. Rate limiting keys on IP address, so all users behind a NAT share the same bucket.
- **No deduplication.** Submitting the same long URL twice produces two different short codes.
- **No analytics pipeline.** Click counts are a simple integer column — no referrer tracking, geo breakdown, or time-series aggregation.
- **No safety scanning.** Links are not checked for phishing or malware.
- **Single-writer ID generation.** The `BIGSERIAL` counter in PostgreSQL is fine for ~70 creates/sec but becomes a bottleneck with multiple writer instances. Production would use ZooKeeper range allocation.
- **Single-layer cache.** Only Redis; no in-process LRU or CDN edge layer.
- **Fixed-window rate limiter.** Allows up to 2× burst at window boundaries. Production would use a sliding window or token bucket.
- **No multi-region deployment.** Single PostgreSQL instance, single Redis instance.
