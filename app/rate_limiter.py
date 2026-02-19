# app/rate_limiter.py

import redis.asyncio as redis
from fastapi import HTTPException
from app.core.logger import get_logger

logger = get_logger(__name__)

async def check_rate_limit(user_id: str, redis_client: redis.Redis):
    """
    Atomic rate limiter: 15 requests per minute per user.
    Uses INCR + EXPIRE pipeline for atomicity.
    """
    if redis_client is None:
        # Silently allow if Redis is not configured (graceful degradation)
        return

    key = f"rate_limit:{user_id}"
    try:
        # Atomic pipeline: increment and set expiry in one round trip
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 60)
            results = await pipe.execute()
            count = results[0]

        if count > 15:
            logger.warning(f"Rate limit exceeded for user {user_id}: {count} requests/min")
            raise HTTPException(
                status_code=429, 
                detail="Rate limit exceeded. Maximum 15 requests per minute."
            )
    except HTTPException:
        # Re-raise 429 errors
        raise
    except Exception as e:
        # Catch connection errors and allow request through silently
        logger.error(f"Redis rate limiter error: {e}. Allowing request through.")
        return
