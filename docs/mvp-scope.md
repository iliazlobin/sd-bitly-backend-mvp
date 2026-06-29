# Bitly URL Shortener — MVP Scope

## Stack
- **Runtime:** Python 3.12 + FastAPI + uvicorn
- **Datastore:** PostgreSQL 16 (primary store + ID counter)
- **Cache:** Redis 7 (redirect cache, rate limiting)
- **Tests:** pytest + httpx (ASGITransport for unit/functional, requests for black-box acceptance)
- **Infra:** Docker Compose (app + db + redis)

## Scope IN
- FR1: Create a short URL with an auto-generated 7-character code
- FR2: Redirect a short code to the original URL (301)
- FR3: Track and return click count per short URL (simple counter, no full analytics pipeline)
- FR4: Accept a custom alias when creating a short URL (collision = 409)
- FR5: Accept an optional expiration time; expired links return 410 Gone
- Redis caching layer: cache redirects (24h TTL), hot-path reads skip DB
- Rate limiting: token bucket per IP on the create endpoint
- URL canonicalization: normalize scheme, host, strip fragments

## Scope OUT
- FR6: Safety warnings / interstitial pages (deferred)
- Full analytics pipeline: no NSQ/Flink/ClickHouse (FR3 is a simple counter)
- CDN edge caching (deferred)
- Multi-layer LRU cache (just Redis)
- ZooKeeper-backed ID range allocation (PostgreSQL sequence for MVP)
- User accounts / API keys (unauthenticated MVP)
- Google Web Risk / TDS integration
- Bloom filter for custom alias collision check (DB query is fine for MVP scale)
- Multi-region deployment

## Functional Requirements

### FR1 — Create Short URL
**Behaviour:** User submits a long URL, receives a shortened version with a 7-character base62 code.
- `POST /api/urls` with `{"long_url": "https://example.com/very/long/path"}`
- Normalize the URL (lowercase scheme+host, strip default ports and fragment)
- Generate a 7-character base62 code from a monotonically increasing counter
- Store the mapping in PostgreSQL
- Warm Redis cache
- Return `201` with `{"short_code": "abc1234", "short_url": "http://localhost:8000/abc1234", "long_url": "https://example.com/very/long/path", "created_at": "...", "expires_at": null}`

**Acceptance:** `POST /api/urls {"long_url": "https://example.com/path"} → 201 {"short_code": "<7 chars>"}; GET /{short_code} → 301 Location: https://example.com/path`

### FR2 — Redirect Short URL
**Behaviour:** User navigates to a short URL and is redirected to the original destination.
- `GET /{short_code}`
- Check Redis cache first; on hit → 301 immediately
- On miss → query PostgreSQL, populate Redis, return 301
- Increment click counter
- Return `301 Moved Permanently` with `Location: {long_url}` and `Cache-Control: private, max-age=90`

**Acceptance:** `GET /abc1234 → 301 Location: https://example.com/path; GET /nonexistent → 404`

### FR3 — Click Count
**Behaviour:** User can view the total click count for a short URL.
- `GET /api/urls/{short_code}/stats`
- Return click count from the database
- Return `200` with `{"short_code": "abc1234", "clicks": 42, "created_at": "...", "expires_at": null}`

**Acceptance:** Create URL → redirect 3 times → `GET /api/urls/{short_code}/stats → 200 {"clicks": 3}`

### FR4 — Custom Alias
**Behaviour:** User can specify a custom short code when creating a URL.
- `POST /api/urls` with `{"long_url": "...", "custom_alias": "my-brand"}`
- Normalize alias (lowercase, strip non-base62 chars, validate length ≤ 20)
- Check for collision in PostgreSQL
- On collision → `409 Conflict`
- On success → `201 Created`

**Acceptance:** `POST /api/urls {"long_url": "...", "custom_alias": "my-link"} → 201; POST same alias again → 409`

### FR5 — URL Expiration
**Behaviour:** User can set an optional expiration time. Expired links return 410 Gone.
- `POST /api/urls` with `{"long_url": "...", "expires_at": "2026-12-31T23:59:59Z"}`
- Store `expires_at` in the database
- On redirect, check if `expires_at < now()`: return `410 Gone` and delete the Redis cache entry
- On stats, show `expires_at` and whether the link is expired

**Acceptance:** Create URL with `expires_at` in the past → `GET /{short_code} → 410 Gone; GET /api/urls/{short_code}/stats → 200 {"expired": true}`

## Build Plan
The build runs as a kanban dependency chain on the **`projects`** board:
1. **architect** — design.md + verify/acceptance/ suite (one black-box case per FR)
2. **senior-engineer** — scaffold (repo layout, deps, config, compose, schema, health endpoint)
3. **staff-engineer** — implement all FRs until acceptance suite passes + unit tests + functional tests + ruff clean
4. **verifier** — gate: all tests green + ruff clean, PASS or BLOCK
5. **sre** — DEPLOY.md + .env.example + verify/manifest.env + CI/CD workflows (lint/ci/functional)
6. **writer** — README.md + DESIGN.md, remove build harness
