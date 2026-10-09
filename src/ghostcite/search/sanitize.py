"""Strip anything account-specific from SerpApi responses before they are stored.

Responses end up in the local cache, in test fixtures and in the committed demo bundle.
None of them may contain an API key or links into the account's private search archive.
"""

from __future__ import annotations

from typing import Any

from ghostcite.redact import redact

# Keys whose values are account-specific links or credentials. Any key ending in
# "_endpoint" (json_endpoint, markdown_endpoint, ...) is a search-archive link and is dropped too.
_DROPPED_KEYS = frozenset(
    {"api_key", "json_endpoint", "raw_html_file", "prettify_html_file", "pixel_position_endpoint"}
)
_ARCHIVE_PATH = "serpapi.com/searches/"


def _is_account_specific(key: str, value: Any) -> bool:
    if key in _DROPPED_KEYS or key.endswith("_endpoint"):
        return True
    # Thumbnails are served from under the search's own archive path; GhostCite never
    # uses images, and the links identify the account's searches.
    return isinstance(value, str) and _ARCHIVE_PATH in value


def _pick(source: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: source[k] for k in keys if isinstance(source, dict) and k in source}


def trim_response(response: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields GhostCite's parsers read (plus provenance), for committed bundles.

    Replaying a trimmed response gives exactly the same candidates as the full one, while
    the file shrinks by about 90%.
    """
    results = []
    for item in response.get("organic_results") or []:
        kept = _pick(item, ("position", "title", "result_id", "link", "snippet", "date", "source"))
        info = item.get("publication_info") if isinstance(item, dict) else None
        if isinstance(info, dict):
            kept["publication_info"] = {
                "summary": info.get("summary", ""),
                "authors": [_pick(a, ("name",)) for a in info.get("authors") or []],
            }
        links = item.get("inline_links") if isinstance(item, dict) else None
        if isinstance(links, dict):
            kept["inline_links"] = {
                name: _pick(links[name], ("total",))
                for name in ("cited_by", "versions")
                if name in links
            }
        results.append(kept)
    trimmed: dict[str, Any] = {
        "search_metadata": _pick(response.get("search_metadata"), ("id", "status", "created_at")),
        "search_parameters": response.get("search_parameters", {}),
        "organic_results": results,
    }
    if "error" in response:
        trimmed["error"] = response["error"]
    graph = response.get("knowledge_graph")
    if isinstance(graph, dict):
        trimmed["knowledge_graph"] = {
            **_pick(graph, ("title", "type", "description", "authors", "author")),
            **_pick(graph, ("originally_published", "publication_date", "first_published")),
            **_pick(graph, ("published", "date")),
            "source": _pick(graph.get("source"), ("name", "link")),
        }
    return trimmed


def sanitize_response(value: Any) -> Any:
    """Return a deep copy of ``value`` with account-specific keys removed and secrets redacted."""
    if isinstance(value, dict):
        return {
            str(key): sanitize_response(item)
            for key, item in value.items()
            if not _is_account_specific(str(key), item)
        }
    if isinstance(value, list):
        return [sanitize_response(item) for item in value]
    if isinstance(value, str):
        return redact(value)
    return value
