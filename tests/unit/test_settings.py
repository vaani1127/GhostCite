from __future__ import annotations

from pathlib import Path

from ghostcite.redact import REDACTED, redact
from ghostcite.settings import API_KEY_ENV, CACHE_DIR_ENV, CREDITS_LOG_ENV, load_settings


def test_no_key_anywhere(tmp_path: Path) -> None:
    settings = load_settings(environ={}, dotenv_path=tmp_path / "missing.env")
    assert settings.api_key is None
    assert not settings.has_api_key


def test_key_from_environment_is_masked_and_registered(tmp_path: Path) -> None:
    settings = load_settings(
        environ={API_KEY_ENV: "  env-key-123456  "},  # gitleaks:allow
        dotenv_path=tmp_path / "none",
    )
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "env-key-123456"
    assert "env-key-123456" not in repr(settings)
    assert redact("x env-key-123456 y") == f"x {REDACTED} y"


def test_key_from_dotenv_file(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"{API_KEY_ENV}=file-key-123456\n", encoding="utf-8")
    settings = load_settings(environ={}, dotenv_path=dotenv)
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "file-key-123456"


def test_environment_wins_over_dotenv(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"{API_KEY_ENV}=file-key-123456\n", encoding="utf-8")
    settings = load_settings(
        environ={API_KEY_ENV: "env-key-654321"},  # gitleaks:allow
        dotenv_path=dotenv,
    )
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "env-key-654321"


def test_blank_key_counts_as_missing(tmp_path: Path) -> None:
    settings = load_settings(environ={API_KEY_ENV: "   "}, dotenv_path=tmp_path / "none")
    assert settings.api_key is None


def test_dotenv_defaults_to_current_directory(tmp_path: Path) -> None:
    # The autouse fixture has already chdir'd into tmp_path.
    (tmp_path / ".env").write_text(f"{API_KEY_ENV}=cwd-key-123456\n", encoding="utf-8")
    settings = load_settings(environ={})
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() == "cwd-key-123456"


def test_cache_dir_override_and_default(tmp_path: Path) -> None:
    custom = load_settings(environ={CACHE_DIR_ENV: str(tmp_path / "c")}, dotenv_path=tmp_path)
    assert custom.cache_dir == tmp_path / "c"
    default = load_settings(environ={}, dotenv_path=tmp_path / "none")
    assert "ghostcite" in str(default.cache_dir).lower()


def test_reads_process_environment_by_default() -> None:
    # The autouse fixture sets GHOSTCITE_CACHE_DIR in os.environ.
    settings = load_settings()
    assert settings.cache_dir.name == "cache"


def test_credits_log_location(tmp_path: Path) -> None:
    none = tmp_path / "none"
    cache = tmp_path / "cache"
    plain = load_settings(environ={CACHE_DIR_ENV: str(cache)}, dotenv_path=none)
    assert plain.credits_log == cache / "credits.log"
    (tmp_path / ".dev").mkdir()
    checkout = load_settings(environ={CACHE_DIR_ENV: str(cache)}, dotenv_path=none)
    assert checkout.credits_log == tmp_path / ".dev" / "credits.log"
    chosen = load_settings(environ={CREDITS_LOG_ENV: str(tmp_path / "x.log")}, dotenv_path=none)
    assert chosen.credits_log == tmp_path / "x.log"
