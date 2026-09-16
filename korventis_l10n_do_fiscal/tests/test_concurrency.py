"""Concurrency tests.

Safe suite (`TestSequenceAllocationSafe`): one transaction, rolled back.
Safe on `korventis` and `baruchcafe`.

Isolated suite (`TestConcurrentSequenceAllocationIsolated`): two real
PostgreSQL backends. Tagged `-standard` (excluded from default `--test-enable`).

Odoo 18 ``Registry.cursor()`` is not an independent session when the registry
is in test mode: it returns ``TestCursor`` wrapping ``registry.test_cr`` and
serializes on ``test_lock``. This test opens backends with
``odoo.sql_db.db_connect(dbname).cursor()``, which always constructs
``sql_db.Cursor`` (real COMMIT) and never ``TestCursor``.

Worker sessions set local ``lock_timeout`` / ``statement_timeout`` so a hang
becomes a PostgreSQL exception (test FAIL with diagnosis), not a stuck
non-daemon thread. The Python deadline is a last resort.

Creating ``api.Environment`` in a worker thread calls ``Registry(dbname)``,
which acquires ``Registry._lock``. ``TransactionCase`` can hold that RLock
while ``join()`` runs (Odoo 18 / PR 161438). This test patches
``Registry._lock`` with Odoo's ``DummyRLock`` for the method duration via
``BaseCase.patch`` (same pattern as ``addons/auth_ldap/tests/test_auth_ldap.py``).
It does **not** call ``enter_test_mode`` (that would wrap ``Registry.cursor()``
in ``TestCursor``). Workers still use ``db_connect``.

XML id ``base.main_company`` is the committed default company in Odoo 18
(``odoo/addons/base/data/res_company_data.xml``). The fixture sequence uses a
sentinel validity window so leftover cleanup cannot match a legitimate range
by number bounds alone.

Disposable DB only (e.g. `korventis_fiscal_test`):

    odoo-bin -d korventis_fiscal_test --test-enable --test-tags=korventis_pg_lock --stop-after-init

NEVER run `korventis_pg_lock` on `korventis` or `baruchcafe`.
"""

import sys
import threading
import time
import traceback

from odoo import api, fields, SUPERUSER_ID
from odoo.modules.registry import DummyRLock, Registry
from odoo.sql_db import Cursor, db_connect
from odoo.tests import TransactionCase, tagged

from odoo.addons.korventis_l10n_do_fiscal.services.ncf_service import NcfService
from odoo.addons.korventis_l10n_do_fiscal.tests.common import KorventisFiscalCommon

_LOCK_RANGE_START = 8000000001
_LOCK_RANGE_END = 8000000099
_FORBIDDEN_DBS = frozenset({"korventis", "baruchcafe"})
_DISPOSABLE_DB_EXACT = "korventis_fiscal_test"
_BARRIER_TIMEOUT_SECONDS = 5.0
_WORKER_LOCK_TIMEOUT = "8s"
_WORKER_STATEMENT_TIMEOUT = "12s"
_WORKER_DEADLINE_SECONDS = 18.0
_CLEANUP_LOCK_TIMEOUT = "5s"
# Fingerprints of this test's sequence only (not a production validity window).
# OLD: leftover from 18.0.1.2.2 (invalid for allocate() in 2026).
# NEW: valid throughout the test without using "today".
_FIXTURE_VALID_FROM_OLD = fields.Date.to_date("2099-01-01")
_FIXTURE_VALID_UNTIL_OLD = fields.Date.to_date("2099-12-31")
_FIXTURE_VALID_FROM = fields.Date.to_date("2000-01-01")
_FIXTURE_VALID_UNTIL = fields.Date.to_date("2099-12-31")
_EXPECTED_FISCAL_NUMBERS = frozenset(
    {
        "E32%010d" % _LOCK_RANGE_START,
        "E32%010d" % (_LOCK_RANGE_START + 1),
    }
)


def _open_real_cursor(db_name):
    """Return a real ``sql_db.Cursor`` (independent PostgreSQL backend).

    Does not call ``Registry.cursor()``, so it cannot become ``TestCursor``.
    """
    cr = db_connect(db_name).cursor()
    if type(cr) is not Cursor:
        try:
            cr.close()
        except Exception:  # noqa: BLE001
            pass
        raise AssertionError(
            "db_connect().cursor() returned %s; expected odoo.sql_db.Cursor "
            "(not TestCursor)." % type(cr)
        )
    return cr


class _MarkerLog:
    def __init__(self):
        self._lock = threading.Lock()
        self._events = []
        self._t0 = time.monotonic()

    def mark(self, worker, stage, extra=""):
        elapsed = time.monotonic() - self._t0
        record = (elapsed, worker, stage, extra)
        with self._lock:
            self._events.append(record)
        line = "korventis_pg_lock marker t=%.3fs worker=%s stage=%s" % (
            elapsed,
            worker,
            stage,
        )
        if extra:
            line = "%s %s" % (line, extra)
        print(line, file=sys.stderr, flush=True)

    def dump(self):
        with self._lock:
            events = list(self._events)
        if not events:
            return "(no markers recorded)"
        lines = []
        for elapsed, worker, stage, extra in events:
            suffix = " %s" % extra if extra else ""
            lines.append("%.3fs %s %s%s" % (elapsed, worker, stage, suffix))
        return "\n".join(lines)

    def has_stage(self, worker, stage):
        with self._lock:
            return any(
                item[1] == worker and item[2] == stage for item in self._events
            )


@tagged("post_install", "-at_install")
class TestSequenceAllocationSafe(KorventisFiscalCommon):
    def test_sequence_allocation_same_cursor(self):
        service = NcfService(self.env)
        seen = set()
        for _ in range(5):
            number, _raw = service.allocate(self.sequence_e32, company=self.company)
            self.assertNotIn(number, seen)
            seen.add(number)
            self.assertEqual(len(number), 13)
        self.assertEqual(len(seen), 5)


@tagged("post_install", "-at_install", "-standard", "korventis_pg_lock")
class TestConcurrentSequenceAllocationIsolated(TransactionCase):
    """Keep TransactionCase for Odoo 18 discovery/tagging and ``self.registry``.

    The class transaction is unused for fixture writes. Sequence setup, workers,
    verify and cleanup use ``db_connect`` only. ``self.env`` is read-only here
    (dbname / diagnostic pid / ``registry.test_cr``).
    """

    def _assert_disposable_lock_db(self, db_name):
        if db_name in _FORBIDDEN_DBS:
            raise AssertionError(
                "korventis_pg_lock must never run on database %r." % db_name
            )
        if db_name != _DISPOSABLE_DB_EXACT and not db_name.endswith("_fiscal_test"):
            raise AssertionError(
                "korventis_pg_lock requires disposable DB %r or a name ending in "
                "'_fiscal_test'. Got %r." % (_DISPOSABLE_DB_EXACT, db_name)
            )

    def _fixture_domain(self, company_id, type_id, valid_from, valid_until):
        return [
            ("company_id", "=", company_id),
            ("document_type_id", "=", type_id),
            ("prefix", "=", "E32"),
            ("range_start", "=", _LOCK_RANGE_START),
            ("range_end", "=", _LOCK_RANGE_END),
            ("valid_from", "=", valid_from),
            ("valid_until", "=", valid_until),
        ]

    def _clear_one_fingerprint(self, env, company_id, type_id, valid_from, valid_until):
        leftovers = env["korventis.fiscal.sequence"].search(
            self._fixture_domain(company_id, type_id, valid_from, valid_until)
        )
        if len(leftovers) > 1:
            raise AssertionError(
                "Fingerprint %s..%s matched %s sequences (ids=%s); refusing to delete."
                % (valid_from, valid_until, len(leftovers), leftovers.ids)
            )
        if not leftovers:
            return
        leftover = leftovers[0]
        docs = env["korventis.fiscal.document"].search_count(
            [("sequence_id", "=", leftover.id)]
        )
        if docs:
            raise AssertionError(
                "Fingerprint leftover sequence %s (%s..%s) has %s fiscal "
                "document(s); refusing to delete."
                % (leftover.id, valid_from, valid_until, docs)
            )
        # Disposable test DB only: product code intentionally prevents deleting
        # consumed range history. This uniquely fingerprinted fixture has no
        # fiscal documents and must not survive a committed concurrency test.
        env.cr.execute(
            "DELETE FROM korventis_fiscal_sequence WHERE id = %s",
            (leftover.id,),
        )
        env.invalidate_all()

    def _clear_fingerprint_leftover(self, env, company_id, type_id):
        """Remove OLD 18.0.1.2.2 leftover and any NEW fixture residue, separately."""
        for valid_from, valid_until in (
            (_FIXTURE_VALID_FROM_OLD, _FIXTURE_VALID_UNTIL_OLD),
            (_FIXTURE_VALID_FROM, _FIXTURE_VALID_UNTIL),
        ):
            self._clear_one_fingerprint(
                env, company_id, type_id, valid_from, valid_until
            )

    def _query_pg_activity(self, cr):
        cr.execute(
            """
            SELECT pid,
                   application_name,
                   usename,
                   state,
                   wait_event_type,
                   wait_event,
                   pg_blocking_pids(pid) AS blocked_by,
                   xact_start,
                   query_start,
                   left(query, 300) AS query
              FROM pg_stat_activity
             WHERE datname = current_database()
          ORDER BY xact_start NULLS LAST, pid
            """
        )
        cols = [item[0] for item in cr.description]
        return [dict(zip(cols, row)) for row in cr.fetchall()]

    def _query_pg_locks(self, cr):
        cr.execute(
            """
            SELECT l.pid,
                   l.locktype,
                   l.mode,
                   l.granted,
                   l.relation::regclass::text AS relation,
                   l.transactionid,
                   l.virtualxid,
                   a.wait_event,
                   a.state,
                   left(a.query, 200) AS query
              FROM pg_locks l
              JOIN pg_stat_activity a ON a.pid = l.pid
             WHERE a.datname = current_database()
          ORDER BY l.granted, l.pid, l.locktype
            """
        )
        cols = [item[0] for item in cr.description]
        return [dict(zip(cols, row)) for row in cr.fetchall()]

    def _format_rows(self, rows):
        if not rows:
            return "(no rows)"
        lines = []
        for row in rows:
            parts = ["%s=%s" % (key, row[key]) for key in row]
            lines.append("  " + "; ".join(parts))
        return "\n".join(lines)

    def _dump_pg_diagnosis(self, db_name, worker_pids, main_pid):
        parts = []
        cr = None
        try:
            cr = _open_real_cursor(db_name)
            cr.execute("SET application_name = %s", ("korventis_pg_lock_diag",))
            activity = self._query_pg_activity(cr)
            locks = self._query_pg_locks(cr)
            blockers = set()
            for row in activity:
                blocked_by = row.get("blocked_by") or []
                for pid in blocked_by:
                    blockers.add(pid)
            highlight = {
                "worker_pids": worker_pids,
                "main_test_pid": main_pid,
                "blocking_pids": sorted(blockers),
            }
            parts.extend(
                [
                    "pg diagnosis highlight: %s" % highlight,
                    "pg_stat_activity:",
                    self._format_rows(activity),
                    "pg_locks:",
                    self._format_rows(locks),
                ]
            )
        except Exception:  # noqa: BLE001
            parts.append("diagnostic_error: %s" % traceback.format_exc())
        finally:
            if cr is not None and not cr.closed:
                try:
                    cr.close()
                except Exception:  # noqa: BLE001
                    pass
        return "\n".join(parts) if parts else "(empty diagnosis)"

    def _active_backend_pids(self, db_name, pids):
        wanted = [pid for pid in pids if pid]
        if not wanted:
            return []
        cr = _open_real_cursor(db_name)
        try:
            cr.execute(
                """
                SELECT pid
                  FROM pg_stat_activity
                 WHERE datname = current_database()
                   AND pid = ANY(%s)
                """,
                (wanted,),
            )
            return [row[0] for row in cr.fetchall()]
        finally:
            cr.close()

    def _combine_errors(self, primary_error, cleanup_error):
        if primary_error and cleanup_error:
            return (
                "PRIMARY ERROR (original cause):\n%s\n\n"
                "CLEANUP ERROR (secondary; did not replace primary):\n%s"
                % (primary_error, cleanup_error)
            )
        return primary_error or cleanup_error

    def test_concurrent_sequence_allocation(self):
        db_name = self.env.cr.dbname
        self._assert_disposable_lock_db(db_name)
        markers = _MarkerLog()
        registry = self.registry
        test_mode = registry.test_cr is not None
        print(
            "korventis_pg_lock registry.test_cr is %s (in_test_mode=%s)"
            % (type(registry.test_cr).__name__ if test_mode else "None", test_mode),
            file=sys.stderr,
            flush=True,
        )

        self.env.cr.execute("SELECT pg_backend_pid()")
        main_pid = self.env.cr.fetchone()[0]
        print(
            "korventis_pg_lock main TransactionCase backend pid=%s" % main_pid,
            file=sys.stderr,
            flush=True,
        )

        seq_id = False
        results = []
        errors = []
        worker_pids = []
        result_lock = threading.Lock()
        barrier = threading.Barrier(2)
        primary_error = None
        cleanup_error = None
        diagnosis = ""

        setup_cr = _open_real_cursor(db_name)
        try:
            setup_cr.execute("SET application_name = %s", ("korventis_pg_lock_setup",))
            setup = api.Environment(setup_cr, SUPERUSER_ID, {})
            type_e32 = setup.ref("korventis_l10n_do_fiscal.document_type_e32")
            company = setup.ref("base.main_company")
            self.assertTrue(company.exists(), "XML id base.main_company is missing.")
            self._clear_fingerprint_leftover(setup, company.id, type_e32.id)
            seq = setup["korventis.fiscal.sequence"].create(
                {
                    "company_id": company.id,
                    "document_type_id": type_e32.id,
                    "prefix": "E32",
                    "range_start": _LOCK_RANGE_START,
                    "range_end": _LOCK_RANGE_END,
                    "next_number": _LOCK_RANGE_START,
                    "valid_from": _FIXTURE_VALID_FROM,
                    "valid_until": _FIXTURE_VALID_UNTIL,
                }
            )
            seq_id = seq.id
            company_id = company.id
            setup_cr.commit()
        finally:
            setup_cr.close()

        def worker(worker_name):
            cr = None
            try:
                markers.mark(worker_name, "started")
                barrier.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
                markers.mark(worker_name, "barrier_passed")
                cr = _open_real_cursor(db_name)
                cr.execute(
                    "SET application_name = %s",
                    ("korventis_pg_lock_%s" % worker_name,),
                )
                cr.execute("SELECT pg_backend_pid()")
                backend_pid = cr.fetchone()[0]
                with result_lock:
                    worker_pids.append(backend_pid)
                markers.mark(
                    worker_name,
                    "cursor_opened",
                    extra="pg_backend_pid=%s" % backend_pid,
                )
                cr.execute("SET lock_timeout = %s", (_WORKER_LOCK_TIMEOUT,))
                cr.execute("SET statement_timeout = %s", (_WORKER_STATEMENT_TIMEOUT,))
                markers.mark(worker_name, "timeouts_configured")
                markers.mark(worker_name, "before_env_create")
                env = api.Environment(cr, SUPERUSER_ID, {})
                markers.mark(worker_name, "env_created")
                sequence = env["korventis.fiscal.sequence"].browse(seq_id)
                company_rec = env["res.company"].browse(company_id)
                if not sequence.exists():
                    raise AssertionError(
                        "Worker %s: sequence %s is not visible." % (worker_name, seq_id)
                    )
                markers.mark(worker_name, "sequence_browsed")
                markers.mark(worker_name, "before_allocate")
                number, raw = NcfService(env).allocate(sequence, company=company_rec)
                markers.mark(
                    worker_name,
                    "after_allocate",
                    extra="raw=%s" % raw,
                )
                markers.mark(worker_name, "before_commit")
                cr.commit()
                markers.mark(worker_name, "after_commit")
                with result_lock:
                    results.append((number, raw))
                markers.mark(worker_name, "worker_done")
            except Exception as exc:  # noqa: BLE001
                tb = traceback.format_exc()
                markers.mark(
                    worker_name,
                    "worker_error",
                    extra="%s: %s" % (type(exc).__name__, exc),
                )
                with result_lock:
                    errors.append("%s\n%s" % (exc, tb))
                if cr is not None and not cr.closed:
                    try:
                        cr.rollback()
                    except Exception:  # noqa: BLE001
                        pass
            finally:
                if cr is not None and not cr.closed:
                    try:
                        cr.close()
                    except Exception:  # noqa: BLE001
                        pass

        # Odoo 18: Environment() -> Registry(dbname) takes Registry._lock.
        # TransactionCase can hold that RLock across join() (PR 161438).
        # DummyRLock is Odoo's official no-op lock (HttpCase.enter_test_mode and
        # auth_ldap tests). BaseCase.patch uses unittest.mock.patch.object and
        # addCleanup(stop), so the original RLock is restored even on failure.
        # This does not call enter_test_mode / TestCursor.
        self.patch(Registry, "_lock", DummyRLock())

        threads = [
            threading.Thread(
                target=worker,
                args=("A",),
                name="korventis-lock-A",
                daemon=False,
            ),
            threading.Thread(
                target=worker,
                args=("B",),
                name="korventis-lock-B",
                daemon=False,
            ),
        ]
        deadline = time.monotonic() + _WORKER_DEADLINE_SECONDS
        for thread in threads:
            thread.start()
        for thread in threads:
            remaining = deadline - time.monotonic()
            thread.join(timeout=max(0.0, remaining))
        alive = [thread.name for thread in threads if thread.is_alive()]

        with result_lock:
            results_snapshot = tuple(results)
            pids_snapshot = tuple(worker_pids)
            errors_snapshot = tuple(errors)

        if alive:
            print(markers.dump(), file=sys.stderr, flush=True)
            diagnosis = self._dump_pg_diagnosis(db_name, pids_snapshot, main_pid)
            print(diagnosis, file=sys.stderr, flush=True)

        omit_unlink = False
        omit_reason = ""
        if alive:
            try:
                still_active = self._active_backend_pids(db_name, pids_snapshot)
            except Exception:  # noqa: BLE001
                still_active = None
                omit_unlink = True
                omit_reason = (
                    "cleanup omitted: could not inspect worker PIDs in "
                    "pg_stat_activity:\n%s" % traceback.format_exc()
                )
            else:
                if still_active:
                    omit_unlink = True
                    omit_reason = (
                        "cleanup omitted: worker backends still in pg_stat_activity: %s"
                        % (still_active,)
                    )
            if omit_reason:
                print("korventis_pg_lock %s" % omit_reason, file=sys.stderr, flush=True)

        try:
            if alive:
                primary_error = (
                    "Worker threads did not finish before the %.1fs global deadline "
                    "(possible harness or lock wait). Alive=%s registry.test_cr=%s "
                    "main_pid=%s worker_pids=%s\nmarkers:\n%s\n%s"
                    % (
                        _WORKER_DEADLINE_SECONDS,
                        alive,
                        test_mode,
                        main_pid,
                        pids_snapshot,
                        markers.dump(),
                        diagnosis,
                    )
                )
            elif errors_snapshot:
                primary_error = (
                    "Worker errors (PostgreSQL timeouts and other exceptions are "
                    "FAIL, not PASS):\n%s\nmarkers:\n%s"
                    % ("\n---\n".join(errors_snapshot), markers.dump())
                )
            elif len(pids_snapshot) != 2:
                primary_error = (
                    "Expected two worker backend PIDs. Got %s\nmarkers:\n%s"
                    % (pids_snapshot, markers.dump())
                )
            elif len(set(pids_snapshot)) != 2:
                primary_error = (
                    "Worker PostgreSQL backends must be distinct. Got %s\nmarkers:\n%s"
                    % (pids_snapshot, markers.dump())
                )
            elif main_pid in pids_snapshot:
                primary_error = (
                    "main_pid %s must not be a worker backend. worker_pids=%s\n"
                    "markers:\n%s" % (main_pid, pids_snapshot, markers.dump())
                )
            elif len(results_snapshot) != 2:
                primary_error = "Expected 2 allocate results, got %s" % (
                    results_snapshot,
                )
            else:
                numbers = [item[0] for item in results_snapshot]
                raws = sorted(item[1] for item in results_snapshot)
                if len(set(numbers)) != 2:
                    primary_error = "Fiscal numbers must be unique, got %s" % (numbers,)
                elif set(numbers) != _EXPECTED_FISCAL_NUMBERS:
                    primary_error = (
                        "Expected fiscal numbers %s, got %s"
                        % (sorted(_EXPECTED_FISCAL_NUMBERS), sorted(numbers))
                    )
                elif raws != [_LOCK_RANGE_START, _LOCK_RANGE_START + 1]:
                    primary_error = (
                        "Expected sorted raws %s, got %s"
                        % ([_LOCK_RANGE_START, _LOCK_RANGE_START + 1], raws)
                    )
                elif not (
                    markers.has_stage("A", "before_env_create")
                    and markers.has_stage("B", "before_env_create")
                    and markers.has_stage("A", "env_created")
                    and markers.has_stage("B", "env_created")
                    and markers.has_stage("A", "before_allocate")
                    and markers.has_stage("B", "before_allocate")
                ):
                    primary_error = (
                        "Workers did not reach env_created/before_allocate.\nmarkers:\n%s"
                        % markers.dump()
                    )
                else:
                    verify_cr = _open_real_cursor(db_name)
                    try:
                        verify_cr.execute(
                            "SET application_name = %s",
                            ("korventis_pg_lock_verify",),
                        )
                        verify = api.Environment(verify_cr, SUPERUSER_ID, {})
                        persisted = verify["korventis.fiscal.sequence"].browse(seq_id)
                        if not persisted.exists():
                            primary_error = "Verify: sequence %s is missing." % seq_id
                        elif persisted.next_number != _LOCK_RANGE_START + 2:
                            primary_error = (
                                "Persisted next_number=%s, expected %s"
                                % (
                                    persisted.next_number,
                                    _LOCK_RANGE_START + 2,
                                )
                            )
                    finally:
                        verify_cr.close()
        except Exception:  # noqa: BLE001
            if primary_error is None:
                primary_error = "Unexpected error during assertions:\n%s" % (
                    traceback.format_exc(),
                )

        try:
            if omit_unlink:
                if primary_error is None:
                    primary_error = omit_reason
                else:
                    primary_error = "%s\n%s" % (primary_error, omit_reason)
            elif seq_id:
                cleanup_cr = _open_real_cursor(db_name)
                try:
                    cleanup_cr.execute(
                        "SET application_name = %s", ("korventis_pg_lock_cleanup",)
                    )
                    cleanup_cr.execute(
                        "SET lock_timeout = %s", (_CLEANUP_LOCK_TIMEOUT,)
                    )
                    env = api.Environment(cleanup_cr, SUPERUSER_ID, {})
                    leftover = env["korventis.fiscal.sequence"].browse(seq_id)
                    if leftover.exists():
                        docs = env["korventis.fiscal.document"].search_count(
                            [("sequence_id", "=", seq_id)]
                        )
                        if docs:
                            raise AssertionError(
                                "Cleanup sequence %s has %s fiscal document(s); "
                                "refusing direct test-fixture deletion."
                                % (seq_id, docs)
                            )
                        cleanup_cr.execute(
                            "DELETE FROM korventis_fiscal_sequence WHERE id = %s",
                            (seq_id,),
                        )
                    cleanup_cr.commit()
                    env.invalidate_all()
                    gone = env["korventis.fiscal.sequence"].browse(seq_id)
                    if gone.exists():
                        raise AssertionError(
                            "Cleanup left sequence %s in the database." % seq_id
                        )
                finally:
                    cleanup_cr.close()
        except Exception:  # noqa: BLE001
            cleanup_error = traceback.format_exc()
            print(
                "korventis_pg_lock cleanup failed:\n%s" % cleanup_error,
                file=sys.stderr,
                flush=True,
            )

        combined = self._combine_errors(primary_error, cleanup_error)
        if combined:
            self.fail(combined)
