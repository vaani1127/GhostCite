"""The Render blueprint must stay a demo-only deployment with no SerpApi key."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ghostcite.settings import API_KEY_ENV, HOSTED_DEMO_ENV
from ghostcite.web.app import create_app

ROOT = Path(__file__).resolve().parents[2]


def _service() -> dict[str, Any]:
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    (service,) = blueprint["services"]
    assert isinstance(service, dict)
    return service


def test_blueprint_is_a_free_docker_web_service() -> None:
    service = _service()
    assert (service["type"], service["runtime"], service["plan"]) == ("web", "docker", "free")
    # Served at https://ghostcite-demo.onrender.com; no custom domain to keep verified.
    assert "domains" not in service
    assert service["name"] == "ghostcite-demo"


def test_blueprint_is_demo_only_and_has_no_key() -> None:
    env = {item["key"]: item.get("value") for item in _service()["envVars"]}
    assert env[HOSTED_DEMO_ENV] == "true"
    assert API_KEY_ENV not in env
    assert not any("SERPAPI" in key or "KEY" in key for key in env)


def test_health_check_path_is_a_real_route(tmp_path: Path) -> None:
    from ghostcite.settings import Settings

    app = create_app(Settings(api_key=None, cache_dir=tmp_path))
    paths = {getattr(route, "path", None) for route in app.routes}
    assert _service()["healthCheckPath"] in paths
