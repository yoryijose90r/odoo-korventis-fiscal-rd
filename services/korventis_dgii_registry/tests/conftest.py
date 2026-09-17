"""Shared test fixtures. Schema tests use an ephemeral Docker PostgreSQL."""

from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid

import psycopg
import pytest


def docker_available():
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=20,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _free_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_postgres(url, timeout=60):
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with psycopg.connect(url, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready: %s" % last_error)


@pytest.fixture
def registry_db(database_url):
    from korventis_dgii_registry.migrate import apply_migrations

    apply_migrations(database_url)
    yield database_url
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE dgii_rnc, dgii_rnc_version, dgii_import_run,
                         dgii_api_audit, dgii_installation
                RESTART IDENTITY CASCADE
                """
            )
        conn.commit()


@pytest.fixture(scope="session")
def database_url():
    env_url = os.environ.get("KORVENTIS_DGII_TEST_DATABASE_URL", "").strip()
    if env_url:
        yield env_url
        return
    if not docker_available():
        pytest.skip(
            "Docker is required for schema tests unless "
            "KORVENTIS_DGII_TEST_DATABASE_URL is set"
        )
    name = "korventis-dgii-schema-test-%s" % uuid.uuid4().hex[:8]
    password = "test-only-not-production"
    port = _free_port()
    image = os.environ.get("KORVENTIS_DGII_TEST_POSTGRES_IMAGE", "postgres:16")
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-e",
            "POSTGRES_PASSWORD=%s" % password,
            "-e",
            "POSTGRES_USER=korventis_dgii",
            "-e",
            "POSTGRES_DB=korventis_dgii_test",
            "-p",
            "127.0.0.1:%s:5432" % port,
            image,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        pytest.fail("docker run postgres failed: %s" % (run.stderr or run.stdout))
    url = (
        "postgresql://korventis_dgii:%s@127.0.0.1:%s/korventis_dgii_test"
        % (password, port)
    )
    try:
        _wait_postgres(url)
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
