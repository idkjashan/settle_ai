import json
import uuid
from typing import Optional, Dict, Any
from redis.asyncio import Redis, from_url
from app.core.config import settings
from app.core.logging import logger

class RedisManager:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: Optional[Redis] = None

    async def get_client(self) -> Redis:
        import asyncio
        current_loop = asyncio.get_running_loop()
        if self._client is None or getattr(self, "_loop", None) is not current_loop:
            self._loop = current_loop
            self._client = from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
        return self._client

    async def acquire_video_lock(self, video_sha256: str, claim_id: uuid.UUID, ttl_sec: int = 60) -> bool:
        """
        Executes atomic SET NX lock: SET claim:lock:{sha256} {claim_id} NX EX {ttl_sec}.
        Returns True if acquired, False if key already exists.
        """
        client = await self.get_client()
        key = f"claim:lock:{video_sha256}"
        val = str(claim_id)
        # set with nx=True returns True if set, None/False if not set
        acquired = await client.set(key, val, nx=True, ex=ttl_sec)
        return bool(acquired)

    async def release_video_lock(self, video_sha256: str) -> bool:
        """Deletes lock on failure or completion."""
        client = await self.get_client()
        key = f"claim:lock:{video_sha256}"
        deleted = await client.delete(key)
        return bool(deleted)

    async def publish_event(self, claim_id: uuid.UUID, event_name: str, payload: Dict[str, Any]) -> None:
        """Publishes pipeline event for Server-Sent Events (SSE)."""
        client = await self.get_client()
        channel = f"claim:events:{claim_id}"
        message = json.dumps({
            "event": event_name,
            "claim_id": str(claim_id),
            "data": payload,
        })
        await client.publish(channel, message)
        logger.info(f"Published event {event_name} to channel {channel}")

    async def flush_locks(self) -> int:
        """Flushes claim locks for demo reset."""
        client = await self.get_client()
        keys = await client.keys("claim:lock:*")
        if keys:
            return await client.delete(*keys)
        return 0

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

redis_manager = RedisManager()

