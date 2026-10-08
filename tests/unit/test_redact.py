from __future__ import annotations

from ghostcite.redact import REDACTED, redact, register_secret

_HEX_KEY = "a" * 32 + "0123456789abcdef" * 2


def test_registered_secret_is_removed() -> None:
    register_secret("s3cr3t-value-123")
    assert redact("token s3cr3t-value-123 leaked") == f"token {REDACTED} leaked"


def test_short_values_are_not_registered() -> None:
    # Registering a tiny value would redact ordinary words everywhere.
    register_secret("abc")
    assert redact("abc abc") == "abc abc"


def test_key_shaped_hex_is_removed_even_if_unregistered() -> None:
    assert redact(f"key={_HEX_KEY}!") == f"key={REDACTED}!"


def test_longer_hex_runs_are_not_treated_as_keys() -> None:
    sha512_like = "f" * 128
    assert redact(sha512_like) == sha512_like


def test_api_key_url_parameter_is_removed() -> None:
    url = "https://serpapi.com/search?engine=google_scholar&api_key=xyz987&q=x"
    assert redact(url) == f"https://serpapi.com/search?engine=google_scholar&api_key={REDACTED}&q=x"


def test_api_key_in_json_and_repr_is_removed() -> None:
    assert redact('{"api_key": "xyz987", "q": "x"}') == f'{{"api_key": "{REDACTED}", "q": "x"}}'
    assert redact("{'api_key': 'xyz987'}") == f"{{'api_key': '{REDACTED}'}}"


def test_text_without_secrets_is_unchanged() -> None:
    text = "Attention is all you need (2017)"
    assert redact(text) == text
