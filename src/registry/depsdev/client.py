"""Deps.dev v3 client: HTTPS JSON fetch with caching, backoff via existing middleware."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from urllib.parse import quote as urlquote
from typing import Any, Dict, Optional, Tuple

from constants import Constants
from common.logging_utils import extra_context, is_debug_enabled, safe_url, Timer
from common.http_metrics import increment
from common.http_client import robust_get

try:
    from src.versioning.cache import TTLCache  # type: ignore
except Exception:  # pylint: disable=broad-exception-caught
    from versioning.cache import TTLCache  # type: ignore

logger = logging.getLogger(__name__)
SERVICE = "api.deps.dev"
HEADERS_JSON = {"Accept": "application/json"}


def _parse_cache_max_age(headers: Dict[str, str]) -> Optional[int]:
    """Extract max-age from Cache-Control header if present."""
    if not headers:
        return None
    cc = None
    for k, v in headers.items():
        if isinstance(k, str) and k.lower() == "cache-control":
            cc = v
            break
    if not cc or not isinstance(cc, str):
        return None
    m = re.search(r"max-age\s*=\s*(\d+)", cc)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:  # pylint: disable=broad-exception-caught
        return None


class DepsDevClient:
    """Lightweight deps.dev client using robust_get and in-run/file cache."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        cache_ttl_sec: Optional[int] = None,
        max_response_bytes: Optional[int] = None,
        file_cache_path: Optional[str] = None,
    ) -> None:
        b = base_url or Constants.DEPSDEV_BASE_URL
        if isinstance(b, str) and not b.startswith("https://"):
            # Enforce HTTPS
            b = "https://" + b.lstrip("/").lstrip(":").lstrip("/")
        self.base_url = b.rstrip("/")
        self.cache_ttl_sec = int(cache_ttl_sec or Constants.DEPSDEV_CACHE_TTL_SEC)
        self.max_response_bytes = int(max_response_bytes or Constants.DEPSDEV_MAX_RESPONSE_BYTES)
        self._cache = TTLCache()
        self._file_cache: Dict[str, Dict[str, Any]] = {}
        self._file_cache_path = file_cache_path or os.path.join(".uv-cache", "depsdev_cache.json")
        try:
            os.makedirs(os.path.dirname(self._file_cache_path), exist_ok=True)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        self._load_file_cache()

    @staticmethod
    def _eco_value(ecosystem: str) -> str:
        e = (ecosystem or "").lower()
        if e in ("npm",):
            return "npm"
        if e in ("pypi", "py", "python"):
            return "pypi"
        if e in ("maven", "java"):
            return "maven"
        return e or "npm"

    @staticmethod
    def normalize_name(ecosystem: str, raw_name: str) -> str:
        """Normalize package name per ecosystem (PEP 503 for PyPI; prefix+encode for Maven)."""
        if raw_name is None:
            return ""
        name = str(raw_name).strip()
        eco = DepsDevClient._eco_value(ecosystem)
        if eco == "pypi":
            # Strip extras and version specifiers from name (PEP 508/440), then apply PEP 503 normalization.
            # Drop environment markers
            s = name.split(";", 1)[0].strip()
            # Remove extras portion
            base = s.split("[", 1)[0].strip()
            # Identify first comparator after base
            tokens = ["===", ">=", "<=", "==", "~=", "!=", ">", "<", " "]
            first_idx = None
            for tok in tokens:
                idx = s.find(tok, len(base))
                if idx != -1:
                    first_idx = idx if first_idx is None else min(first_idx, idx)
            if first_idx is not None and first_idx >= len(base):
                base = s[:first_idx].strip()
            lowered = base.lower()
            pep503 = re.sub(r"[-_.]+", "-", lowered)
            return urlquote(pep503, safe="")
        if eco == "maven":
            # deps.dev expects a prefixed coordinate in the name segment; then encode
            if not name:
                return ""
            prefixed = name if name.startswith("maven:") else f"maven:{name}"
            return urlquote(prefixed, safe="")
        # npm and others: encode as single path segment (scoped names become %40scope%2Fname)
        return urlquote(name, safe="")

    @staticmethod
    def normalize_version(_ecosystem: str, raw_version: Optional[str]) -> Optional[str]:
        """Conservative pass-through for version; guard trivial whitespace."""
        if raw_version is None:
            return None
        v = str(raw_version).strip()
        return v or None

    def _load_file_cache(self) -> None:
        try:
            if os.path.isfile(self._file_cache_path):
                with open(self._file_cache_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh) or {}
                    if isinstance(data, dict):
                        self._file_cache = data
        except Exception:  # pylint: disable=broad-exception-caught
            self._file_cache = {}

    def _save_file_cache(self) -> None:
        try:
            with open(self._file_cache_path, "w", encoding="utf-8") as fh:
                json.dump(self._file_cache, fh)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def _file_get(self, key: str) -> Optional[Dict[str, Any]]:
        try:
            entry = self._file_cache.get(key)
            if not entry or not isinstance(entry, dict):
                return None
            exp = entry.get("expires_at")
            if isinstance(exp, (int, float)) and time.time() < float(exp):
                return entry.get("value")
            return None
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    def _file_put(self, key: str, value: Dict[str, Any], ttl: int) -> None:
        try:
            self._file_cache[key] = {"value": value, "expires_at": time.time() + ttl}
            self._save_file_cache()
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def _cache_key(self, url: str) -> str:
        return url

    def _cache_hit(self, where: str, url: str) -> None:
        if is_debug_enabled(logger):
            logger.debug(
                "deps.dev cache hit",
                extra=extra_context(event="depsdev_cache_hit", component="depsdev_client", target=safe_url(url), cache=where),
            )
        increment(SERVICE, "attempts_total")

    def _cache_miss(self, where: str, url: str) -> None:
        if is_debug_enabled(logger):
            logger.debug(
                "deps.dev cache miss",
                extra=extra_context(event="depsdev_cache_miss", component="depsdev_client", target=safe_url(url), cache=where),
            )

    def _request_json(self, url: str) -> Tuple[int, Dict[str, str], Optional[Any]]:
        key = self._cache_key(url)
        # In-run cache
        cached = self._cache.get(key)
        if cached:
            self._cache_hit("memory", url)
            return int(cached.get("status", 200)), dict(cached.get("headers", {})), cached.get("data")

        # File cache
        fval = self._file_get(key)
        if fval:
            self._cache_hit("file", url)
            # Promote into memory cache with a short TTL to avoid repeated file reads
            try:
                ttl = int(Constants.DEPSDEV_CACHE_TTL_SEC)
            except Exception:  # pylint: disable=broad-exception-caught
                ttl = 60
            self._cache.set(key, fval, ttl)
            return int(fval.get("status", 200)), dict(fval.get("headers", {})), fval.get("data")

        self._cache_miss("both", url)
        if is_debug_enabled(logger):
            logger.debug("deps.dev request", extra=extra_context(event="depsdev_request", component="depsdev_client", target=safe_url(url)))
        with Timer() as t:
            status, headers, text = robust_get(url, headers=HEADERS_JSON, context="depsdev")
        if status != 200 or not isinstance(text, str):
            logger.info(
                "deps.dev response non-200",
                extra=extra_context(event="depsdev_response", component="depsdev_client", outcome="non_200", status_code=status, duration_ms=t.duration_ms() if 't' in locals() else None, target=safe_url(url)),
            )
            return status, headers, None
        # Response size guard
        try:
            sz = len(text.encode("utf-8"))
        except Exception:  # pylint: disable=broad-exception-caught
            sz = len(text)
        if sz > self.max_response_bytes:
            logger.warning(
                "deps.dev response too large",
                extra=extra_context(event="depsdev_response", component="depsdev_client", outcome="too_large", size_bytes=sz, limit=self.max_response_bytes, target=safe_url(url)),
            )
            return 0, {}, None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return status, headers, None
        # Determine TTL from headers
        ttl = _parse_cache_max_age(headers) or self.cache_ttl_sec
        cache_record = {"status": status, "headers": headers, "data": data}
        try:
            self._cache.set(key, cache_record, int(ttl))
            self._file_put(key, cache_record, int(ttl))
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        logger.info(
            "deps.dev response ok",
            extra=extra_context(event="depsdev_response", component="depsdev_client", outcome="success", status_code=status, duration_ms=t.duration_ms(), target=safe_url(url)),
        )
        increment(SERVICE, "attempts_total")
        return status, headers, data

    def get_project(self, ecosystem: str, name: str) -> Tuple[int, Dict[str, str], Optional[Dict[str, Any]]]:
        eco = self._eco_value(ecosystem)
        n = self.normalize_name(eco, name)
        url1 = f"{self.base_url}/projects/{eco}/{n}"
        status, headers, data = self._request_json(url1)
        # Maven fallback: try unprefixed coordinate if prefixed attempt fails
        if (status != 200 or not isinstance(data, dict)) and eco == "maven" and isinstance(n, str):
            alt_n_enc = None
            if n.startswith("maven%3A"):
                alt_n_enc = n[len("maven%3A"):]
            elif n.startswith("maven:"):
                # n isn't encoded yet; encode after stripping prefix
                alt_n_enc = urlquote(n[len("maven:"):], safe="")
            if alt_n_enc:
                url2 = f"{self.base_url}/projects/{eco}/{alt_n_enc}"
                if is_debug_enabled(logger):
                    logger.debug(
                        "deps.dev request (fallback)",
                        extra=extra_context(event="depsdev_request_fallback", component="depsdev_client", target=safe_url(url2)),
                    )
                status2, headers2, data2 = self._request_json(url2)
                if status2 == 200 and isinstance(data2, dict):
                    return status2, headers2, data2
        return status, headers, data

    def get_version(self, ecosystem: str, name: str, version: Optional[str]) -> Tuple[int, Dict[str, str], Optional[Dict[str, Any]]]:
        eco = self._eco_value(ecosystem)
        n = self.normalize_name(eco, name)
        v = self.normalize_version(eco, version)
        if not v:
            return 0, {}, None
        url1 = f"{self.base_url}/versions/{eco}/{n}@{v}"
        status, headers, data = self._request_json(url1)
        # Maven fallback: try unprefixed coordinate if prefixed attempt fails
        if (status != 200 or not isinstance(data, dict)) and eco == "maven" and isinstance(n, str):
            alt_n_enc = None
            if n.startswith("maven%3A"):
                alt_n_enc = n[len("maven%3A"):]
            elif n.startswith("maven:"):
                alt_n_enc = urlquote(n[len("maven:"):], safe="")
            if alt_n_enc:
                url2 = f"{self.base_url}/versions/{eco}/{alt_n_enc}@{v}"
                if is_debug_enabled(logger):
                    logger.debug(
                        "deps.dev request (fallback)",
                        extra=extra_context(event="depsdev_request_fallback", component="depsdev_client", target=safe_url(url2)),
                    )
                status2, headers2, data2 = self._request_json(url2)
                if status2 == 200 and isinstance(data2, dict):
                    return status2, headers2, data2
        return status, headers, data
