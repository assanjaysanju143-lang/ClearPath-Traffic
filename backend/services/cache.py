"""
Simple in-memory TTL cache.
Prevents redundant API calls for the same route within CACHE_TTL_SECONDS.
"""

import time
from typing import Any, Optional
from config import get_settings

settings = get_settings()

_store: dict[str, tuple[Any, float]] = {}


def _make_key(*args) -> str:
    return "|".join(str(a) for a in args)


def get(key: str) -> Optional[Any]:
    entry = _store.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.time() > expires_at:
        del _store[key]
        return None
    return value


def set(key: str, value: Any, ttl: int = None) -> None:
    ttl = ttl or settings.CACHE_TTL_SECONDS
    _store[key] = (value, time.time() + ttl)


def route_key(origin: str, destination: str, mode: str) -> str:
    return _make_key("route", origin.lower(), destination.lower(), mode)


def flow_key(lat: float, lon: float) -> str:
    return _make_key("flow", round(lat, 4), round(lon, 4))
