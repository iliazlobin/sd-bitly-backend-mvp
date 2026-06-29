# Bitly MVP — Engineering Spec

## 1. Goal & scope
Build a working URL shortener MVP that creates short 7-character codes for long URLs, redirects on lookup with Redis caching, tracks click counts, supports custom aliases and expiration. This is the smallest functional cut — no analytics pipeline, no safety scanning, no CDN layer. The MVP proves the core create→redirect→count loop.

**In scope**
- Create short URL with auto-generated 7-char base62 code
- Redirect short code to original URL (301) with Redis caching
- Track click count per short URL
- Custom alias support (collision → 409)
- Optional expiration time (expired → 410 Gone)
- Rate limiting on create endpoint
- URL canonicalization

**Out of scope**
- Safety warnings / interstitial pages
- Full analytics pipeline (NSQ, Flink, ClickHouse)
- CDN edge caching
- Multi-region deployment
- ZooKeeper ID range allocation
- User accounts / API keys
- Bloom filter for alias collisions

## 2. Functional requirements

**FR1 — Create Short URL.** User submits `POST /api/urls` with `{"long_url": "..."}` → URL is canonicalized, a base62 7-char code is generated from an auto-increment counter, the mapping is stored, Redis is warmed. → `201 {"short_code": "abc1234", "short_url": "...", "long_url": "..."}`. Missing `long_url` → `422`.

**FR2 — Redirect Short URL.** User navigates `GET /{short_code}` → check Redis cache (24h TTL), on hit → `301 Location: {long_url}`, on miss → query PostgreSQL, populate Redis, increment click counter, → `301`. Non-existent code → `404`. Expired link → `410 Gone`.

**FR3 — Click Count.** User queries `GET /api/urls/{short_code}/stats` → returns `{"short_code": "...", "clicks": N, "created_at": "...", "expires_at": null|"..."}`. Non-existent → `404`.

**FR4 — Custom Alias.** User creates with `{"long_url": "...", "custom_alias": "my-link"}` → alias is normalized (lowercase, base62 chars, ≤20 chars), checked for collision. Success → `201`. Collision → `409 {"detail": "Alias already taken", "existing": {"short_url": "..."}}`. Invalid alias chars → `422`.

**FR5 — URL Expiration.** User creates with `{"long_url": "...", "expires_at": "2026-12-31T23:59:59Z"}` → stored. On redirect with `expires_at < now()` → `410 Gone`, Redis tombstone. Stats show `expires_at` value.

## 3. Stack & deployment
- Runtime: Python 3.12, FastAPI, uvicorn
- Datastore: PostgreSQL 16 (primary store, counter sequence)
- Cache: Redis 7 (redirect cache, rate-limit buckets)
- Tests: pytest + httpx (unit/functional), requests (black-box acceptance)
- Infra: Docker Compose (app + db + redis), multi-stage Dockerfile on `python:3.12-slim`
- Deploy: Local/Docker
- Design → [System Design: Bitly](https://app.notion.com/p/iliazlobin/38ed865005a8818dae1ccbadb0174aa8)

## 4. Data model

```
URL
  id: bigint (PK, auto-increment)
  short_code: varchar(20) (UNIQUE)  ← base62-encoded, 7 chars or custom alias
  long_url: text (NOT NULL)         ← canonicalized
  clicks: int (DEFAULT 0)           ← incremented on each redirect
  created_at: timestamptz (DEFAULT now())
  expires_at: timestamptz (NULL)    ← NULL = never expires
```

Alembic manages the schema. The `id` column is a PostgreSQL `BIGSERIAL` used as the counter for base62 encoding in FR1.

## 5. API

- `POST /api/urls` — create a short URL. Body: `{long_url, custom_alias?, expires_at?}`. Returns `201` with URL object.
- `GET /{short_code}` — redirect to the original URL. Returns `301` + `Location` header.
- `GET /api/urls/{short_code}/stats` — return click count and metadata. Returns `200`.
- `GET /healthz` — health check. Returns `200 {"status": "healthy"}`.

## 6. Test scenarios
- **Idempotency:** Creating the same long URL twice produces two different short codes (no dedup in MVP).
- **Collision:** Creating with an already-taken custom alias → 409.
- **Expiration:** Creating with a past `expires_at` → redirect returns 410, stats show link as expired.
- **Redirect counting:** Each GET increments the click counter exactly once.
- **Cache correctness:** Redis-warmed redirect returns correct Location without hitting PostgreSQL.
- **Validation:** Missing `long_url` → 422; non-base62 alias chars → 422; alias > 20 chars → 422.
- **Rate limiting:** Exceeding rate limit → 429 with Retry-After header.
- **Non-existent:** GET a non-existent short code → 404; stats for non-existent → 404.

## 7. Module layout

```
sd-bitly-backend-mvp/
├── src/
│   └── bitly/
│       ├── __init__.py
│       ├── main.py              # FastAPI app factory + lifespan
│       ├── config.py            # pydantic-settings
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── urls.py          # POST /api/urls, GET /api/urls/{code}/stats
│       │   └── redirect.py      # GET /{short_code}
│       ├── services/
│       │   ├── __init__.py
│       │   ├── url_service.py   # create, lookup, increment, normalize
│       │   └── codec.py         # base62 encode/decode
│       ├── models/
│       │   ├── __init__.py
│       │   └── url.py           # SQLAlchemy URL model
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── url.py           # Pydantic request/response schemas
│       └── db.py                # engine, session, Base
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_codec.py
│   │   └── test_url_service.py
│   └── functional/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_create_url.py
│       ├── test_redirect.py
│       ├── test_stats.py
│       ├── test_custom_alias.py
│       └── test_expiration.py
├── verify/
│   ├── __init__.py
│   ├── manifest.env
│   └── acceptance/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_fr1_create.py
│       ├── test_fr2_redirect.py
│       ├── test_fr3_stats.py
│       ├── test_fr4_custom_alias.py
│       └── test_fr5_expiration.py
├── alembic/
│   └── ...
├── alembic.ini
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── SPEC.md
├── README.md
└── DESIGN.md
```

## 8. Run

```bash
# Local dev
pip install -e ".[dev]"
alembic upgrade head
uvicorn src.bitly.main:app --reload --port 8000

# Docker
docker compose up -d
curl http://localhost:8000/healthz
curl -X POST http://localhost:8000/api/urls -H 'Content-Type: application/json' -d '{"long_url":"https://example.com"}'
curl -v http://localhost:8000/abc1234

# Tests
pytest tests/unit/ -v
pytest tests/functional/ -v
pytest verify/acceptance/ -v
```
