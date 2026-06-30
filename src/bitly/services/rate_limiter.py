"""Fixed-window rate limiter backed by Redis.

Keys on `rate:{ip}:{window_timestamp}`, where window_timestamp is
`floor(now() / window_seconds)`. Uses Redis INCR + EXPIRE in a single
pipeline for atomicity.
"""

import time

import redis.asyncio as aioredis


async def check_rate_limit(
    redis: aioredis.Redis,
    ip: str,
    limit: int,
    window_s: int,
) -> bool:
    """Check whether *ip* is within the rate limit for the current window.

    Returns True if the request is allowed, False if the limit is exceeded.
    """
    now = int(time.time())
    window_ts = now // window_s
    key = f"rate:{ip}:{window_ts}"

    # INCR + EXPIRE in a pipeline so the key always has a TTL.
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window_s)
        count_raw, _ = await pipe.execute()

    count = int(count_raw)
    return count <= limit
