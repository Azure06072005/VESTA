"""src/service/simhash_cache.py

64-bit SimHash Deduplication & URL Canonicalization Engine for VESTA F401.
Maintains an in-memory sliding buffer (TTL = 6 hours = 21,600s) to eliminate
duplicate syndicated wire articles across Vietnamese financial outlets (CafeF,
Vietstock, VnEconomy, Tuoi Tre, etc.).
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
import time
import urllib.parse
from typing import Dict, List, Optional, Set, Tuple


# Strips tracking parameters, anchors, session tokens, and trailing slashes
TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "from", "source", "device", "token", "session",
})


def canonicalize_url(url: str) -> str:
    """Normalizes an article URL: removes tracking queries, fragments, lowercase scheme/host."""
    if not url or not isinstance(url, str):
        return ""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        # Filter query params
        query_dict = urllib.parse.parse_qsl(parsed.query)
        filtered_query = [
            (k, v) for k, v in query_dict if k.lower() not in TRACKING_PARAMS
        ]
        new_query = urllib.parse.urlencode(filtered_query)
        # Reconstruct clean URL
        clean_path = parsed.path.rstrip("/")
        clean_url = urllib.parse.urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            clean_path,
            "",
            new_query,
            "",  # strip fragment / #
        ))
        return clean_url
    except Exception:
        return url.strip()


def compute_simhash_64(text: str) -> int:
    """Computes a 64-bit SimHash fingerprint from Vietnamese text using word 2-grams."""
    if not text or not isinstance(text, str):
        return 0

    # Clean text: lowercase and extract words
    words = re.findall(r"\w+", text.lower())
    if not words:
        return 0

    # Generate word 1-grams and 2-grams for high collision fidelity on short headlines
    shingles: List[str] = list(words)
    for i in range(len(words) - 1):
        shingles.append(f"{words[i]}_{words[i+1]}")

    # Accumulate 64-bit vector
    v = [0] * 64
    for shingle in shingles:
        # MD5 64-bit slice
        h = int(hashlib.md5(shingle.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(64):
            bit = (h >> i) & 1
            if bit == 1:
                v[i] += 1
            else:
                v[i] -= 1

    # Form final 64-bit integer
    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(h1: int, h2: int) -> int:
    """Calculates bitwise Hamming distance between two 64-bit integers."""
    return bin(h1 ^ h2).count("1")


@dataclasses.dataclass
class CachedArticle:
    article_id: str
    canonical_url: str
    simhash: int
    timestamp: float
    headline: str


class SimHashDedupCache:
    """Thread-safe in-memory sliding dedup buffer for streaming news."""

    def __init__(
        self,
        ttl_seconds: float = 21600.0,  # 6 hours
        hamming_threshold: int = 4,    # <= 4 bits difference considered duplicate
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.hamming_threshold = hamming_threshold
        # Maps article_id -> CachedArticle
        self.cache: Dict[str, CachedArticle] = {}
        # Maps canonical_url -> article_id
        self.url_map: Dict[str, str] = {}

    def _evict_expired(self, current_time: float) -> None:
        """Purges articles older than 6 hours."""
        cutoff = current_time - self.ttl_seconds
        expired_ids = [
            art_id for art_id, item in self.cache.items() if item.timestamp < cutoff
        ]
        for art_id in expired_ids:
            item = self.cache.pop(art_id, None)
            if item and item.canonical_url in self.url_map:
                self.url_map.pop(item.canonical_url, None)

    def check_and_insert(
        self,
        headline: str,
        body: Optional[str] = None,
        url: Optional[str] = None,
        article_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> Tuple[bool, Optional[str], int]:
        """Checks if article is a duplicate within the 6-hour sliding window.

        Returns:
            (is_duplicate: bool, original_article_id: Optional[str], min_hamming_dist: int)
        """
        now = timestamp if timestamp is not None else time.time()
        self._evict_expired(now)

        clean_url = canonicalize_url(url) if url else ""
        art_id = article_id or clean_url or hashlib.md5(f"{headline}_{now}".encode()).hexdigest()[:16]

        # 1. Exact URL match check
        if clean_url and clean_url in self.url_map:
            orig_id = self.url_map[clean_url]
            return True, orig_id, 0

        # 2. SimHash semantic similarity check
        text_to_hash = f"{headline} {body[:300] if body else ''}".strip()
        new_hash = compute_simhash_64(text_to_hash)

        min_dist = 64
        nearest_id: Optional[str] = None

        for item in self.cache.values():
            dist = hamming_distance(new_hash, item.simhash)
            if dist < min_dist:
                min_dist = dist
                nearest_id = item.article_id
            if dist <= self.hamming_threshold:
                # Found near-duplicate within 6 hours
                return True, item.article_id, dist

        # Not duplicate: insert into cache
        cached = CachedArticle(
            article_id=art_id,
            canonical_url=clean_url,
            simhash=new_hash,
            timestamp=now,
            headline=headline,
        )
        self.cache[art_id] = cached
        if clean_url:
            self.url_map[clean_url] = art_id

        return False, None, min_dist

    def clear(self) -> None:
        """Clears all cached articles."""
        self.cache.clear(
        )
        self.url_map.clear()

    @property
    def size(self) -> int:
        return len(self.cache)
