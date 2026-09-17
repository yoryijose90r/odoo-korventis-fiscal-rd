"""Local ZIP importer. Does not download, does not write Odoo tables."""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .archive import ArchiveError, ZipLimits, inspect_zip
from .migrate import connect
from .normalize import has_unsafe_control_characters, normalize_header, normalize_name


_logger = logging.getLogger(__name__)

IMPORT_LOCK_KEY = 1262760520
MAX_LOGGED_ISSUES = 50
COPY_BATCH_SIZE = 500

CSV_HEADERS = [
    "RNC",
    "RAZÓN SOCIAL",
    "ACTIVIDAD ECONÓMICA",
    "FECHA DE INICIO OPERACIONES",
    "ESTADO",
    "RÉGIMEN DE PAGO",
]

RNC_LENGTHS = (9, 11)


class RegistryImportError(Exception):
    """Import refused. Message must not include secrets, tokens or RNCs."""


@dataclass(frozen=True)
class ImportLimits:
    zip: ZipLimits = field(default_factory=ZipLimits)
    min_records: int = 1
    max_reject_ratio: float = 0.001
    volume_ratio_min: float = 0.70
    volume_ratio_max: float = 1.30
    volume_ratio_floor: int = 1000


@dataclass
class ImportResult:
    state: str
    version_id: int = None
    archive_sha256: str = None
    total_rows: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    warning_count: int = 0
    duplicate_count: int = 0
    details: str = ""
    error: str = ""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_zip(
    conninfo,
    zip_path,
    source_label="local-zip",
    activate=False,
    limits=None,
    fail_at=None,
):
    limits = limits or ImportLimits()
    path = Path(zip_path)
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise RegistryImportError("import source must be an existing .zip file")
    conn = connect(conninfo)
    conn.autocommit = False
    locked = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (IMPORT_LOCK_KEY,))
            locked = bool(cur.fetchone()[0])
        if not locked:
            return ImportResult(state="skipped", error="another import is running")
        conn.commit()
        return _import_locked(
            conn, path, source_label, activate, limits, fail_at=fail_at
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        if locked:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (IMPORT_LOCK_KEY,))
                conn.commit()
            except Exception:
                _logger.error("import unlock failed (%s)", "OperationalError")
        conn.close()


def restore_previous(conninfo):
    conn = connect(conninfo)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (IMPORT_LOCK_KEY,))
            cur.execute(
                """
                SELECT id FROM dgii_rnc_version
                 WHERE state = 'active'
                 FOR UPDATE
                """
            )
            active = cur.fetchall()
            if len(active) != 1:
                raise RegistryImportError("restore requires exactly one active version")
            cur.execute(
                """
                SELECT id FROM dgii_rnc_version
                 WHERE state = 'previous'
                 ORDER BY activated_at DESC NULLS LAST, imported_at DESC, id DESC
                 LIMIT 1
                 FOR UPDATE
                """
            )
            previous = cur.fetchone()
            if not previous:
                raise RegistryImportError("no previous version to restore")
            cur.execute(
                """
                UPDATE dgii_rnc_version
                   SET state = 'previous'
                 WHERE id = %s
                """,
                (active[0][0],),
            )
            cur.execute(
                """
                UPDATE dgii_rnc_version
                   SET state = 'active',
                       activated_at = now()
                 WHERE id = %s
                   AND record_count > 0
                """,
                (previous[0],),
            )
            if cur.rowcount != 1:
                raise RegistryImportError("previous version cannot be activated")
        conn.commit()
        return previous[0]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _import_locked(conn, path, source_label, activate, limits, fail_at=None):
    started = datetime.datetime.now(datetime.timezone.utc)
    run_id = None
    try:
        run_id = _insert_run(conn, source_label, started)
        member = inspect_zip(path, limits.zip)
        archive_hash = sha256_file(path)
        existing = _version_by_sha(conn, archive_hash)
        if existing:
            return _reuse_existing(conn, run_id, existing, archive_hash, activate)
        stats = {
            "total_rows": 0,
            "accepted": 0,
            "rejected": 0,
            "warnings": 0,
            "issues": [],
        }
        imported_at = datetime.datetime.now(datetime.timezone.utc)
        with conn.cursor() as cur:
            _create_stage(cur)
            _stream_csv(cur, path, member.filename, imported_at, stats)
            _validate_stage(cur, stats, limits)
            version_id = _insert_version(
                cur,
                source_label,
                member.filename,
                path.stat().st_size,
                archive_hash,
                imported_at,
                stats,
            )
            _copy_stage_to_version(cur, version_id, stats["accepted"])
            if fail_at == "before_activate":
                raise RegistryImportError("injected failure before activation")
            if activate:
                _activate(cur, version_id)
                if fail_at == "during_activate":
                    raise RegistryImportError("injected failure during activation")
        result = ImportResult(
            state="success",
            version_id=version_id,
            archive_sha256=archive_hash,
            total_rows=stats["total_rows"],
            accepted_count=stats["accepted"],
            rejected_count=stats["rejected"],
            warning_count=stats["warnings"],
            duplicate_count=stats.get("duplicates", 0),
            details=_details(stats, activate),
        )
        _finish_run(conn, run_id, result, version_id)
        conn.commit()
        return result
    except (ArchiveError, RegistryImportError, csv.Error, UnicodeError) as exc:
        conn.rollback()
        result = ImportResult(state="failed", error=_safe_error(exc))
        if run_id:
            try:
                _finish_run(conn, run_id, result, None)
                conn.commit()
            except Exception:
                conn.rollback()
        return result
    except Exception:
        conn.rollback()
        _logger.error("import failed (%s)", "unexpected")
        result = ImportResult(state="failed", error="import failed")
        if run_id:
            try:
                _finish_run(conn, run_id, result, None)
                conn.commit()
            except Exception:
                conn.rollback()
        return result


def _safe_error(exc):
    if isinstance(exc, csv.Error):
        return "CSV is truncated or invalid"
    if isinstance(exc, UnicodeError):
        return "CSV encoding is invalid"
    return str(exc)[:300]


def _reuse_existing(conn, run_id, existing, archive_hash, activate):
    if activate and existing["state"] == "staging" and existing["record_count"] > 0:
        with conn.cursor() as cur:
            _activate(cur, existing["id"])
        result = ImportResult(
            state="success",
            version_id=existing["id"],
            archive_sha256=archive_hash,
            total_rows=existing["record_count"],
            accepted_count=existing["record_count"],
            rejected_count=existing["rejected_count"],
            warning_count=existing["warning_count"],
            details="activated previously staged archive SHA-256",
        )
        _finish_run(conn, run_id, result, existing["id"])
        conn.commit()
        return result
    result = ImportResult(
        state="unchanged",
        version_id=existing["id"],
        archive_sha256=archive_hash,
        total_rows=existing["record_count"],
        accepted_count=existing["record_count"],
        rejected_count=existing["rejected_count"],
        warning_count=existing["warning_count"],
        details="archive SHA-256 already imported",
    )
    _finish_run(conn, run_id, result, existing["id"])
    conn.commit()
    return result


def _insert_run(conn, source_label, started):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dgii_import_run (name, state, source_url, started_at)
            VALUES (%s, 'running', %s, %s)
            RETURNING id
            """,
            (source_label[:120], source_label[:500], started),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def _finish_run(conn, run_id, result, version_id):
    finished = datetime.datetime.now(datetime.timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dgii_import_run
               SET state = %s,
                   finished_at = %s,
                   archive_sha256 = %s,
                   version_id = %s,
                   total_rows = %s,
                   accepted_count = %s,
                   rejected_count = %s,
                   warning_count = %s,
                   duplicate_count = %s,
                   details = %s,
                   error_message = %s
             WHERE id = %s
            """,
            (
                result.state,
                finished,
                result.archive_sha256,
                version_id,
                result.total_rows,
                result.accepted_count,
                result.rejected_count,
                result.warning_count,
                result.duplicate_count,
                result.details[:4000] if result.details else None,
                (result.error or None),
                run_id,
            ),
        )


def _version_by_sha(conn, archive_hash):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, state, record_count, rejected_count, warning_count
              FROM dgii_rnc_version
             WHERE archive_sha256 = %s
            """,
            (archive_hash,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "state": row[1],
        "record_count": row[2],
        "rejected_count": row[3],
        "warning_count": row[4],
    }


def _create_stage(cur):
    cur.execute("DROP TABLE IF EXISTS dgii_import_stage")
    cur.execute(
        """
        CREATE TEMP TABLE dgii_import_stage (
            source_line bigint NOT NULL,
            rnc text NOT NULL,
            rnc_normalizado text NOT NULL,
            razon_social text NOT NULL,
            razon_social_normalizada text NOT NULL,
            actividad_economica text,
            fecha_inicio_operaciones date,
            estado text NOT NULL,
            regimen_pago text NOT NULL,
            fecha_importacion timestamptz NOT NULL
        ) ON COMMIT DROP
        """
    )


def _open_csv_text(binary):
    preview = binary.read(8)
    binary.seek(0)
    if preview.startswith(b"\xef\xbb\xbf"):
        return io.TextIOWrapper(binary, encoding="utf-8-sig", errors="strict", newline="")
    return io.TextIOWrapper(binary, encoding="latin-1", errors="strict", newline="")


def _stream_csv(cur, path, member_name, imported_at, stats):
    batch = []
    with zipfile.ZipFile(path) as archive, archive.open(member_name) as binary:
        with _open_csv_text(binary) as text:
            reader = csv.reader(text, dialect="excel", strict=True)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise RegistryImportError("CSV is empty") from exc
            normalized = [normalize_header(value) for value in header]
            expected = [normalize_header(value) for value in CSV_HEADERS]
            if normalized != expected:
                raise RegistryImportError("CSV headers do not match the DGII layout")
            for row in reader:
                line_num = reader.line_num
                if not row or not any((cell or "").strip() for cell in row):
                    continue
                stats["total_rows"] += 1
                parsed = _validate_row(line_num, row, stats)
                if not parsed:
                    continue
                batch.append(
                    (
                        line_num,
                        parsed["rnc"],
                        parsed["rnc_normalizado"],
                        parsed["razon_social"],
                        parsed["razon_social_normalizada"],
                        parsed["actividad_economica"],
                        parsed["fecha_inicio_operaciones"],
                        parsed["estado"],
                        parsed["regimen_pago"],
                        imported_at,
                    )
                )
                stats["accepted"] += 1
                if len(batch) >= COPY_BATCH_SIZE:
                    _copy_batch(cur, batch)
                    batch = []
    if batch:
        _copy_batch(cur, batch)


def _copy_batch(cur, batch):
    with cur.copy(
        """
        COPY dgii_import_stage (
            source_line, rnc, rnc_normalizado, razon_social,
            razon_social_normalizada, actividad_economica,
            fecha_inicio_operaciones, estado, regimen_pago,
            fecha_importacion
        ) FROM STDIN
        """
    ) as copy:
        for row in batch:
            copy.write_row(row)


def _validate_row(line_num, row, stats):
    if len(row) != 6:
        _reject(stats, line_num, "column count is not 6")
        return None
    values = [(value or "").strip() for value in row]
    rnc, name, activity, date_value, status, regime = values
    if has_unsafe_control_characters("".join(values)):
        _reject(stats, line_num, "row contains unsafe control characters")
        return None
    if not rnc.isdigit() or len(rnc) not in RNC_LENGTHS:
        _reject(stats, line_num, "RNC is malformed")
        return None
    if not name or not status or not regime:
        _reject(stats, line_num, "required fields are missing")
        return None
    normalized_name = normalize_name(name)
    if not normalized_name:
        _reject(stats, line_num, "name cannot be normalized")
        return None
    parsed_date = None
    if date_value:
        try:
            parsed_date = datetime.datetime.strptime(date_value, "%d/%m/%Y").date()
        except ValueError:
            stats["warnings"] += 1
            if len(stats["issues"]) < MAX_LOGGED_ISSUES:
                stats["issues"].append({"line": line_num, "kind": "warning", "reason": "invalid date"})
    return {
        "rnc": rnc,
        "rnc_normalizado": rnc,
        "razon_social": name,
        "razon_social_normalizada": normalized_name,
        "actividad_economica": activity or None,
        "fecha_inicio_operaciones": parsed_date,
        "estado": status,
        "regimen_pago": regime,
    }


def _reject(stats, line_num, reason):
    stats["rejected"] += 1
    if len(stats["issues"]) < MAX_LOGGED_ISSUES:
        stats["issues"].append({"line": line_num, "kind": "reject", "reason": reason})


def _validate_stage(cur, stats, limits):
    if stats["accepted"] < limits.min_records or stats["accepted"] <= 0:
        raise RegistryImportError("accepted row count is below the integrity threshold")
    if stats["total_rows"] <= 0:
        raise RegistryImportError("CSV has no data rows")
    max_rejected = int(stats["total_rows"] * limits.max_reject_ratio)
    if stats["rejected"] > max_rejected:
        raise RegistryImportError("rejected row count exceeds the integrity threshold")
    cur.execute(
        """
        SELECT count(*) - count(DISTINCT rnc_normalizado)
          FROM dgii_import_stage
        """
    )
    duplicates = int(cur.fetchone()[0])
    stats["duplicates"] = duplicates
    if duplicates:
        raise RegistryImportError("staging contains duplicate normalized RNCs")
    cur.execute("SELECT count(*) FROM dgii_import_stage")
    staged = int(cur.fetchone()[0])
    if staged != stats["accepted"]:
        raise RegistryImportError("staging row count does not match accepted rows")
    cur.execute(
        """
        SELECT id, record_count
          FROM dgii_rnc_version
         WHERE state = 'active'
        """
    )
    active = cur.fetchone()
    if active and active[1] >= limits.volume_ratio_floor:
        ratio = stats["accepted"] / float(active[1])
        if not limits.volume_ratio_min <= ratio <= limits.volume_ratio_max:
            raise RegistryImportError("volume differs too much from the active version")


def _insert_version(cur, source_label, filename, archive_size, archive_hash, imported_at, stats):
    cur.execute(
        """
        INSERT INTO dgii_rnc_version (
            name, state, source_url, source_filename, archive_size,
            archive_sha256, imported_at, record_count, rejected_count, warning_count
        ) VALUES (
            %s, 'staging', %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        RETURNING id
        """,
        (
            filename,
            source_label[:500],
            filename,
            archive_size,
            archive_hash,
            imported_at,
            stats["accepted"],
            stats["rejected"],
            stats["warnings"],
        ),
    )
    return cur.fetchone()[0]


def _copy_stage_to_version(cur, version_id, expected):
    cur.execute(
        """
        INSERT INTO dgii_rnc (
            version_id, rnc, rnc_normalizado, razon_social,
            razon_social_normalizada, actividad_economica,
            fecha_inicio_operaciones, estado, regimen_pago, fecha_importacion
        )
        SELECT %s, rnc, rnc_normalizado, razon_social,
               razon_social_normalizada, actividad_economica,
               fecha_inicio_operaciones, estado, regimen_pago, fecha_importacion
          FROM dgii_import_stage
        """,
        (version_id,),
    )
    if cur.rowcount != expected:
        raise RegistryImportError("copy from staging was incomplete")


def _activate(cur, version_id):
    cur.execute(
        """
        SELECT count(*) FROM dgii_rnc WHERE version_id = %s
        """,
        (version_id,),
    )
    rows = int(cur.fetchone()[0])
    if rows <= 0:
        raise RegistryImportError("refusing to activate an empty version")
    cur.execute(
        """
        UPDATE dgii_rnc_version
           SET record_count = %s
         WHERE id = %s AND state = 'staging'
        """,
        (rows, version_id),
    )
    cur.execute(
        """
        UPDATE dgii_rnc_version
           SET state = 'previous'
         WHERE state = 'active'
           AND id <> %s
        """,
        (version_id,),
    )
    cur.execute(
        """
        UPDATE dgii_rnc_version
           SET state = 'active',
               activated_at = now()
         WHERE id = %s
           AND state = 'staging'
           AND record_count > 0
        """,
        (version_id,),
    )
    if cur.rowcount != 1:
        raise RegistryImportError("activation did not update the staging version")
    cur.execute("SELECT count(*) FROM dgii_rnc_version WHERE state = 'active'")
    if int(cur.fetchone()[0]) != 1:
        raise RegistryImportError("activation would leave an invalid active set")


def _details(stats, activate):
    return json.dumps(
        {
            "activate": bool(activate),
            "issues": stats["issues"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
