import threading

from odoo import api, SUPERUSER_ID
from odoo.modules.registry import Registry
from odoo.tests import tagged

from odoo.addons.korventis_l10n_do_fiscal.services.ncf_service import NcfService
from odoo.addons.korventis_l10n_do_fiscal.tests.common import KorventisFiscalCommon


@tagged("post_install", "-at_install")
class TestConcurrentSequenceAllocation(KorventisFiscalCommon):
    def test_concurrent_sequence_allocation(self):
        seq = self.env["korventis.fiscal.sequence"].create(
            {
                "company_id": self.company.id,
                "document_type_id": self.type_e32.id,
                "prefix": "E32",
                "range_start": 8000000001,
                "range_end": 8000000099,
                "next_number": 8000000001,
            }
        )
        seq_id = seq.id
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
                    service = NcfService(env)
                    sequence = env["korventis.fiscal.sequence"].browse(seq_id)
                    number, raw = service.allocate(sequence)
                    cr.commit()
                    results.append((number, raw))
            except Exception as exc:  # noqa: BLE001 — collect for assertion
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertFalse(errors, errors)
        self.assertEqual(len(results), 2)
        numbers = [item[0] for item in results]
        raws = [item[1] for item in results]
        self.assertEqual(len(set(numbers)), 2)
        self.assertEqual(len(set(raws)), 2)
        self.assertTrue(all(n.startswith("E32") and len(n) == 13 for n in numbers))
