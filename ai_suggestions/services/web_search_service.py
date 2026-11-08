import logging
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


def search_web_resources(query, max_results=8, timeout_seconds=5):
    """Return normalized web results, or an empty list on search failure."""
    query = (query or "").strip()[:500]
    if not query:
        return []

    max_results = max(1, min(int(max_results), 10))

    try:
        # Keep the Django app importable when the optional search dependency
        # has not yet been installed in the active environment.
        from ddgs import DDGS

        raw_results = DDGS(timeout=timeout_seconds).text(
            query,
            region="us-en",
            safesearch="moderate",
            max_results=max_results,
        )
    except Exception as exc:
        logger.warning(
            "Online resource search failed (%s).",
            type(exc).__name__,
        )
        return []

    normalized = []
    seen_urls = set()

    for result in raw_results:
        url = (result.get("href") or result.get("url") or "").strip()
        parsed_url = urlsplit(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            continue
        if url in seen_urls:
            continue

        seen_urls.add(url)
        normalized.append({
            "title": (result.get("title") or "Reference link").strip()[:250],
            "url": url[:2048],
            "snippet": (result.get("body") or "").strip()[:600],
        })

        if len(normalized) >= max_results:
            break

    return normalized
