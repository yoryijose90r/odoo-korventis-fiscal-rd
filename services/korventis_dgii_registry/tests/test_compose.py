"""Compose files must interpolate without publishing PostgreSQL."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.conftest import docker_available

COMPOSE_DIR = Path(__file__).resolve().parents[3] / "deploy" / "dgii-registry"


def _compose_flags(filename, password):
    env = os.environ.copy()
    env["KORVENTIS_DGII_POSTGRES_PASSWORD"] = password
    env["KORVENTIS_DGII_PUBLISH_PORT"] = "18080"
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_DIR / filename), "config"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(COMPOSE_DIR),
    )
    rendered = result.stdout or ""
    postgres_published = False
    for line in rendered.splitlines():
        stripped = line.strip()
        if "5432" in stripped and "published" in stripped.lower():
            postgres_published = True
        if stripped.startswith("- ") and "5432" in stripped and "127.0.0.1" in stripped:
            postgres_published = True
    return {
        "ok": result.returncode == 0,
        "has_image": "korventis-dgii-registry:18.0.2.0" in rendered,
        "has_postgres": "postgres:16" in rendered,
        "no_database_url": "KORVENTIS_DGII_DATABASE_URL" not in rendered,
        "no_postgres_url": "postgresql://" not in rendered and "postgres://" not in rendered,
        "has_pghost": "KORVENTIS_DGII_PGHOST" in rendered,
        "loopback": "127.0.0.1" in rendered,
        "no_wildcard_publish": "0.0.0.0:" not in rendered,
        "postgres_published": postgres_published,
    }


@pytest.mark.parametrize(
    "filename,mode",
    (
        ("docker-compose.local.yml", "local"),
        ("docker-compose.shared.yml", "shared"),
    ),
)
def test_compose_config_renders_without_postgres_ports(filename, mode):
    if not docker_available():
        pytest.skip("Docker is required to render compose files")
    source = (COMPOSE_DIR / filename).read_text(encoding="utf-8")
    assert "KORVENTIS_DGII_DATABASE_URL" not in source
    assert "KORVENTIS_DGII_PGHOST: postgres" in source
    assert "127.0.0.1:${KORVENTIS_DGII_PUBLISH_PORT:-8080}:8080" in source
    assert "KORVENTIS_DGII_MODE: %s" % mode in source
    flags = _compose_flags(filename, "test-only-not-production")
    assert flags["ok"]
    assert flags["has_image"]
    assert flags["has_postgres"]
    assert flags["no_database_url"]
    assert flags["has_pghost"]
    assert flags["loopback"]
    assert flags["no_wildcard_publish"]
    assert flags["postgres_published"] is False


@pytest.mark.parametrize(
    "filename",
    ("docker-compose.local.yml", "docker-compose.shared.yml"),
)
def test_compose_accepts_special_password_without_url(filename):
    if not docker_available():
        pytest.skip("Docker is required to render compose files")
    secret = "".join(("@", "#", "/", ":", "%", "?", "&", "Aa1"))
    flags = _compose_flags(filename, secret)
    assert flags["ok"]
    assert flags["no_database_url"]
    assert flags["no_postgres_url"]
