from __future__ import annotations

from pathlib import Path

import pytest

from ghostcite import samples
from ghostcite.errors import InputError


def _fake_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point samples.py at a fake install: <root>/src/ghostcite/samples.py."""
    module = tmp_path / "src" / "ghostcite" / "samples.py"
    module.parent.mkdir(parents=True)
    module.write_text("", encoding="utf-8")
    monkeypatch.setattr(samples, "__file__", str(module))
    return module


def test_packaged_samples_win(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _fake_package(tmp_path, monkeypatch)
    packaged = module.parent / "_samples"
    packaged.mkdir()
    (packaged / "sample.bib").write_text("@misc{x}", encoding="utf-8")
    (tmp_path / "samples").mkdir()
    assert samples.samples_dir() == packaged
    assert samples.sample_path("sample.bib") == packaged / "sample.bib"


def test_checkout_samples_are_the_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_package(tmp_path, monkeypatch)
    checkout = tmp_path / "samples"
    checkout.mkdir()
    assert samples.samples_dir() == checkout


def test_missing_samples(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_package(tmp_path, monkeypatch)
    with pytest.raises(InputError, match="not installed"):
        samples.samples_dir()
    (tmp_path / "samples").mkdir()
    with pytest.raises(InputError, match=r"demo_cache/bundle\.json was not found"):
        samples.sample_path(samples.DEMO_BUNDLE)
