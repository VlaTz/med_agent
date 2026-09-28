"""Disk cache for outbound HTTP calls to public research APIs.

Bonus requirement: avoids re-hitting PubMed/ClinicalTrials.gov on repeated
runs of the same query during development/demoing.
"""
from __future__ import annotations

import functools
import hashlib
import json
from pathlib import Path

import diskcache

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / ".api_cache"
_cache = diskcache.Cache(str(_CACHE_DIR))

DEFAULT_TTL_SECONDS = 6 * 60 * 60  # 6h: fresh enough during a work session, avoids hammering the APIs


def _key(prefix: str, *args, **kwargs) -> str:
    raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    return f"{prefix}:{hashlib.sha256(raw.encode()).hexdigest()}"


def cached(prefix: str, ttl: int = DEFAULT_TTL_SECONDS):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = _key(prefix, *args, **kwargs)
            hit = _cache.get(key)
            if hit is not None:
                return hit
            result = func(*args, **kwargs)
            _cache.set(key, result, expire=ttl)
            return result

        return wrapper

    return decorator
