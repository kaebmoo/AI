import json
from typing import Optional, Any, Union
import redis
from app.config import settings

class CacheService:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or (settings.REDIS_URL if hasattr(settings, "REDIS_URL") else "redis://localhost:6379/0")
        self._redis = None

    @property
    def redis(self):
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url)
        return self._redis

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            val = self.redis.get(key)
            if val:
                return json.loads(val)
        except Exception:
            # Log error but return None to avoid breaking app flow
            pass
        return None

    def set(self, key: str, value: Any, expire: int = 3600):
        """Set value in cache with expiration"""
        try:
            self.redis.setex(key, expire, json.dumps(value))
        except Exception:
            pass

    def delete(self, key: str):
        """Delete key from cache"""
        try:
            self.redis.delete(key)
        except Exception:
            pass

    def clear_pattern(self, pattern: str):
        """Clear keys matching pattern"""
        try:
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
        except Exception:
            pass
