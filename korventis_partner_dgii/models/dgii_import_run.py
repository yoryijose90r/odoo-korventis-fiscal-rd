import logging
import time

from odoo import _, api, fields, models
from odoo.exceptions import AccessError


_logger = logging.getLogger(__name__)

PRIMARY_DGII_URL = (
    "https://dgii.gov.do/app/WebApps/Consultas/RNC/"
    "RNC_CONTRIBUYENTES.zip"
)


class KorventisDgiiImportRun(models.Model):
    _name = "korventis.dgii.import.run"
    _description = "Ejecución de importación del padrón DGII"
    _order = "started_at desc, id desc"

    name = fields.Char(required=True, readonly=True)
    state = fields.Selection(
        [
            ("running", "En ejecución"),
            ("success", "Correcta"),
            ("unchanged", "Sin cambios"),
            ("failed", "Fallida"),
            ("skipped", "Omitida por concurrencia"),
        ],
        required=True,
        readonly=True,
        index=True,
    )
    source_url = fields.Char(readonly=True)
    started_at = fields.Datetime(required=True, readonly=True)
    finished_at = fields.Datetime(readonly=True)
    duration_seconds = fields.Float(readonly=True)
    archive_sha256 = fields.Char(readonly=True, index=True)
    version_id = fields.Many2one(
        "korventis.dgii.rnc.version",
        readonly=True,
        ondelete="set null",
    )
    total_rows = fields.Integer(readonly=True)
    accepted_count = fields.Integer(readonly=True)
    rejected_count = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)
    duplicate_count = fields.Integer(readonly=True)
    details = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)

    @api.model
    def _try_import_lock(self):
        self.env.cr.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s))",
            ("korventis_partner_dgii.import",),
        )
        return bool(self.env.cr.fetchone()[0])

    @api.model
    def run_import(self, source_url=None, fallback_url=None):
        if not (
            self.env.user._is_system()
            or self.env.user.has_group(
                "korventis_partner_dgii.group_dgii_manager"
            )
        ):
            raise AccessError(_("Sólo un administrador DGII puede importar el padrón."))
        Run = self.sudo()
        started_at = fields.Datetime.now()
        if not self._try_import_lock():
            return Run.create(
                {
                    "name": _("Importación DGII omitida %s") % started_at,
                    "state": "skipped",
                    "source_url": source_url or PRIMARY_DGII_URL,
                    "started_at": started_at,
                    "finished_at": fields.Datetime.now(),
                    "details": _("Otra importación del padrón ya está en ejecución."),
                }
            )
        run = Run.create(
            {
                "name": _("Importación DGII %s") % started_at,
                "state": "running",
                "source_url": source_url or PRIMARY_DGII_URL,
                "started_at": started_at,
            }
        )
        started_clock = time.monotonic()
        importer = None
        try:
            from odoo.addons.korventis_partner_dgii.services.importer import (
                DgiiRegistryImporter,
            )

            importer = DgiiRegistryImporter(self.env, run)
            with self.env.cr.savepoint():
                result = importer.execute(
                    source_url or PRIMARY_DGII_URL,
                    fallback_url=fallback_url,
                )
            run.write(
                {
                    "state": result["state"],
                    "source_url": result["source_url"],
                    "finished_at": fields.Datetime.now(),
                    "duration_seconds": time.monotonic() - started_clock,
                    "archive_sha256": result.get("archive_sha256"),
                    "version_id": result.get("version_id"),
                    "total_rows": result.get("total_rows", 0),
                    "accepted_count": result.get("accepted_count", 0),
                    "rejected_count": result.get("rejected_count", 0),
                    "warning_count": result.get("warning_count", 0),
                    "duplicate_count": result.get("duplicate_count", 0),
                    "details": result.get("details"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            _logger.exception("DGII local registry import failed")
            stats = importer.stats if importer else {}
            run.write(
                {
                    "state": "failed",
                    "finished_at": fields.Datetime.now(),
                    "duration_seconds": time.monotonic() - started_clock,
                    "archive_sha256": (
                        importer.archive_sha256 if importer else False
                    ),
                    "total_rows": stats.get("total_rows", 0),
                    "accepted_count": stats.get("accepted_count", 0),
                    "rejected_count": stats.get("rejected_count", 0),
                    "warning_count": stats.get("warning_count", 0),
                    "duplicate_count": stats.get("duplicate_count", 0),
                    "details": (
                        importer._details() if importer else False
                    ),
                    "error_message": str(exc),
                }
            )
        return run

    @api.model
    def _cron_import_registry(self):
        parameters = self.env["ir.config_parameter"].sudo()
        source_url = parameters.get_param(
            "korventis_partner_dgii.source_url",
            PRIMARY_DGII_URL,
        )
        fallback_url = parameters.get_param(
            "korventis_partner_dgii.fallback_url",
            "",
        )
        self.run_import(source_url, fallback_url=fallback_url or None)
        return True

    def action_open_version(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Versión del padrón"),
            "res_model": "korventis.dgii.rnc.version",
            "res_id": self.version_id.id,
            "view_mode": "form",
        }
