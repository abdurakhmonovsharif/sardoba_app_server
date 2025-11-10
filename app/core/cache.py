import asyncio
import pickle
import logging
import threading
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional, Protocol

from redis import Redis
from redis.exceptions import RedisError

from .config import get_settings

logger = logging.getLogger(__name__)


class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None:
        ...

    def set(self, key: str, value: Any, ttl: int) -> None:
        ...

    def delete(self, key: str) -> None:
        ...

    def clear_namespace(self, namespace: str) -> None:
        ...


class RedisCacheBackend:
    def __init__(self, client: Redis):
        self.client = client

    def get(self, key: str) -> Any | None:
        return self.client.get(key)

    def set(self, key: str, value: Any, ttl: int) -> None:
        self.client.setex(key, ttl, value)

    def delete(self, key: str) -> None:
        self.client.delete(key)

    def clear_namespace(self, namespace: str) -> None:
        pattern = f"{namespace}:*"
        keys = list(self.client.scan_iter(pattern))
        if keys:
            self.client.delete(*keys)


@dataclass
class _InMemoryEntry:
    value: Any
    expires_at: float


class InMemoryCacheBackend:
    def __init__(self) -> None:
        self._data: dict[str, _InMemoryEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            if entry.expires_at < time.time():
                self._data.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            self._data[key] = _InMemoryEntry(value=value, expires_at=time.time() + ttl)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear_namespace(self, namespace: str) -> None:
        prefix = f"{namespace}:"
        with self._lock:
            to_delete = [key for key in self._data if key.startswith(prefix)]
            for key in to_delete:
                self._data.pop(key, None)


class CacheManager:
    def __init__(self) -> None:
        self.backend: CacheBackend | None = None

    def init_backend(self) -> None:
        if self.backend is not None:
            return

        settings = get_settings()
        if settings.REDIS_URL:
            try:
                client = Redis.from_url(settings.REDIS_URL)
                client.ping()
                self.backend = RedisCacheBackend(client)
                logger.info("Using Redis cache backend.")
                return
            except (RedisError, OSError) as exc:  # pragma: no cover - best effort
                logger.warning("Redis unavailable (%s). Falling back to in-memory cache.", exc)
        self.backend = InMemoryCacheBackend()
        logger.info("Using in-memory cache backend.")

    def get_backend(self) -> CacheBackend:
        if self.backend is None:
            self.init_backend()
        assert self.backend is not None
        return self.backend

    def invalidate_namespace(self, namespace: str) -> None:
        backend = self.get_backend()
        backend.clear_namespace(namespace)


cache_manager = CacheManager()


CallableType = Callable[..., Any]


def _build_cache_key(namespace: str, identifier: str) -> str:
    return f"{namespace}:{identifier}"


def cache(
    ttl: int,
    namespace: str,
    key_builder: Optional[Callable[..., str]] = None,
):
    """
    Decorator to cache function responses.

    Parameters:
        ttl: cache TTL in seconds
        namespace: logical namespace used for invalidation
        key_builder: function that receives the same args/kwargs and returns a cache key suffix
    """

    def decorator(func: CallableType) -> CallableType:
        is_coroutine = asyncio.iscoroutinefunction(func)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            identifier = key_builder(*args, **kwargs) if key_builder else repr((args, kwargs))
            key = _build_cache_key(namespace, identifier)
            backend = cache_manager.get_backend()
            cached_value = backend.get(key)
            if cached_value is not None:
                return pickle.loads(cached_value)

            result = await func(*args, **kwargs)
            backend.set(key, pickle.dumps(result), ttl)
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            identifier = key_builder(*args, **kwargs) if key_builder else repr((args, kwargs))
            key = _build_cache_key(namespace, identifier)
            backend = cache_manager.get_backend()
            cached_value = backend.get(key)
            if cached_value is not None:
                return pickle.loads(cached_value)

            result = func(*args, **kwargs)
            backend.set(key, pickle.dumps(result), ttl)
            return result

        wrapper: CallableType = async_wrapper if is_coroutine else sync_wrapper
        return wrapper

    return decorator


def invalidate_cache(namespace: str) -> None:
    cache_manager.invalidate_namespace(namespace)
