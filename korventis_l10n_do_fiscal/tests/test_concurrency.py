"""Concurrency tests.

Safe suite (`TestSequenceAllocationSafe`): one transaction, rolled back.
Safe on `korventis` and `baruchcafe`.

Isolated suite (`TestConcurrentSequenceAllocationIsolated`): two PostgreSQL
sessions. Tagged `-standard` (excluded from default `--test-enable`).

Disposable DB only (e.g. conceptual `korventis_fiscal_test`):

    odoo-bin -d korventis_fiscal_test --test-enable --test-tags=korventis_pg_lock --stop-after-init

NEVER run `korventis_pg_lock` on `korventis` or `baruchcafe`.
"""

import threading

from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry
from odoo.tests import TransactionCase, tagged

from odoo.addons.korventis_l10n_do_fiscal.services.ncf_service import NcfService
from odoo.addons.korventis_l10n_do_fiscal.tests.common import KorventisFiscalCommon


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
    def test_concurrent_sequence_allocation(self):
        type_e32 = self.env.ref("korventis_l10n_do_fiscal.document_type_e32")
        do = self.env.ref("base.do")
        company = self.env["res.company"].create(
            {
                "name": "KORVENTIS_LOCK_TEST_DO_NOT_USE",
                "country_id": do.id,
            }
        )
        seq = self.env["korventis.fiscal.sequence"].create(
            {
                "company_id": company.id,
                "document_type_id": type_e32.id,
                "prefix": "E32",
                "range_start": 8000000001,
                "range_end": 8000000099,
                "next_number": 8000000001,
            }
        )
        seq_id = seq.id
        company_id = company.id
        db_name = self.env.cr.dbname
        self.env.cr.commit()
        results = []
        errors = []
        barrier = threading.Barrier(2)

        def worker():
            try:
                barrier.wait(timeout=10)
                db_registry = Registry(db_name)
                with db_registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    sequence = env["korventis.fiscal.sequence"].browse(seq_id)
                    company_rec = env["res.company"].browse(company_id)
                    number, raw = NcfService(env).allocate(sequence, company=company_rec)
                    cr.commit()
                    results.append((number, raw))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        try:
            self.assertFalse(errors, errors)
            self.assertEqual(len(results), 2)
            numbers = [item[0] for item in results]
            self.assertEqual(len(set(numbers)), 2)
        finally:
            db_registry = Registry(db_name)
            with db_registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                leftover = env["korventis.fiscal.sequence"].browse(seq_id)
                if leftover.exists():
                    leftover.unlink()
                leftover_co = env["res.company"].browse(company_id)
                if leftover_co.exists() and leftover_co.name == "KORVENTIS_LOCK_TEST_DO_NOT_USE":
                    leftover_co.write({"active": False})
                cr.commit()
