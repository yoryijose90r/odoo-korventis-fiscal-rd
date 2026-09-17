"""Shared test fixtures. Schema tests use an ephemeral Docker PostgreSQL."""

from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid

import psycopg
import pytest
from psycopg import sql


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


def connect(conninfo):
    return psycopg.connect(**conninfo)


def _wait_postgres(conninfo, timeout=60):
    deadline = time.time() + timeout
    last_error_type = None
    while time.time() < deadline:
        try:
            with connect(conninfo) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return
        except Exception as exc:  # noqa: BLE001
            last_error_type = type(exc).__name__
            time.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready (%s)" % last_error_type)


def recreate_database(conninfo, dbname):
    admin = dict(conninfo, dbname="postgres")
    ident = sql.Identifier(dbname)
    with psycopg.connect(**admin, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (dbname,),
            )
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(ident))
            cur.execute(sql.SQL("CREATE DATABASE {}").format(ident))
    return dict(conninfo, dbname=dbname)


@pytest.fixture
def db_conninfo(database_conninfo):
    from korventis_dgii_registry.migrate import apply_migrations

    apply_migrations(database_conninfo)
    yield database_conninfo
    with connect(database_conninfo) as conn:
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
def database_conninfo():
    env_host = os.environ.get("KORVENTIS_DGII_TEST_PGHOST", "").strip()
    if env_host:
        yield {
            "host": env_host,
            "port": int(os.environ.get("KORVENTIS_DGII_TEST_PGPORT", "5432")),
            "user": os.environ["KORVENTIS_DGII_TEST_PGUSER"],
            "password": os.environ["KORVENTIS_DGII_TEST_PGPASSWORD"],
            "dbname": os.environ["KORVENTIS_DGII_TEST_PGDATABASE"],
        }
        return
    if not docker_available():
        pytest.skip(
            "Docker is required for schema tests unless discrete "
            "KORVENTIS_DGII_TEST_PG* variables are set"
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
        pytest.fail("docker run postgres failed")
    conninfo = {
        "host": "127.0.0.1",
        "port": port,
        "user": "korventis_dgii",
        "password": password,
        "dbname": "korventis_dgii_test",
    }
    try:
        _wait_postgres(conninfo)
        yield conninfo
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
