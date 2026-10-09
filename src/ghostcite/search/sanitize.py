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
