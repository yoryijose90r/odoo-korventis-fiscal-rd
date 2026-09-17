"""Compose files must interpolate without publishing PostgreSQL."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.conftest import docker_available

COMPOSE_DIR = Path(__file__).resolve().parents[3] / "deploy" / "dgii-registry"


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
    path = COMPOSE_DIR / filename
    env = os.environ.copy()
    env["KORVENTIS_DGII_POSTGRES_PASSWORD"] = "test-only-not-production"
    env["KORVENTIS_DGII_PUBLISH_PORT"] = "18080"
    result = subprocess.run(
        ["docker", "compose", "-f", str(path), "config"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(COMPOSE_DIR),
    )
    assert result.returncode == 0, result.stderr or result.stdout
    rendered = result.stdout
    assert "korventis-dgii-registry:18.0.2.0" in rendered
    assert "postgres:16" in rendered
    assert "KORVENTIS_DGII_MODE: %s" % mode in rendered or (
        "KORVENTIS_DGII_MODE: \"%s\"" % mode in rendered
    )
    assert "127.0.0.1" in rendered
    assert "0.0.0.0:" not in rendered
    # Host must not publish PostgreSQL. The internal container port 5432 is fine.
    for line in rendered.splitlines():
        stripped = line.strip()
        if "5432" in stripped and "published" in stripped.lower():
            pytest.fail("PostgreSQL published to the host: %s" % stripped)
        if stripped.startswith("- ") and "5432" in stripped and "127.0.0.1" in stripped:
            pytest.fail("PostgreSQL host port mapping: %s" % stripped)
