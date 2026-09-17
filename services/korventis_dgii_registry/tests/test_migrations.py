"""Concurrent migrations and discrete PostgreSQL credentials."""

from __future__ import annotations

import os
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from korventis_dgii_registry.migrate import apply_migrations, schema_status
from tests.conftest import (
    _free_port,
    _wait_postgres,
    connect,
    docker_available,
    recreate_database,
)


def test_concurrent_apply_migrations(db_conninfo):
    fresh = recreate_database(db_conninfo, "korventis_dgii_concurrent")

    def worker():
        return apply_migrations(fresh)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: worker(), range(2)))
    combined = [tuple(item) for item in results]
    assert set(combined) <= {
        ("001_initial", "002_hardening", "003_importer"),
        tuple(),
    }
    assert ("001_initial", "002_hardening", "003_importer") in combined
    status = schema_status(fresh)
    assert status["migrations"] == ["001_initial", "002_hardening", "003_importer"]
    with connect(fresh) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version, count(*) FROM schema_migrations GROUP BY version")
            counts = {row[0]: int(row[1]) for row in cur.fetchall()}
    assert counts == {"001_initial": 1, "002_hardening": 1, "003_importer": 1}


def test_password_with_special_characters():
    if not docker_available():
        pytest.skip("Docker is required for special-character password tests")

    def _run():
        name = "korventis-dgii-pw-test-%s" % uuid.uuid4().hex[:8]
        secret = "".join(("@", "#", "/", ":", "%", "?", "&", "Aa1"))
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
                "POSTGRES_PASSWORD=%s" % secret,
                "-e",
                "POSTGRES_USER=korventis_dgii",
                "-e",
                "POSTGRES_DB=korventis_dgii_pw",
                "-p",
                "127.0.0.1:%s:5432" % port,
                image,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode != 0:
            return False
        conninfo = {
            "host": "127.0.0.1",
            "port": port,
            "user": "korventis_dgii",
            "password": secret,
            "dbname": "korventis_dgii_pw",
        }
        try:
            _wait_postgres(conninfo)
            apply_migrations(conninfo)
            with connect(conninfo) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM schema_migrations")
                    return cur.fetchone()[0] == 3
        except Exception:  # noqa: BLE001
            return False
        finally:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)

    assert _run() is True
