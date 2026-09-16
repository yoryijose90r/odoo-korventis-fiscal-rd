from odoo import _, api, fields, models

from odoo.addons.korventis_partner_dgii.hooks import CRON_XMLID, LAST_MIGRATION_KEY


class KorventisDgiiRegistryStatus(models.TransientModel):
    _name = "korventis.dgii.registry.status"
    _description = "Estado del padrón local DGII"

    module_installed = fields.Boolean(readonly=True)
    registry_state = fields.Selection(
        [
            ("pending", "Padrón pendiente de importar"),
            ("active", "Padrón activo"),
        ],
        readonly=True,
    )
    active_version_id = fields.Many2one(
        "korventis.dgii.rnc.version",
        string="Versión activa",
        readonly=True,
    )
    active_record_count = fields.Integer(readonly=True)
    last_success_at = fields.Datetime(
        string="Última sincronización correcta",
        readonly=True,
    )
    last_success_state = fields.Char(readonly=True)
    last_error_at = fields.Datetime(string="Último error", readonly=True)
    last_error = fields.Text(readonly=True)
    cron_active = fields.Boolean(string="Tarea diaria activa", readonly=True)
    cron_nextcall = fields.Datetime(
        string="Próxima ejecución programada (UTC)",
        readonly=True,
    )
    auto_import_enabled = fields.Boolean(readonly=True)
    last_migration = fields.Char(readonly=True)

    @api.model
    def _status_values(self):
        parameters = self.env["ir.config_parameter"].sudo()
        active = self.env["korventis.dgii.rnc.version"].sudo().search(
            [("state", "=", "active")],
            limit=1,
        )
        success = self.env["korventis.dgii.import.run"].sudo().search(
            [("state", "in", ("success", "unchanged"))],
            order="finished_at desc, id desc",
            limit=1,
        )
        failed = self.env["korventis.dgii.import.run"].sudo().search(
            [("state", "=", "failed")],
            order="finished_at desc, id desc",
            limit=1,
        )
        cron = self.env.ref(CRON_XMLID, raise_if_not_found=False)
        if cron:
            cron = cron.sudo().with_context(active_test=False)
        return {
            "module_installed": True,
            "registry_state": "active" if active else "pending",
            "active_version_id": active.id,
            "active_record_count": active.record_count if active else 0,
            "last_success_at": success.finished_at,
            "last_success_state": success.state if success else False,
            "last_error_at": failed.finished_at,
            "last_error": failed.error_message if failed else False,
            "cron_active": bool(cron and cron.active),
            "cron_nextcall": cron.nextcall if cron else False,
            "auto_import_enabled": parameters.get_param(
                "korventis_partner_dgii.auto_import_enabled",
                "False",
            )
            == "True",
            "last_migration": parameters.get_param(LAST_MIGRATION_KEY, ""),
        }

    @api.model
    def action_open(self):
        status = self.create(self._status_values())
        return {
            "type": "ir.actions.act_window",
            "name": _("Estado del padrón DGII"),
            "res_model": self._name,
            "res_id": status.id,
            "view_mode": "form",
            "target": "current",
        }
