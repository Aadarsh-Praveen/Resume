"""
Location geocoder — determines if a job location is in the US.

Strategy (fastest to slowest):
  1. Regex fast-path: obvious US indicators (state abbrevs, "United States", "Remote")
  2. Regex fast-path: obvious non-US indicators (known foreign city/country patterns)
  3. DB cache lookup: previously geocoded location → instant
  4. Nominatim geocode (free, OpenStreetMap, no API key): 1 req/sec rate limit
  5. Fallback: allow through (better to over-collect than silently drop)

The DB cache means each unique location string is geocoded at most once ever.
"""

import logging
import re
import time

logger = logging.getLogger(__name__)

# Nominatim rate limit: 1 request per second
_NOMINATIM_DELAY = 1.1

# State abbreviations regex — matches ", CA" ", NY" etc.
_STATE_ABBREV_RE = re.compile(
    r",\s*([A-Z]{2})\b",
)
_US_STATE_ABBREVS = {
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in",
    "ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
    "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn",
    "tx","ut","vt","va","wa","wv","wi","wy","dc",
}

# Obvious non-US markers — if any of these appear, skip geocoding
_NON_US_MARKERS = {
    "india", "bengaluru", "bangalore", "mumbai", "hyderabad", "pune", "chennai",
    "delhi", "noida", "gurugram", "gurgaon", "kolkata",
    "uk", "united kingdom", "london", "manchester", "edinburgh",
    "canada", "toronto", "vancouver", "montreal", "ottawa",
    "australia", "sydney", "melbourne", "brisbane",
    "germany", "berlin", "munich", "hamburg",
    "france", "paris",
    "netherlands", "amsterdam",
    "singapore",
    "ireland", "dublin",
    "brazil", "são paulo", "sao paulo",
    "mexico", "ciudad de méxico",
    "japan", "tokyo",
    "china", "beijing", "shanghai",
    "israel", "tel aviv",
    "sweden", "stockholm",
    "switzerland", "zurich",
    "spain", "madrid", "barcelona",
    "italy", "milan", "rome",
    "poland", "warsaw",
    "ukraine", "kyiv",
    "romania", "bucharest",
}


def is_us_or_remote(location: str) -> bool:
    """
    Return True if the location is US-based, remote, or unspecified.
    Uses regex fast-paths first, then DB cache, then Nominatim geocoding.
    """
    if not location or not location.strip():
        return True  # blank = no restriction

    loc = location.strip()
    loc_lower = loc.lower()

    # ── Fast path: remote / blank ──────────────────────────────────────────────
    if "remote" in loc_lower:
        return True

    # ── Fast path: explicit US ─────────────────────────────────────────────────
    if "united states" in loc_lower or loc_lower in ("us", "usa"):
        return True
    if loc_lower.startswith("us,") or ", us," in loc_lower or loc_lower.endswith(", us"):
        return True

    # ── Fast path: state abbreviation pattern ", CA" ", NY" etc. ──────────────
    for m in _STATE_ABBREV_RE.finditer(loc):
        if m.group(1).lower() in _US_STATE_ABBREVS:
            return True

    # ── Fast path: obvious non-US ─────────────────────────────────────────────
    for marker in _NON_US_MARKERS:
        if marker in loc_lower:
            _write_cache(loc, False)
            return False

    # ── DB cache lookup ────────────────────────────────────────────────────────
    cached = _read_cache(loc)
    if cached is not None:
        return cached

    # ── Nominatim geocode ──────────────────────────────────────────────────────
    result = _geocode(loc)
    if result is not None:
        _write_cache(loc, result)
        return result

    # ── Fallback: allow through ────────────────────────────────────────────────
    logger.debug("Location '%s' — geocode unavailable, allowing through", loc)
    return True


def _read_cache(location: str) -> bool | None:
    try:
        from pipeline.dedup import get_cached_location
        return get_cached_location(location)
    except Exception:
        return None


def _write_cache(location: str, is_us: bool) -> None:
    try:
        from pipeline.dedup import cache_location
        cache_location(location, is_us)
    except Exception:
        pass


def _geocode(location: str) -> bool | None:
    """
    Geocode via Nominatim. Returns True if US, False if not, None on failure.
    """
    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderServiceError, GeocoderTimedOut

        geocoder = Nominatim(user_agent="applyflow-job-agent/1.0", timeout=5)
        time.sleep(_NOMINATIM_DELAY)  # respect rate limit

        result = geocoder.geocode(location, exactly_one=True, addressdetails=True)
        if result is None:
            logger.debug("Nominatim: no result for '%s'", location)
            return None

        country_code = (
            result.raw.get("address", {}).get("country_code", "")
        ).lower()
        is_us = country_code == "us"
        logger.info("Geocoded '%s' → country_code='%s' → is_us=%s", location, country_code, is_us)
        return is_us

    except ImportError:
        logger.warning("geopy not installed — install with: pip install geopy")
        return None
    except Exception as e:
        logger.warning("Nominatim geocode failed for '%s': %s", location, e)
        return None
