import csv
import io
import os
import tempfile
import zipfile
from unittest.mock import patch

import requests

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.korventis_partner_dgii.services.importer import (
    CSV_HEADERS,
    DgiiRegistryImporter,
)
from odoo.addons.korventis_partner_dgii.tests.common import (
    official_registry_present,
)


SOURCE_URL = (
    "https://dgii.gov.do/app/WebApps/Consultas/RNC/"
    "RNC_CONTRIBUYENTES.zip"
)


@tagged("post_install", "-at_install")
class TestDgiiImporter(TransactionCase):
    def setUp(self):
        super().setUp()
        if official_registry_present(self.env):
            self.skipTest(
                "Los ZIP de fixture son pequeños y no pueden activarse contra "
                "un padrón oficial ya cargado. Use una base sin importación "
                "real para esta clase."
            )
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param("korventis_partner_dgii.minimum_records", "1")
        parameters.set_param("korventis_partner_dgii.minimum_volume_ratio", "0.01")
        parameters.set_param("korventis_partner_dgii.maximum_volume_ratio", "100")

    def _csv_bytes(self, rows, headers=None):
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(headers or CSV_HEADERS)
        writer.writerows(rows)
        return output.getvalue().encode("latin-1")

    def _zip_path(self, members):
        descriptor, path = tempfile.mkstemp(suffix=".zip")
        os.close(descriptor)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in members:
                archive.writestr(name, content)
        return path

    def _run_path(self, path, source_url=SOURCE_URL):
        with patch.object(
            DgiiRegistryImporter,
            "_download",
            return_value={
                "not_modified": False,
                "path": path,
                "etag": '"fixture"',
                "last_modified": "Wed, 16 Sep 2026 00:00:00 GMT",
            },
        ):
            return self.env["korventis.dgii.import.run"].run_import(source_url)

    def _valid_rows(self):
        return [
            [
                "101000011",
                "EMPRESA ACTIVA SRL",
                "SERVICIOS",
                "01/01/2020",
                "ACTIVO",
                "NORMAL",
            ],
            [
                "00114272360",
                "PERSONA SUSPENDIDA",
                "CONSULTORIA",
                "08/12/2006",
                "SUSPENDIDO",
                "NORMAL",
            ],
            [
                "02601322098",
                "ALBA ALEJANDRA GERMAN LUIS",
                "LIMPIEZA",
                "07/08/2013",
                "ACTIVO",
                "NORMAL",
            ],
        ]

    def _active_version(self):
        version = self.env["korventis.dgii.rnc.version"].sudo().create(
            {
                "name": "old.csv",
                "state": "active",
                "source_url": SOURCE_URL,
                "source_filename": "old.csv",
                "archive_sha256": "f" * 64,
                "imported_at": fields.Datetime.now(),
                "activated_at": fields.Datetime.now(),
                "record_count": 1,
            }
        )
        self.env["korventis.dgii.rnc"].sudo().create(
            {
                "rnc": "101999999",
                "rnc_normalizado": "101999999",
                "razon_social": "VERSION ANTERIOR",
                "razon_social_normalizada": "VERSION ANTERIOR",
                "estado": "ACTIVO",
                "regimen_pago": "NORMAL",
                "fecha_importacion": fields.Datetime.now(),
                "version_padron_id": version.id,
            }
        )
        return version

    def test_valid_import_activates_active_and_suspended_rows(self):
        path = self._zip_path(
            [
                (
                    "RNC_Contribuyentes_Actualizado_16_Sep_2026.csv",
                    self._csv_bytes(self._valid_rows()),
                )
            ]
        )
        run = self._run_path(path)
        self.assertEqual(run.state, "success")
        self.assertEqual(run.accepted_count, 3)
        self.assertEqual(run.rejected_count, 0)
        self.assertEqual(run.version_id.state, "active")
        records = self.env["korventis.dgii.rnc"].search(
            [("version_padron_id", "=", run.version_id.id)]
        )
        self.assertEqual(set(records.mapped("estado")), {"ACTIVO", "SUSPENDIDO"})
        self.assertIn("02601322098", records.mapped("rnc"))
        self.assertTrue(run.version_id.source_attachment_id)

    def test_isolated_anomalies_are_counted_without_discarding_registry(self):
        rows = self._valid_rows() + [
            ["12345678", "ID CORTO", "", "", "ACTIVO", "NORMAL"],
            ["101000012", "FECHA INVALIDA", "", "00/00/0000", "ACTIVO", "NORMAL"],
            ["101000013", "NOMBRE \x90 INSEGURO", "", "", "ACTIVO", "NORMAL"],
        ]
        path = self._zip_path([("RNC_Contribuyentes.csv", self._csv_bytes(rows))])
        run = self._run_path(path)
        self.assertEqual(run.state, "success")
        self.assertEqual(run.accepted_count, 4)
        self.assertEqual(run.rejected_count, 2)
        self.assertEqual(run.warning_count, 1)
        invalid_date = self.env["korventis.dgii.rnc"].search(
            [
                ("version_padron_id", "=", run.version_id.id),
                ("rnc", "=", "101000012"),
            ]
        )
        self.assertFalse(invalid_date.fecha_inicio_operaciones)
        self.assertFalse(
            self.env["korventis.dgii.rnc"].search(
                [
                    ("version_padron_id", "=", run.version_id.id),
                    ("rnc", "=", "12345678"),
                ]
            )
        )

    def test_txt_alternative_uses_separate_verified_adapter(self):
        line = (
            "101000011|EMPRESA ACTIVA SRL||SERVICIOS| | | | |"
            "01/01/2020|ACTIVO|NORMAL\r\n"
        ).encode("latin-1")
        path = self._zip_path([("TMP/DGII_RNC.TXT", line)])
        run = self._run_path(
            path,
            "https://dgii.gov.do/app/WebApps/Consultas/RNC/DGII_RNC.zip",
        )
        self.assertEqual(run.state, "success")
        self.assertEqual(run.accepted_count, 1)

    def test_duplicate_identifiers_fail_import(self):
        rows = self._valid_rows()
        rows.append(list(rows[0]))
        path = self._zip_path([("RNC_Contribuyentes.csv", self._csv_bytes(rows))])
        run = self._run_path(path)
        self.assertEqual(run.state, "failed")
        self.assertFalse(
            self.env["korventis.dgii.rnc.version"].search(
                [("state", "=", "active")]
            )
        )

    def test_corrupt_zip_fails_and_preserves_active_version(self):
        old = self._active_version()
        descriptor, path = tempfile.mkstemp(suffix=".zip")
        os.write(descriptor, b"not a zip")
        os.close(descriptor)
        run = self._run_path(path)
        self.assertEqual(run.state, "failed")
        self.assertEqual(old.state, "active")
        self.assertEqual(old.record_count, 1)

    def test_zip_with_unexpected_files_is_rejected(self):
        path = self._zip_path(
            [
                ("RNC_Contribuyentes.csv", self._csv_bytes(self._valid_rows())),
                ("unexpected.txt", b"unexpected"),
            ]
        )
        self.assertEqual(self._run_path(path).state, "failed")

    def test_zip_with_malicious_path_is_rejected(self):
        path = self._zip_path(
            [("../RNC_Contribuyentes.csv", self._csv_bytes(self._valid_rows()))]
        )
        self.assertEqual(self._run_path(path).state, "failed")

    def test_empty_and_wrong_column_csv_fail(self):
        header_only = self._zip_path(
            [("RNC_Contribuyentes.csv", self._csv_bytes([]))]
        )
        self.assertEqual(self._run_path(header_only).state, "failed")
        wrong_columns = self._zip_path(
            [
                (
                    "RNC_Contribuyentes.csv",
                    self._csv_bytes(self._valid_rows(), headers=["RNC", "NOMBRE"]),
                )
            ]
        )
        self.assertEqual(self._run_path(wrong_columns).state, "failed")

    def test_truncated_csv_fails(self):
        content = (
            ",".join(CSV_HEADERS).encode("latin-1")
            + b'\r\n"101000011","RAZON SIN CIERRE'
        )
        path = self._zip_path([("RNC_Contribuyentes.csv", content)])
        self.assertEqual(self._run_path(path).state, "failed")

    def test_activation_failure_rolls_back_candidate_and_preserves_old(self):
        old = self._active_version()
        path = self._zip_path(
            [("RNC_Contribuyentes.csv", self._csv_bytes(self._valid_rows()))]
        )
        with patch.object(
            DgiiRegistryImporter,
            "_activate",
            side_effect=UserError("simulated activation failure"),
        ):
            run = self._run_path(path)
        self.assertEqual(run.state, "failed")
        self.assertEqual(old.state, "active")
        self.assertEqual(
            self.env["korventis.dgii.rnc.version"].search_count([]),
            1,
        )

    def test_identical_hash_is_not_imported_again(self):
        content = self._csv_bytes(self._valid_rows())
        first_path = self._zip_path([("RNC_Contribuyentes.csv", content)])
        with open(first_path, "rb") as source:
            archive_bytes = source.read()
        first = self._run_path(first_path)
        descriptor, second_path = tempfile.mkstemp(suffix=".zip")
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(archive_bytes)
        second = self._run_path(second_path)
        self.assertEqual(first.state, "success")
        self.assertEqual(second.state, "unchanged")
        self.assertEqual(first.version_id, second.version_id)

    def test_previous_version_is_retained_and_can_be_restored(self):
        first = self._run_path(
            self._zip_path(
                [("RNC_Contribuyentes.csv", self._csv_bytes(self._valid_rows()))]
            )
        )
        changed_rows = self._valid_rows() + [
            ["101000014", "NUEVA EMPRESA", "", "", "ACTIVO", "NORMAL"]
        ]
        second = self._run_path(
            self._zip_path(
                [("RNC_Contribuyentes.csv", self._csv_bytes(changed_rows))]
            )
        )
        self.assertEqual(first.version_id.state, "previous")
        self.assertEqual(second.version_id.state, "active")
        self.assertEqual(
            self.env["korventis.dgii.rnc.version"].search_count([]),
            2,
        )
        first.version_id.action_restore_previous()
        self.assertEqual(first.version_id.state, "active")
        self.assertEqual(second.version_id.state, "previous")

    def test_concurrent_execution_is_skipped_before_download(self):
        Run = type(self.env["korventis.dgii.import.run"])
        with patch.object(Run, "_try_import_lock", return_value=False):
            with patch.object(DgiiRegistryImporter, "_download") as download:
                run = self.env["korventis.dgii.import.run"].run_import(SOURCE_URL)
        self.assertEqual(run.state, "skipped")
        download.assert_not_called()

    def test_download_failure_is_recorded_without_raising(self):
        with patch(
            "odoo.addons.korventis_partner_dgii.services.importer.requests.get",
            side_effect=requests.RequestException("offline"),
        ):
            run = self.env["korventis.dgii.import.run"].run_import(SOURCE_URL)
        self.assertEqual(run.state, "failed")
        self.assertIn("offline", run.error_message)

    def test_non_official_fallback_url_is_rejected(self):
        importer = DgiiRegistryImporter(
            self.env,
            self.env["korventis.dgii.import.run"],
        )
        with self.assertRaises(UserError):
            importer._validate_official_url("https://example.com/padron.zip")

    def test_official_csv_header_matches_phase_a_latin1(self):
        header = (
            "RNC,RAZÓN SOCIAL,ACTIVIDAD ECONÓMICA,"
            "FECHA DE INICIO OPERACIONES,ESTADO,RÉGIMEN DE PAGO"
        )
        self.assertEqual(header.split(","), CSV_HEADERS)
        encoded = header.encode("latin-1")
        path = self._zip_path(
            [
                (
                    "RNC_Contribuyentes_Actualizado_05_Sep_2026.csv",
                    encoded + b"\r\n" + self._csv_bytes(self._valid_rows()).split(b"\r\n", 1)[1],
                )
            ]
        )
        self.assertEqual(self._run_path(path).state, "success")

    def test_txt_malformed_line_does_not_merge_with_next(self):
        content = (
            "101000011|EMPRESA ACTIVA SRL||SERVICIOS| | | | |01/01/2020|ACTIVO\r\n"
            "|NORMAL\r\n"
            "101000011|EMPRESA ACTIVA SRL||SERVICIOS| | | | |"
            "01/01/2020|ACTIVO|NORMAL\r\n"
        ).encode("latin-1")
        path = self._zip_path([("TMP/DGII_RNC.TXT", content)])
        run = self._run_path(
            path,
            "https://dgii.gov.do/app/WebApps/Consultas/RNC/DGII_RNC.zip",
        )
        self.assertEqual(run.state, "success")
        self.assertEqual(run.accepted_count, 1)
        self.assertEqual(run.rejected_count, 2)

    def test_external_redirect_is_rejected(self):
        importer = DgiiRegistryImporter(
            self.env,
            self.env["korventis.dgii.import.run"],
        )
        redirect = requests.Response()
        redirect.status_code = 302
        redirect.headers["Location"] = "https://example.com/padron.zip"
        with patch(
            "odoo.addons.korventis_partner_dgii.services.importer.requests.get",
            return_value=redirect,
        ):
            with self.assertRaises(UserError):
                importer._download(SOURCE_URL, None)

    def test_partial_content_range_must_match_local_offset(self):
        importer = DgiiRegistryImporter(
            self.env,
            self.env["korventis.dgii.import.run"],
        )
        response = requests.Response()
        response.status_code = 206
        response.headers["Content-Range"] = "bytes 50-60/100"
        response.headers["Content-Length"] = "11"
        with patch(
            "odoo.addons.korventis_partner_dgii.services.importer.requests.get",
            return_value=response,
        ):
            with self.assertRaises(requests.RequestException):
                importer._download(SOURCE_URL, None)

    def test_failed_import_does_not_persist_cron_urls(self):
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param("korventis_partner_dgii.source_url", SOURCE_URL)
        parameters.set_param("korventis_partner_dgii.fallback_url", "")
        wizard = self.env["korventis.dgii.import.wizard"].create(
            {
                "source_url": SOURCE_URL,
                "fallback_url": (
                    "https://dgii.gov.do/app/WebApps/Consultas/RNC/DGII_RNC.zip"
                ),
                "save_for_scheduled_import": True,
            }
        )
        with patch.object(
            DgiiRegistryImporter,
            "_download",
            side_effect=requests.RequestException("offline"),
        ):
            wizard.action_import()
        self.assertEqual(
            parameters.get_param("korventis_partner_dgii.source_url"),
            SOURCE_URL,
        )
        self.assertFalse(parameters.get_param("korventis_partner_dgii.fallback_url"))
