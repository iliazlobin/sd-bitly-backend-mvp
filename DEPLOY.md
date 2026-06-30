# Deployment Guide

## Prerequisites

- **Docker** (20.10+) and **Docker Compose** (v2, the `docker compose` plugin)
- **curl** for health checks
- **Python 3.11+** and **pip** (for local development only)
- An available host port (default: `8010`)

> **Port conflicts:** The default `APP_PORT=8010` avoids collisions with common services (5432/Postgres, 6379/Redis, 8000/8080). If 8010 is taken, set `APP_PORT` in `.env` or on the command line.

## Docker Compose (Recommended)

### 1. Start the stack

```bash
docker compose up --build -d
```

This builds the application image, starts PostgreSQL 16 and Redis 7, waits for both to become healthy, runs Alembic migrations, and launches the API server.

### 2. Verify the deployment

```bash
# Health check
curl -sf http://localhost:8010/healthz
# Expected: {"status":"healthy"}

# Check service status
docker compose ps
```

### 3. Run acceptance tests

```bash
API_BASE_URL=http://localhost:8010 pytest verify/acceptance/ -v
```

### 4. Stop the stack

```bash
# Stop containers (preserve data)
docker compose down

# Stop and delete volumes (fresh start)
docker compose down -v
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://bitly:bitly@db:5432/bitly` | Async PostgreSQL connection string. The compose file sets this automatically to point at the `db` service. For local dev, change `db` to `localhost`. |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection string. The compose file sets this to the `redis` service. For local dev, change `redis` to `localhost`. |
| `RATE_LIMIT_REQUESTS` | `10` | Max requests per IP within the rate limit window. |
| `RATE_LIMIT_WINDOW_S` | `1` | Rate limit window duration in seconds. |
| `APP_PORT` | `8010` | Host port mapping for the API. Container always listens on 8000 internally. |
| `APP_HOST` | `0.0.0.0` | Host/IP the server binds to inside the container. |

To override, create a `.env` file or pass on the command line:

```bash
# .env file
APP_PORT=9000
RATE_LIMIT_REQUESTS=50

# Or inline
APP_PORT=9000 docker compose up -d
```

## Database Migrations

Migrations run automatically on container startup via the compose `command`:

```sh
alembic upgrade head && uvicorn src.bitly.main:app --host 0.0.0.0 --port 8000
```

The initial migration (`001_create_urls_table`) creates:

| Table | Purpose |
|-------|---------|
| `urls` | URL mappings — short_code, long_url, clicks, created_at, expires_at |

With a unique index on `short_code` for fast lookups.

### Manual migration (local development)

```bash
pip install -e ".[dev]"
export DATABASE_URL=postgresql+asyncpg://bitly:bitly@localhost:5432/bitly
alembic upgrade head
```

### Check current migration state

```bash
# Inside the container
docker compose exec app alembic current

# Or locally
alembic current
```

## Local Development

For development without Docker Compose (requires running PostgreSQL and Redis instances):

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Set environment variables (point to your local services)
export DATABASE_URL=postgresql+asyncpg://bitly:bitly@localhost:5432/bitly
export REDIS_URL=redis://localhost:6379/0

# 3. Run migrations
alembic upgrade head

# 4. Start the server with hot reload
uvicorn src.bitly.main:app --reload --port 8010

# 5. Run tests
pytest tests/ -v                                          # White-box
API_BASE_URL=http://localhost:8010 pytest verify/acceptance/ -v  # Black-box
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | Health check — returns `{"status":"healthy"}` |
| `POST` | `/api/urls` | Create a short URL — body: `{"long_url":"...", "custom_alias":"...", "expires_at":"..."}` |
| `GET` | `/api/urls/{short_code}/stats` | Get click stats for a short URL |
| `GET` | `/{short_code}` | Redirect to the long URL (301) |

### Smoke test

```bash
# Create a short URL
curl -sf http://localhost:8010/api/urls \
  -H "Content-Type: application/json" \
  -d '{"long_url":"https://example.com/hello"}' | python3 -m json.tool

# Expected: {"short_code":"...", "short_url":"http://localhost:8010/...",
#            "long_url":"https://example.com/hello", "clicks":0, ...}

# Follow the redirect (replace SHORT_CODE with the actual code)
curl -sI http://localhost:8010/SHORT_CODE
# Expected: HTTP/1.1 301 Moved Permanently
#           Location: https://example.com/hello

# Check stats
curl -sf http://localhost:8010/api/urls/SHORT_CODE/stats | python3 -m json.tool
# Expected: {"clicks": 1, ...}
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker compose logs app --tail=100

# Common issues:
# - "connection refused" on DB → Postgres isn't ready yet (retry after healthcheck passes)
# - "relation does not exist" → migrations didn't run (check app startup logs)
```

### Port already in use

```bash
# Find what's using port 8010
lsof -i :8010

# Use a different port
APP_PORT=9000 docker compose up -d
```

### Database connection errors

```bash
# Verify Postgres is running and healthy
docker compose ps db
docker compose exec db pg_isready -U bitly -d bitly

# Check the DATABASE_URL the app sees
docker compose exec app env | grep DATABASE_URL
```

### Redis connection errors

```bash
# Verify Redis is running and healthy
docker compose ps redis
docker compose exec redis redis-cli ping
# Expected: PONG

# Check the REDIS_URL the app sees
docker compose exec app env | grep REDIS_URL
```

### Migrations fail

```bash
# Check current state
docker compose exec app alembic current

# Reset and re-run (DEVELOPMENT ONLY — destroys data)
docker compose down -v
docker compose up -d
```

### Rate limiting

The default rate limit is 10 requests per second per IP. If you hit 429 responses:

```bash
# Check the rate limit config
docker compose exec app env | grep RATE_LIMIT

# Increase the limit (restart required)
RATE_LIMIT_REQUESTS=100 docker compose up -d
```

## Acceptance Suite

```bash
API_BASE_URL=http://localhost:8010 pytest verify/acceptance/ -v
```

All 5 functional requirements should pass (FR-1 through FR-5):
- FR1: Create short URL
- FR2: Redirect to long URL
- FR3: Get click stats
- FR4: Custom alias support
- FR5: Expiration support

## Production Considerations

This is a single-process MVP. For production deployment:

- **Separate processes:** Run the API server behind a load balancer; consider a dedicated migration job
- **Horizontal scaling:** Deploy multiple API replicas — the rate limiter is Redis-based and works correctly across instances
- **Connection pooling:** Increase `pool_size` and `max_overflow` in `database.py` for high concurrency
- **Monitoring:** Add structured logging, metrics export (Prometheus), and alerting
- **Graceful shutdown:** The lifespan handler closes DB and Redis connections cleanly; ensure your orchestrator sends SIGTERM with adequate drain time
- **Secrets management:** Replace hardcoded credentials with secrets injection (Docker secrets, Vault, etc.)
- **Backups:** Configure PostgreSQL WAL archiving and point-in-time recovery; persist Redis data with AOF or RDB snapshots
