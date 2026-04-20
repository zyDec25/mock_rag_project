import os

import redis.asyncio as redis


QUICK_PARSE_TTL_SECONDS = 7200
QUICK_PARSE_KEY_PREFIX = "quick_parse"

REDIS_URL = os.getenv("REDIS_URL", "redis://mock_redis:6379/0")

redis_client = redis.from_url(
    REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)


def quick_parse_key(session_id: str) -> str:
    return f"{QUICK_PARSE_KEY_PREFIX}:{session_id}"


async def set_quick_parse_content(
    session_id: str,
    content: str,
    ttl_seconds: int = QUICK_PARSE_TTL_SECONDS,
) -> None:
    await redis_client.setex(quick_parse_key(session_id), ttl_seconds, content)


async def get_quick_parse_content(session_id: str) -> str | None:
    return await redis_client.get(quick_parse_key(session_id))


async def get_quick_parse_ttl(session_id: str) -> int:
    return await redis_client.ttl(quick_parse_key(session_id))


async def delete_quick_parse_content(session_id: str) -> None:
    await redis_client.delete(quick_parse_key(session_id))


async def close_redis() -> None:
    await redis_client.aclose()
