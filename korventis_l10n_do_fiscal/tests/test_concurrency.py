"""Concurrency tests.

Safe suite (`TestSequenceAllocationSafe`): one transaction, rolled back.
Safe on `korventis` and `baruchcafe`.

Isolated suite (`TestConcurrentSequenceAllocationIsolated`): two PostgreSQL
sessions. Tagged `-standard` (excluded from default `--test-enable`).

Odoo 18 TransactionCase patches ``self.env.cr.commit/rollback`` so they raise.
This test never commits the managed test cursor. Setup, workers, verify and
cleanup use ``Registry(dbname).cursor()`` (independent connections).

Disposable DB only (e.g. `korventis_fiscal_test`):

    odoo-bin -d korventis_fiscal_test --test-enable --test-tags=korventis_pg_lock --stop-after-init

NEVER run `korventis_pg_lock` on `korventis` or `baruchcafe`.
"""

import threading

from odoo import api, SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.modules.registry import Registry
from odoo.tests import TransactionCase, tagged

from odoo.addons.korventis_l10n_do_fiscal.services.ncf_service import NcfService
from odoo.addons.korventis_l10n_do_fiscal.tests.common import KorventisFiscalCommon

_LOCK_RANGE_START = 8000000001
_LOCK_RANGE_END = 8000000099
_COMPANY_NAME = "KORVENTIS_LOCK_TEST_DO_NOT_USE"
_FORBIDDEN_DBS = frozenset({"korventis", "baruchcafe"})
_DISPOSABLE_DB_EXACT = "korventis_fiscal_test"


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

    def _independent_env(self, db_name):
        """New PostgreSQL session. commit/rollback are NOT patched by TransactionCase."""
        return Registry(db_name).cursor()

    def test_concurrent_sequence_allocation(self):
        db_name = self.env.cr.dbname
        self._assert_disposable_lock_db(db_name)
        seq_id = False
        company_id = False
        results = []
        errors = []
        barrier = threading.Barrier(2)
        result_lock = threading.Lock()

        with self._independent_env(db_name) as setup_cr:
            setup = api.Environment(setup_cr, SUPERUSER_ID, {})
            type_e32 = setup.ref("korventis_l10n_do_fiscal.document_type_e32")
            do = setup.ref("base.do")
            company = setup["res.company"].create(
                {
                    "name": _COMPANY_NAME,
                    "country_id": do.id,
                }
            )
            seq = setup["korventis.fiscal.sequence"].create(
                {
                    "company_id": company.id,
                    "document_type_id": type_e32.id,
                    "prefix": "E32",
                    "range_start": _LOCK_RANGE_START,
                    "range_end": _LOCK_RANGE_END,
                    "next_number": _LOCK_RANGE_START,
                }
            )
            seq_id = seq.id
            company_id = company.id
            setup_cr.commit()

        def worker():
            try:
                barrier.wait(timeout=10)
                with Registry(db_name).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    sequence = env["korventis.fiscal.sequence"].browse(seq_id)
                    company_rec = env["res.company"].browse(company_id)
                    number, raw = NcfService(env).allocate(sequence, company=company_rec)
                    cr.commit()
                    with result_lock:
                        results.append((number, raw))
            except Exception as exc:  # noqa: BLE001
                with result_lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        alive = [thread for thread in threads if thread.is_alive()]

        try:
            self.assertFalse(alive, "Worker threads did not finish (possible deadlock).")
            self.assertFalse(errors, errors)
            self.assertEqual(len(results), 2)
            numbers = [item[0] for item in results]
            raws = sorted(item[1] for item in results)
            self.assertEqual(len(set(numbers)), 2)
            self.assertEqual(raws, [_LOCK_RANGE_START, _LOCK_RANGE_START + 1])
            for number in numbers:
                self.assertEqual(len(number), 13)
                self.assertTrue(number.startswith("E32"))
            with self._independent_env(db_name) as verify_cr:
                verify = api.Environment(verify_cr, SUPERUSER_ID, {})
                persisted = verify["korventis.fiscal.sequence"].browse(seq_id)
                self.assertEqual(persisted.next_number, _LOCK_RANGE_START + 2)
        finally:
            with self._independent_env(db_name) as cleanup_cr:
                env = api.Environment(cleanup_cr, SUPERUSER_ID, {})
                leftover = env["korventis.fiscal.sequence"].browse(seq_id)
                if leftover.exists():
                    leftover.unlink()
                leftover_co = env["res.company"].browse(company_id)
                if leftover_co.exists() and leftover_co.name == _COMPANY_NAME:
                    try:
                        leftover_co.unlink()
                    except (UserError, Exception):
                        leftover_co.write({"active": False})
                cleanup_cr.commit()
