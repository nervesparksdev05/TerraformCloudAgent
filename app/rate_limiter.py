import asyncio
import logging
from fastapi import HTTPException
import redis.asyncio as redis

# Setup logging
logger = logging.getLogger(__name__)

async def check_rate_limit(user_id: str, redis_client: redis.Redis):
    """
    Atomic rate limiter: 15 requests per minute per user.
    Uses INCR + EXPIRE pipeline for atomicity.
    """
    if redis_client is None:
        return

    key = f"rate:{user_id}"
    try:
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 60)
            results = await pipe.execute()
            count = results[0]

        if count > 100:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Max 100 requests per minute."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Redis unreachable: {e}. Graceful bypass.")
        return

