# Bitly URL Shortener MVP — Design

> **Stack:** Python 3.12 · FastAPI · PostgreSQL 16 · Redis 7 · SQLAlchemy (async) · Alembic · pytest · httpx · Docker Compose
> **Architecture:** Monolithic REST API — PostgreSQL for source-of-truth, Redis for redirect cache and rate limiting.

## 1. Scope

### In scope

- **FR1 — Create Short URL.** Auto-generate a 7-character base62 code from a PostgreSQL `BIGSERIAL` counter. Canonicalize the input URL. Store the mapping, warm the Redis cache.
- **FR2 — Redirect Short URL.** Resolve a short code to a `301` redirect. Check Redis first; on miss, query PostgreSQL and populate the cache. Increment the click counter.
- **FR3 — Click Count.** Return click count and metadata per short URL.
- **FR4 — Custom Alias.** Accept a user-specified short code (1–20 base62 chars). Detect collisions via a `UNIQUE` constraint.
- **FR5 — URL Expiration.** Store an optional `expires_at` timestamp. Expired links return `410 Gone`.
- **Rate limiting.** Fixed-window counter per IP on `POST /api/urls` (10 req/s default).
- **URL canonicalization.** Lowercase scheme+host, strip default ports (`:80`, `:443`), strip fragment.
- **Redis caching.** Read-through cache on the redirect path with a 24-hour TTL.

### Out of scope

- Safety warnings / interstitial pages
- Full analytics pipeline (NSQ, Flink, ClickHouse)
- CDN edge caching
- Multi-region deployment
- ZooKeeper ID range allocation
- User accounts / API keys
- Bloom filter for alias collision pre-check
- In-process LRU cache

## 2. Architecture

### MVP architecture

```
Client (REST) ──→ FastAPI ──→ Redis (redirect cache, rate-limit buckets)
                          └─→ PostgreSQL (URLs table, BIGSERIAL counter)
```

A single-service REST API. No message queue, no analytics pipeline. The redirect path checks Redis first; on miss it falls through to PostgreSQL, populates the cache, and returns the `301`. The create path generates a 7-character base62 code from a PostgreSQL `BIGSERIAL` counter, canonicalizes the URL, stores the mapping, and warms the cache.

**Create flow (FR1):**

1. `POST /api/urls` → validate `long_url` present and parseable → `422` if invalid
2. Canonicalize: lowercase scheme+host, strip default ports, strip fragment
3. If `custom_alias` provided: validate ≤20 base62 chars → `422` if invalid; `INSERT` with the alias → `UNIQUE` constraint catches collisions → `409`
4. If no alias: `INSERT` → `base62_encode(id)` → 7-char `short_code` → `UPDATE`
5. Warm Redis: `SET url:{short_code} {long_url} EX 86400`
6. Return `201` with full URL object

**Redirect flow (FR2):**

1. `GET /{short_code}` → validate format (1–20 alphanumeric) → `404` if invalid
2. `GET url:{short_code}` from Redis → on hit: check expiry via DB, increment click counter, return `301`
3. On Redis miss: `SELECT long_url, expires_at FROM urls WHERE short_code = $1` → `404` if no row
4. Check `expires_at < now()` → `410 Gone`
5. Populate Redis: `SET url:{short_code} {long_url} EX 86400`
6. Increment `clicks` column atomically
7. Return `301 Moved Permanently` + `Location: {long_url}` + `Cache-Control: private, max-age=90`

**Stats flow (FR3):**

1. `GET /api/urls/{short_code}/stats` → `SELECT` from `urls` table
2. No row → `404`
3. Return `200` with short_code, long_url, clicks, created_at, expires_at

### Target production architecture

The MVP is a single-writer, single-cache, single-database cut. The full production architecture (not implemented here) layers on:

- **Multi-layer cache pyramid:** CDN edge (`s-maxage=90`) → in-process LRU (1K entries, ~0.1ms) → Redis cluster (hash-sharded) → primary store — achieving >95% cache hit rate at the origin.
- **Distributed ID generation:** ZooKeeper range allocation — each create-service instance claims 1,000-ID blocks atomically and burns through them in-process, collapsing coordination traffic by 1,000× versus per-request counter increments.
- **Async analytics pipeline:** Redirect publishes an event to NSQ/Kafka (fire-and-forget) → Flink enriches and aggregates into 5-second microbatches → ClickHouse stores pre-aggregated rollups (~10 MB/day versus 72 GB/day of raw events). Raw events are cold-archived to object storage.
- **Safety scanning:** Async crawler fetches destination pages → Threat Detection Service + Google Web Risk classify → safety status cached in Redis with 5-min TTL, checked on every redirect.

## 3. Data Model

### PostgreSQL — source of truth

```sql
CREATE TABLE urls (
    id          BIGSERIAL PRIMARY KEY,
    short_code  VARCHAR(20) UNIQUE NOT NULL,
    long_url    TEXT NOT NULL,
    clicks      INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ
);
CREATE INDEX idx_urls_short_code ON urls (short_code);
```

| Column | Type | Purpose |
|---|---|---|
| `id` | `BIGSERIAL` | Monotonically increasing counter; base62-encoded to produce `short_code`. At ~70 creates/sec, `BIGINT` (9.2 × 10^18) lasts 4 billion years. |
| `short_code` | `VARCHAR(20) UNIQUE` | 7-character auto-generated code or custom alias (≤20 chars). `UNIQUE` constraint catches alias collisions. |
| `long_url` | `TEXT` | Canonicalized destination URL. No length constraint at the DB level; FastAPI validates max 2048 at the boundary. |
| `clicks` | `INTEGER DEFAULT 0` | Atomically incremented on each redirect. Simple, instantly queryable. |
| `created_at` | `TIMESTAMPTZ` | Creation timestamp with timezone. |
| `expires_at` | `TIMESTAMPTZ NULL` | `NULL` = never expires. The redirect path checks `expires_at < now()` on every cache miss. |

No user table — the MVP is unauthenticated.

### Redis — ephemeral cache

```
url:{short_code}        → long_url (string, TTL 86400s)    — redirect cache
rate:{ip}:{window_ts}   → count (string, TTL window_s)     — rate-limit counter
```

- **Redirect cache:** Read-through pattern. 24h TTL keeps hot links out of PostgreSQL. URLs are immutable after creation, so cache staleness is not a risk.
- **Rate limiter:** Fixed-window counter per IP. Keyed on `{ip}:{floor(now() / window_seconds)}`. Window TTL auto-clears expired buckets.

## 4. Key Decisions

| # | Decision | Chose | Rationale |
|---|----------|-------|-----------|
| 1 | ID generation | PostgreSQL `BIGSERIAL` + base62 | Guarantees monotonic, collision-free 64-bit integers. Encodes to exactly 7 base62 chars for billions of IDs — unlike UUID (22 chars in base62) or hash-based approaches that need collision handling. The single-writer bottleneck is acceptable at MVP scale. |
| 2 | Two-step auto code | `INSERT` → `encode(id)` → `UPDATE` | The `id` value isn't known until after `INSERT`. Pre-computing requires a separate sequence or application-side counter — more coordination. The two-step approach is trivially atomic in a transaction. |
| 3 | Redirect cache TTL | 24 hours (86400s) | Keeps hot links cached through a full day cycle. URLs are immutable, so staleness isn't a concern. Shorter TTLs increase DB load; infinite TTL would require invalidation logic. |
| 4 | Rate limit window | Fixed window (1s buckets) | Simplest Redis implementation (`INCR` + `EXPIRE` in one pipeline). Allows up to 2× burst at window boundaries, but the simplicity gain outweighs the imprecision at MVP scale. |
| 5 | URL canonicalization | Lowercase scheme+host, strip default ports and fragment | Covers 95% of duplicate URLs with minimal code. Full WHATWG spec normalization (sorting query params, encoding normalization) is overkill for MVP. |
| 6 | Click counter increment | Synchronous `UPDATE` | Simple, instantly queryable. At MVP scale the extra ~1ms DB write is negligible. Production would fire-and-forget to a queue. |
| 7 | Redirect status | `301` + `Cache-Control: private, max-age=90` | `301` tells browsers and proxies the redirect is stable — subsequent clicks within 90s are served from browser cache, reducing origin load. `private` prevents intermediate proxy caching, important if links become personalized later. |
| 8 | Single-table design | URLs table only | MVP has no auth, no analytics dimensions. A separate click_events table would explode row count with no analytics value. Add when the analytics pipeline is in scope. |

### Base62 encoding

Characters: `0-9` (10) + `a-z` (26) + `A-Z` (52) = 62 symbols.

```
encode(n):
  if n == 0: return "0000000"
  collect digits by repeated n % 62, n //= 62
  left-pad result to 7 chars with "0"

decode(s):
  strip leading "0", then n = n * 62 + char_index for each character
```

Key numbers: `62^6 ≈ 56.8B` — IDs 0 through 56.8B encode to 6 or fewer characters; left-padding keeps the code at exactly 7 characters up to `62^7 - 1 ≈ 3.5T`.

## 5. API Contracts

Base URL: `http://localhost:8010` (configurable via `APP_PORT`). All responses are JSON. Timestamps are ISO 8601. Short codes are 1–20 alphanumeric characters (`[0-9a-zA-Z]`).

### `POST /api/urls` — Create Short URL

```
Request:  {"long_url": "https://example.com/very/long/path?q=1",
           "custom_alias": "my-link",             // optional, ≤20 base62 chars
           "expires_at": "2026-12-31T23:59:59Z"}  // optional, ISO 8601

Response: 201 {"short_code": "0000001",
               "short_url": "http://localhost:8010/0000001",
               "long_url": "https://example.com/very/long/path?q=1",
               "clicks": 0,
               "created_at": "2026-06-29T12:00:00Z",
               "expires_at": null}

Errors:
  422  {"detail": "long_url is required"}
  422  {"detail": "Invalid URL format"}
  422  {"detail": "custom_alias must be 1-20 base62 chars"}
  409  {"detail": "Alias 'my-link' is already taken"}
  429  {"detail": "Rate limit exceeded"}  (Retry-After: 1)
```

- **Canonicalization:** Lowercase scheme+host, strip `:80`/`:443` default ports, strip `#fragment`. Query string is preserved.
- **Duplicate long URLs are allowed.** Two POSTs with the same URL produce two different short codes (no dedup).
- **Rate limit:** 10 requests/sec per IP (configurable via `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW_S`).
- **Auto-generated code:** Always exactly 7 characters, left-padded with `0`.

### `GET /{short_code}` — Redirect

```
Response: 301 Moved Permanently
  Location: https://example.com/very/long/path?q=1
  Cache-Control: private, max-age=90

Errors:
  404  {"detail": "Short code not found"}
  410  {"detail": "This link has expired"}
```

- The click counter is incremented atomically on every origin redirect (not on browser-cached hits).
- Expired links delete their Redis cache entry so subsequent requests don't get stale cache hits.
- Invalid-format short codes (non-alphanumeric chars) return `404` without hitting the database.

### `GET /api/urls/{short_code}/stats` — Stats

```
Response: 200 {"short_code": "0000001",
               "long_url": "https://example.com/very/long/path?q=1",
               "clicks": 42,
               "created_at": "2026-06-29T12:00:00Z",
               "expires_at": null}

Errors:
  404  {"detail": "Short code not found"}
```

- `expires_at` is `null` for permanent links, an ISO 8601 timestamp for expiring links.
- Stats remain accessible even after a link expires.

### `GET /healthz` — Health Check

```
Response: 200 {"status": "healthy"}
```

Liveness probe for Docker healthcheck and load balancers. Confirms the process is alive; does not verify DB/Redis connectivity.

## 6. Module Layout

```
sd-bitly-backend-mvp/
├── src/bitly/
│   ├── main.py              # create_app() factory + lifespan + /healthz
│   ├── config.py            # pydantic-settings (DATABASE_URL, REDIS_URL, rate limits)
│   ├── database.py          # Async SQLAlchemy engine, session factory, get_session dependency
│   ├── redis.py             # Async Redis client factory, get_redis dependency
│   ├── models/
│   │   └── url.py           # SQLAlchemy URL model
│   ├── schemas/
│   │   └── url.py           # Pydantic: CreateURLRequest, URLResponse, StatsResponse
│   ├── routers/
│   │   ├── urls.py           # POST /api/urls, GET /api/urls/{code}/stats
│   │   └── redirect.py       # GET /{short_code}
│   └── services/
│       ├── url_service.py    # create_url, lookup_url, increment_clicks, get_stats, canonicalize_url
│       ├── codec.py          # base62_encode, base62_decode
│       └── rate_limiter.py   # check_rate_limit (Redis INCR + EXPIRE)
├── tests/
│   ├── unit/
│   │   ├── test_codec.py            # Base62 round-trip, edge cases, padding
│   │   └── test_canonicalize.py     # URL normalization: lowercase, ports, fragment
│   └── functional/
│       ├── test_create_url.py       # FR1: create, canonicalize, validation, idempotency
│       ├── test_redirect.py         # FR2: 301 redirect, 404, click counter, query params
│       ├── test_stats.py            # FR3: metadata, click count, 404
│       ├── test_custom_alias.py     # FR4: alias create, 409 collision, 422 validation
│       └── test_expiration.py       # FR5: create/redirect expired, stats, 410
├── verify/acceptance/
│   ├── test_fr1_create.py           # Black-box FR1: create, canonicalize, idempotency, rate limit
│   ├── test_fr2_redirect.py         # Black-box FR2: 301, 404, click counter
│   ├── test_fr3_stats.py            # Black-box FR3: stats metadata, 0 clicks, 404
│   ├── test_fr4_custom_alias.py     # Black-box FR4: alias create, 409, 422
│   └── test_fr5_expiration.py       # Black-box FR5: expire, 410, stats after expiry
├── alembic/
│   └── versions/
│       └── 001_create_urls_table.py
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── SPEC.md
└── DEPLOY.md
```

Layering discipline: routers are thin — they parse requests, call services, and serialize responses. Services contain all business logic and are the only layer that touches the database or Redis.

## 7. Concurrency & Correctness

- **Alias collision:** PostgreSQL `UNIQUE` constraint on `short_code` is the single source of truth. Two concurrent POSTs with the same alias → one succeeds, one gets `IntegrityError` → `409`.
- **Auto code collision:** Impossible — `BIGSERIAL` is monotonic and `short_code` is `base62(id)`.
- **Click counter:** `UPDATE urls SET clicks = clicks + 1` is atomic in PostgreSQL (row-level lock). No lost updates.
- **Expiry + cache consistency:** On cache miss, the redirect path checks `expires_at < now()` after the DB read but before populating Redis. If a link expires between these steps, the newly-cached entry has a benign 24h stale window — the next redirect catches it on the DB check path.
- **Rate limiter edge cases:** Fixed-window counters allow up to 2× burst at window boundaries. All users behind a shared IP share the same bucket (acceptable for an unauthenticated MVP).

## 8. Functional Requirements → Test Map

| SPEC Section 6 Scenario | Functional Test | Acceptance Test |
|---|---|---|
| **Idempotency:** Same long URL twice → two different short codes | `tests/functional/test_create_url.py::test_same_url_different_codes` | `verify/acceptance/test_fr1_create.py::test_same_long_url_different_codes` |
| **Collision:** Duplicate custom alias → 409 | `tests/functional/test_custom_alias.py::test_duplicate_alias_409` | `verify/acceptance/test_fr4_custom_alias.py::test_duplicate_alias_409` |
| **Expiration:** Past expires_at → 410 Gone | `tests/functional/test_expiration.py::test_expired_link_returns_410` | `verify/acceptance/test_fr5_expiration.py::test_expired_link_returns_410` |
| **Redirect counting:** Each GET increments click counter | `tests/functional/test_redirect.py::test_increments_click_count` | `verify/acceptance/test_fr2_redirect.py::test_redirect_increments_click_count` |
| **Cache correctness:** Redis-warmed redirect returns correct Location | `tests/functional/test_redirect.py::test_redirect_301_with_location` | `verify/acceptance/test_fr2_redirect.py::test_redirect_returns_301_with_location` |
| **Validation:** Missing long_url → 422; non-base62 alias → 422; alias > 20 chars → 422 | `tests/functional/test_create_url.py::test_missing_long_url_422`, `test_empty_long_url_422`, `test_invalid_url_422`, `test_no_scheme_422`; `tests/functional/test_custom_alias.py::test_invalid_alias_non_base62`, `test_invalid_alias_too_long`, `test_invalid_alias_empty` | `verify/acceptance/test_fr1_create.py::test_create_missing_long_url`, `test_create_empty_long_url`, `test_create_invalid_url`, `test_create_invalid_url_no_scheme`; `verify/acceptance/test_fr4_custom_alias.py::test_invalid_alias_non_base62`, `test_invalid_alias_too_long`, `test_invalid_alias_empty` |
| **Rate limiting:** Exceeding limit → 429 + Retry-After | Covered by acceptance test | `verify/acceptance/test_fr1_create.py::test_rate_limit_exceeded` |
| **Non-existent:** GET nonexistent → 404; stats for nonexistent → 404 | `tests/functional/test_redirect.py::test_nonexistent_404`, `tests/functional/test_stats.py::test_nonexistent_404` | `verify/acceptance/test_fr2_redirect.py::test_redirect_nonexistent_code_404`, `verify/acceptance/test_fr3_stats.py::test_stats_nonexistent_code_404` |

### CI Verification

Three GitHub Actions workflows run on every push, pull request, and daily schedule:

| Workflow | What it runs | Badge |
|---|---|---|
| **Lint** | `ruff check` + `ruff format --check` | [![Lint](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/lint.yml/badge.svg)](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/lint.yml) |
| **CI** | Unit tests (`tests/unit/`) + end-to-end acceptance (`verify/acceptance/` against live Compose stack) | [![CI](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/ci.yml/badge.svg)](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/ci.yml) |
| **Functional** | Functional tests (`tests/functional/`) against PostgreSQL 16 service | [![Functional](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/functional.yml/badge.svg)](https://github.com/iliazlobin/sd-bitly-backend-mvp/actions/workflows/functional.yml) |

- **Unit tests** run without any services — they test pure functions (base62 codec, URL canonicalization).
- **Functional tests** use in-memory SQLite and fakeredis — fast, isolated, no external dependencies.
- **CI (e2e)** spins up the full Docker Compose stack and runs the black-box acceptance suite against the live application.
