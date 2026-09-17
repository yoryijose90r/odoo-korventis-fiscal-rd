"""Importer integration tests against disposable PostgreSQL. Fictional ZIPs only."""

from __future__ import annotations

import copy
import threading
import zipfile
from http.client import HTTPConnection
import json

import pytest

from korventis_dgii_registry.archive import ZipLimits
from korventis_dgii_registry.importer import (
    IMPORT_LOCK_KEY,
    ImportLimits,
    RegistryImportError,
    import_zip,
    restore_previous,
)
from korventis_dgii_registry.migrate import probe_readiness
from korventis_dgii_registry.server import make_server
from tests.conftest import connect
from tests.test_health import _assert_no_secrets, _settings
from tests.zip_fixtures import csv_bytes, valid_rows, write_zip


def _count(conninfo, sql, params=None):
    with connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()[0]


def test_import_valid_and_readiness_active(db_conninfo, tmp_path, monkeypatch):
    path = write_zip(tmp_path / "ok.zip", csv_bytes(valid_rows()))
    result = import_zip(db_conninfo, path, source_label="fixture", activate=True)
    assert result.state == "success"
    assert result.accepted_count == 3
    assert result.rejected_count == 0
    stored = _count(
        db_conninfo,
        "SELECT rnc_normalizado FROM dgii_rnc WHERE rnc_normalizado = %s",
        ("012345678",),
    )
    assert stored == "012345678"
    spanish = _count(
        db_conninfo,
        "SELECT count(*) FROM dgii_rnc WHERE razon_social LIKE %s",
        ("%CIA%",),
    )
    assert spanish == 1
    suspendido = _count(
        db_conninfo,
        "SELECT count(*) FROM dgii_rnc WHERE estado = %s",
        ("SUSPENDIDO",),
    )
    assert suspendido == 1
    settings = _settings(db_conninfo, monkeypatch)
    payload = probe_readiness(settings)
    assert payload["registry"] == "active"
    _assert_no_secrets(payload, db_conninfo)
    assert "131000001" not in (result.details or "")


def test_import_validate_only_stays_pending(db_conninfo, tmp_path, monkeypatch):
    path = write_zip(tmp_path / "val.zip", csv_bytes(valid_rows()))
    result = import_zip(db_conninfo, path, activate=False)
    assert result.state == "success"
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version WHERE state = 'staging'") == 1
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version WHERE state = 'active'") == 0
    payload = probe_readiness(_settings(db_conninfo, monkeypatch))
    assert payload["registry"] == "pending"


def test_import_leading_zeros_and_bom(db_conninfo, tmp_path):
    path = write_zip(
        tmp_path / "bom.zip",
        csv_bytes(valid_rows(), encoding="utf-8", bom=True),
    )
    result = import_zip(db_conninfo, path, activate=True)
    assert result.state == "success"
    assert _count(
        db_conninfo,
        "SELECT rnc FROM dgii_rnc WHERE rnc = %s",
        ("012345678",),
    ) == "012345678"


def test_import_rejects_wrong_headers(db_conninfo, tmp_path):
    path = write_zip(
        tmp_path / "hdr.zip",
        csv_bytes(valid_rows(), header=["A", "B", "C", "D", "E", "F"]),
    )
    result = import_zip(db_conninfo, path, activate=True)
    assert result.state == "failed"
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc") == 0


def test_import_skips_empty_rows_and_warns_invalid_dates(db_conninfo, tmp_path):
    rows = valid_rows() + [
        ["", "", "", "", "", ""],
        ["131000003", "FECHA RARA", "COMERCIO", "99/99/2010", "ACTIVO", "NORMAL"],
    ]
    path = write_zip(tmp_path / "emptyrow.zip", csv_bytes(rows))
    result = import_zip(db_conninfo, path, activate=True)
    assert result.state == "success"
    assert result.accepted_count == 4
    assert result.warning_count == 1
    assert result.rejected_count == 0


def test_import_rejects_empty_csv(db_conninfo, tmp_path):
    path = write_zip(tmp_path / "empty.zip", csv_bytes([]))
    result = import_zip(db_conninfo, path, activate=True)
    assert result.state == "failed"


def test_import_malformed_and_duplicate_rnc(db_conninfo, tmp_path):
    rows = valid_rows() + [["abc", "BAD", "X", "01/01/2010", "ACTIVO", "NORMAL"]]
    path = write_zip(tmp_path / "badrow.zip", csv_bytes(rows))
    result = import_zip(db_conninfo, path, activate=True)
    assert result.state == "failed"
    dup = [
        ["131000001", "A", "X", "01/01/2010", "ACTIVO", "NORMAL"],
        ["131000001", "B", "Y", "01/01/2010", "ACTIVO", "NORMAL"],
    ]
    path2 = write_zip(tmp_path / "dup.zip", csv_bytes(dup))
    result2 = import_zip(db_conninfo, path2, activate=True)
    assert result2.state == "failed"
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc") == 0


def test_import_corrupt_zip(db_conninfo, tmp_path):
    path = tmp_path / "c.zip"
    path.write_bytes(b"not-zip")
    result = import_zip(db_conninfo, path, activate=True)
    assert result.state == "failed"


def test_same_sha_is_idempotent(db_conninfo, tmp_path):
    path = write_zip(tmp_path / "once.zip", csv_bytes(valid_rows()))
    first = import_zip(db_conninfo, path, activate=True)
    second = import_zip(db_conninfo, path, activate=True)
    assert first.state == "success"
    assert second.state == "unchanged"
    assert second.version_id == first.version_id
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version") == 1
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc") == 3


def test_failure_before_activate_keeps_previous(db_conninfo, tmp_path):
    first_zip = write_zip(tmp_path / "a.zip", csv_bytes(valid_rows()))
    first = import_zip(db_conninfo, first_zip, activate=True)
    other = [
        ["131000009", "OTRA SRL", "COMERCIO", "01/01/2011", "ACTIVO", "NORMAL"],
        ["131000008", "MAS SRL", "COMERCIO", "01/01/2011", "ACTIVO", "NORMAL"],
        ["131000007", "TER SRL", "COMERCIO", "01/01/2011", "ACTIVO", "NORMAL"],
    ]
    second_zip = write_zip(tmp_path / "b.zip", csv_bytes(other))
    failed = import_zip(db_conninfo, second_zip, activate=True, fail_at="before_activate")
    assert failed.state == "failed"
    assert _count(
        db_conninfo,
        "SELECT count(*) FROM dgii_rnc_version WHERE state = 'active' AND id = %s",
        (first.version_id,),
    ) == 1
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version WHERE state = 'active'") == 1


def test_failure_during_activate_rolls_back(db_conninfo, tmp_path):
    first_zip = write_zip(tmp_path / "a2.zip", csv_bytes(valid_rows()))
    first = import_zip(db_conninfo, first_zip, activate=True)
    other = [
        ["131000019", "OTRA2 SRL", "COMERCIO", "01/01/2011", "ACTIVO", "NORMAL"],
        ["131000018", "MAS2 SRL", "COMERCIO", "01/01/2011", "ACTIVO", "NORMAL"],
        ["131000017", "TER2 SRL", "COMERCIO", "01/01/2011", "ACTIVO", "NORMAL"],
    ]
    second_zip = write_zip(tmp_path / "b2.zip", csv_bytes(other))
    failed = import_zip(db_conninfo, second_zip, activate=True, fail_at="during_activate")
    assert failed.state == "failed"
    assert _count(
        db_conninfo,
        "SELECT id FROM dgii_rnc_version WHERE state = 'active'",
    ) == first.version_id
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version") == 1


def test_previous_version_is_kept_and_restored(db_conninfo, tmp_path):
    first_zip = write_zip(tmp_path / "v1.zip", csv_bytes(valid_rows()))
    first = import_zip(db_conninfo, first_zip, activate=True)
    other = [
        ["131000029", "NUEVA SRL", "COMERCIO", "01/01/2012", "ACTIVO", "NORMAL"],
        ["131000028", "NUEVA2 SRL", "COMERCIO", "01/01/2012", "ACTIVO", "NORMAL"],
        ["131000027", "NUEVA3 SRL", "COMERCIO", "01/01/2012", "ACTIVO", "NORMAL"],
    ]
    second_zip = write_zip(tmp_path / "v2.zip", csv_bytes(other))
    second = import_zip(db_conninfo, second_zip, activate=True)
    assert second.state == "success"
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version WHERE state = 'previous'") == 1
    restored = restore_previous(db_conninfo)
    assert restored == first.version_id
    assert _count(
        db_conninfo,
        "SELECT id FROM dgii_rnc_version WHERE state = 'active'",
    ) == first.version_id


def test_concurrent_import_is_skipped(db_conninfo, tmp_path):
    path = write_zip(tmp_path / "lock.zip", csv_bytes(valid_rows()))
    with connect(db_conninfo) as holder:
        holder.autocommit = True
        with holder.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (IMPORT_LOCK_KEY,))
        try:
            result = import_zip(db_conninfo, path, activate=True)
            assert result.state == "skipped"
        finally:
            with holder.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (IMPORT_LOCK_KEY,))


def test_two_threads_only_one_active(db_conninfo, tmp_path):
    zip_a = write_zip(tmp_path / "ta.zip", csv_bytes(valid_rows()))
    other = [
        ["131000039", "THR SRL", "COMERCIO", "01/01/2013", "ACTIVO", "NORMAL"],
        ["131000038", "THR2 SRL", "COMERCIO", "01/01/2013", "ACTIVO", "NORMAL"],
        ["131000037", "THR3 SRL", "COMERCIO", "01/01/2013", "ACTIVO", "NORMAL"],
    ]
    zip_b = write_zip(tmp_path / "tb.zip", csv_bytes(other))
    barrier = threading.Barrier(2)
    results = []

    def worker(path):
        barrier.wait(timeout=10)
        results.append(import_zip(db_conninfo, path, activate=True))

    threads = [
        threading.Thread(target=worker, args=(zip_a,)),
        threading.Thread(target=worker, args=(zip_b,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    states = sorted(item.state for item in results)
    assert "success" in states
    assert states.count("success") >= 1
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version WHERE state = 'active'") == 1


def test_restart_after_import_stays_active(db_conninfo, tmp_path, monkeypatch):
    path = write_zip(tmp_path / "rst.zip", csv_bytes(valid_rows()))
    result = import_zip(db_conninfo, path, activate=True)
    assert result.state == "success"
    settings = _settings(db_conninfo, monkeypatch)
    httpd = make_server(settings)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = httpd.server_address[:2]
        conn = HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/health/ready")
        ready = json.loads(conn.getresponse().read().decode("utf-8"))
        assert ready["status"] == "ok"
        assert ready["registry"] == "active"
        conn.close()
    finally:
        httpd.shutdown()
        httpd.server_close()


def _other_rows(prefix):
    return [
        ["1310000%s9" % prefix, "NUEVA %s SRL" % prefix, "COMERCIO", "01/01/2012", "ACTIVO", "NORMAL"],
        ["1310000%s8" % prefix, "NUEVA2 %s SRL" % prefix, "COMERCIO", "01/01/2012", "ACTIVO", "NORMAL"],
        ["1310000%s7" % prefix, "NUEVA3 %s SRL" % prefix, "COMERCIO", "01/01/2012", "ACTIVO", "NORMAL"],
    ]


def test_sha_active_activate_is_unchanged(db_conninfo, tmp_path):
    path = write_zip(tmp_path / "active.zip", csv_bytes(valid_rows()))
    first = import_zip(db_conninfo, path, activate=True)
    second = import_zip(db_conninfo, path, activate=True)
    assert first.state == "success"
    assert second.state == "unchanged"
    assert "already the active version" in second.details
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version") == 1
    assert _count(db_conninfo, "SELECT state FROM dgii_rnc_version") == "active"


def test_sha_staging_activate_promotes(db_conninfo, tmp_path):
    path = write_zip(tmp_path / "stg.zip", csv_bytes(valid_rows()))
    staged = import_zip(db_conninfo, path, activate=False)
    assert staged.state == "success"
    assert _count(db_conninfo, "SELECT state FROM dgii_rnc_version") == "staging"
    activated = import_zip(db_conninfo, path, activate=True)
    assert activated.state == "success"
    assert activated.version_id == staged.version_id
    assert "activated previously staged" in activated.details
    assert _count(db_conninfo, "SELECT state FROM dgii_rnc_version") == "active"


def test_sha_previous_activate_does_not_restore(db_conninfo, tmp_path):
    first_zip = write_zip(tmp_path / "prev1.zip", csv_bytes(valid_rows()))
    first = import_zip(db_conninfo, first_zip, activate=True)
    second_zip = write_zip(tmp_path / "prev2.zip", csv_bytes(_other_rows("4")))
    second = import_zip(db_conninfo, second_zip, activate=True)
    assert second.state == "success"
    reused = import_zip(db_conninfo, first_zip, activate=True)
    assert reused.state == "unchanged"
    assert reused.version_id == first.version_id
    assert "previous version" in reused.details
    assert "restore-previous" in reused.details
    assert _count(db_conninfo, "SELECT id FROM dgii_rnc_version WHERE state = 'active'") == second.version_id
    assert _count(
        db_conninfo,
        "SELECT state FROM dgii_rnc_version WHERE id = %s",
        (first.version_id,),
    ) == "previous"
    restored = restore_previous(db_conninfo)
    assert restored == first.version_id


def test_staging_row_mismatch_rejects_and_keeps_active(db_conninfo, tmp_path):
    first_zip = write_zip(tmp_path / "keep.zip", csv_bytes(valid_rows()))
    first = import_zip(db_conninfo, first_zip, activate=True)
    staged_zip = write_zip(tmp_path / "mismatch.zip", csv_bytes(_other_rows("5")))
    staged = import_zip(db_conninfo, staged_zip, activate=False)
    recorded = _count(
        db_conninfo,
        "SELECT record_count FROM dgii_rnc_version WHERE id = %s",
        (staged.version_id,),
    )
    with connect(db_conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM dgii_rnc
                 WHERE id = (
                    SELECT id FROM dgii_rnc
                     WHERE version_id = %s
                     LIMIT 1
                 )
                """,
                (staged.version_id,),
            )
        conn.commit()
    failed = import_zip(db_conninfo, staged_zip, activate=True)
    assert failed.state == "failed"
    assert "record_count" in failed.error
    assert _count(
        db_conninfo,
        "SELECT record_count FROM dgii_rnc_version WHERE id = %s",
        (staged.version_id,),
    ) == recorded
    assert _count(
        db_conninfo,
        "SELECT state FROM dgii_rnc_version WHERE id = %s",
        (staged.version_id,),
    ) == "staging"
    assert _count(
        db_conninfo,
        "SELECT id FROM dgii_rnc_version WHERE state = 'active'",
    ) == first.version_id


def test_staging_activate_rechecks_min_records(db_conninfo, tmp_path):
    path = write_zip(tmp_path / "min.zip", csv_bytes(valid_rows()))
    staged = import_zip(db_conninfo, path, activate=False)
    failed = import_zip(
        db_conninfo,
        path,
        activate=True,
        limits=ImportLimits(min_records=1000),
    )
    assert failed.state == "failed"
    assert _count(
        db_conninfo,
        "SELECT state FROM dgii_rnc_version WHERE id = %s",
        (staged.version_id,),
    ) == "staging"
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version WHERE state = 'active'") == 0


def test_dry_run_does_not_persist(db_conninfo, tmp_path):
    path = write_zip(tmp_path / "dry.zip", csv_bytes(valid_rows()))
    result = import_zip(db_conninfo, path, activate=False, persist=False)
    assert result.state == "success"
    assert result.accepted_count == 3
    assert "no persistent writes" in result.details
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version") == 0
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc") == 0
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_import_run") == 0


def test_dry_run_revalidates_existing_sha_without_writes(db_conninfo, tmp_path):
    path = write_zip(tmp_path / "again.zip", csv_bytes(valid_rows()))
    imported = import_zip(db_conninfo, path, activate=True)
    assert imported.state == "success"
    versions = _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version")
    rows = _count(db_conninfo, "SELECT count(*) FROM dgii_rnc")
    runs = _count(db_conninfo, "SELECT count(*) FROM dgii_import_run")
    active_id = _count(db_conninfo, "SELECT id FROM dgii_rnc_version WHERE state = 'active'")
    recorded = _count(
        db_conninfo,
        "SELECT record_count FROM dgii_rnc_version WHERE id = %s",
        (active_id,),
    )
    dry = import_zip(db_conninfo, path, persist=False)
    assert dry.state == "success"
    assert dry.accepted_count == 3
    assert dry.total_rows == 3
    assert "ZIP and CSV validated" in dry.details
    assert "already the active version" not in dry.details
    assert dry.version_id is None
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version") == versions
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc") == rows
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_import_run") == runs
    assert _count(db_conninfo, "SELECT id FROM dgii_rnc_version WHERE state = 'active'") == active_id
    assert _count(
        db_conninfo,
        "SELECT record_count FROM dgii_rnc_version WHERE id = %s",
        (active_id,),
    ) == recorded
    refused = import_zip(
        db_conninfo,
        path,
        persist=False,
        limits=ImportLimits(min_records=1000),
    )
    assert refused.state == "failed"
    assert "integrity" in refused.error
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version") == versions
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc") == rows
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_import_run") == runs
    assert _count(db_conninfo, "SELECT id FROM dgii_rnc_version WHERE state = 'active'") == active_id


def test_restore_times_out_when_import_lock_is_held(db_conninfo, tmp_path):
    first_zip = write_zip(tmp_path / "r1.zip", csv_bytes(valid_rows()))
    first = import_zip(db_conninfo, first_zip, activate=True)
    second_zip = write_zip(tmp_path / "r2.zip", csv_bytes(_other_rows("6")))
    second = import_zip(db_conninfo, second_zip, activate=True)
    path = write_zip(tmp_path / "r3.zip", csv_bytes(_other_rows("7")))
    with connect(db_conninfo) as holder:
        holder.autocommit = True
        with holder.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (IMPORT_LOCK_KEY,))
        try:
            skipped = import_zip(db_conninfo, path, activate=True)
            assert skipped.state == "skipped"
            with pytest.raises(RegistryImportError, match="another import is running"):
                restore_previous(db_conninfo, lock_timeout_ms=1000)
            assert _count(
                db_conninfo,
                "SELECT id FROM dgii_rnc_version WHERE state = 'active'",
            ) == second.version_id
            assert _count(
                db_conninfo,
                "SELECT state FROM dgii_rnc_version WHERE id = %s",
                (first.version_id,),
            ) == "previous"
        finally:
            with holder.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(%s)", (IMPORT_LOCK_KEY,))


def test_import_aborts_when_decompressed_bytes_exceed_limit(db_conninfo, tmp_path, monkeypatch):
    payload = csv_bytes(valid_rows())
    assert len(payload) > 64
    path = write_zip(tmp_path / "cap.zip", payload)
    real_infolist = zipfile.ZipFile.infolist

    def lying_infolist(self):
        copies = []
        for member in real_infolist(self):
            clone = copy.copy(member)
            clone.file_size = 40
            copies.append(clone)
        return copies

    monkeypatch.setattr(zipfile.ZipFile, "infolist", lying_infolist)
    monkeypatch.setattr(zipfile.ZipFile, "testzip", lambda self: None)
    result = import_zip(
        db_conninfo,
        path,
        activate=True,
        limits=ImportLimits(
            zip=ZipLimits(max_uncompressed_bytes=64, max_compression_ratio=1000.0)
        ),
    )
    assert result.state == "failed"
    assert "uncompressed" in result.error
    assert _count(db_conninfo, "SELECT count(*) FROM dgii_rnc_version") == 0
