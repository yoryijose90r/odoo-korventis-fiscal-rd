"""Compose files must interpolate without publishing PostgreSQL."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.conftest import docker_available

COMPOSE_DIR = Path(__file__).resolve().parents[3] / "deploy" / "dgii-registry"
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_MIN_RECORDS = (
    'KORVENTIS_DGII_IMPORT_MIN_RECORDS: "${KORVENTIS_DGII_IMPORT_MIN_RECORDS:?Set import minimum in .env}"'
)


def _compose_env(password, extra=None):
    env = os.environ.copy()
    for name in (
        "KORVENTIS_DGII_IMPORT_MIN_RECORDS",
        "KORVENTIS_DGII_IMPORT_MAX_REJECT_RATIO",
        "KORVENTIS_DGII_RESTORE_LOCK_TIMEOUT_MS",
        "KORVENTIS_DGII_ALLOW_REMOTE",
        "KORVENTIS_DGII_AUTO_IMPORT",
    ):
        env.pop(name, None)
    env["KORVENTIS_DGII_POSTGRES_PASSWORD"] = password
    env["KORVENTIS_DGII_PUBLISH_PORT"] = "18080"
    if extra:
        env.update(extra)
    return env


def _compose_config(filename, password, extra=None):
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_DIR / filename), "config"],
        capture_output=True,
        text=True,
        check=False,
        env=_compose_env(password, extra),
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
    return result, rendered, postgres_published


def _compose_flags(filename, password, extra=None):
    result, rendered, postgres_published = _compose_config(filename, password, extra)
    return {
        "ok": result.returncode == 0,
        "stderr": result.stderr or "",
        "rendered": rendered,
        "has_image": "korventis-dgii-registry:18.0.2.0" in rendered,
        "has_postgres": "postgres:16" in rendered,
        "no_database_url": "KORVENTIS_DGII_DATABASE_URL" not in rendered,
        "no_postgres_url": "postgresql://" not in rendered and "postgres://" not in rendered,
        "has_pghost": "KORVENTIS_DGII_PGHOST" in rendered,
        "loopback": "127.0.0.1" in rendered,
        "no_wildcard_publish": "0.0.0.0:" not in rendered,
        "postgres_published": postgres_published,
        "min_records": "KORVENTIS_DGII_IMPORT_MIN_RECORDS" in rendered,
        "allow_remote_false": "KORVENTIS_DGII_ALLOW_REMOTE: \"false\"" in rendered
        or "KORVENTIS_DGII_ALLOW_REMOTE: false" in rendered,
        "auto_import_false": "KORVENTIS_DGII_AUTO_IMPORT: \"false\"" in rendered
        or "KORVENTIS_DGII_AUTO_IMPORT: false" in rendered,
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
    extra = None
    if mode == "shared":
        extra = {"KORVENTIS_DGII_IMPORT_MIN_RECORDS": "750000"}
        assert SHARED_MIN_RECORDS in source
    flags = _compose_flags(filename, "test-only-not-production", extra)
    assert flags["ok"], flags["stderr"]
    assert flags["has_image"]
    assert flags["has_postgres"]
    assert flags["no_database_url"]
    assert flags["has_pghost"]
    assert flags["loopback"]
    assert flags["no_wildcard_publish"]
    assert flags["postgres_published"] is False
    assert flags["allow_remote_false"]
    assert flags["auto_import_false"]
    assert flags["min_records"]


@pytest.mark.parametrize(
    "filename",
    ("docker-compose.local.yml", "docker-compose.shared.yml"),
)
def test_compose_accepts_special_password_without_url(filename):
    if not docker_available():
        pytest.skip("Docker is required to render compose files")
    secret = "".join(("@", "#", "/", ":", "%", "?", "&", "Aa1"))
    extra = {"KORVENTIS_DGII_IMPORT_MIN_RECORDS": "750000"}
    flags = _compose_flags(filename, secret, extra)
    assert flags["ok"], flags["stderr"]
    assert flags["no_database_url"]
    assert flags["no_postgres_url"]


def test_shared_compose_injects_import_min_records():
    if not docker_available():
        pytest.skip("Docker is required to render compose files")
    flags = _compose_flags(
        "docker-compose.shared.yml",
        "test-only-not-production",
        {"KORVENTIS_DGII_IMPORT_MIN_RECORDS": "750000"},
    )
    assert flags["ok"], flags["stderr"]
    assert "750000" in flags["rendered"]
    assert "KORVENTIS_DGII_IMPORT_MIN_RECORDS" in flags["rendered"]


def test_shared_compose_requires_import_min_records():
    if not docker_available():
        pytest.skip("Docker is required to render compose files")
    result, rendered, _postgres = _compose_config(
        "docker-compose.shared.yml",
        "test-only-not-production",
    )
    assert result.returncode != 0
    combined = "%s\n%s" % (rendered, result.stderr or "")
    assert "KORVENTIS_DGII_IMPORT_MIN_RECORDS" in combined or "import minimum" in combined.lower()


def test_local_compose_defaults_min_records_when_unset():
    if not docker_available():
        pytest.skip("Docker is required to render compose files")
    flags = _compose_flags("docker-compose.local.yml", "test-only-not-production")
    assert flags["ok"], flags["stderr"]
    assert "KORVENTIS_DGII_IMPORT_MIN_RECORDS" in flags["rendered"]


def test_gitignore_excludes_env_and_dump_backups():
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in text
    assert "*.dump" in text
    for relative in ("deploy/dgii-registry/.env", "dgii_registry_pre_oficial.dump"):
        check = subprocess.run(
            ["git", "check-ignore", "-q", relative],
            cwd=str(REPO_ROOT),
            check=False,
        )
        assert check.returncode == 0, relative
