from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class KorventisDgiiRncVersion(models.Model):
    _name = "korventis.dgii.rnc.version"
    _description = "Versión del padrón local DGII"
    _order = "imported_at desc, id desc"

    name = fields.Char(required=True, readonly=True)
    state = fields.Selection(
        [
            ("staging", "En preparación"),
            ("active", "Activa"),
            ("previous", "Anterior recuperable"),
        ],
        required=True,
        default="staging",
        readonly=True,
        index=True,
    )
    source_url = fields.Char(required=True, readonly=True)
    source_filename = fields.Char(required=True, readonly=True)
    source_last_modified = fields.Char(readonly=True)
    source_etag = fields.Char(readonly=True)
    archive_size = fields.Integer(readonly=True)
    archive_sha256 = fields.Char(required=True, readonly=True, index=True)
    source_attachment_id = fields.Many2one(
        "ir.attachment",
        readonly=True,
        ondelete="set null",
    )
    imported_at = fields.Datetime(required=True, readonly=True)
    activated_at = fields.Datetime(readonly=True)
    record_count = fields.Integer(readonly=True)
    rejected_count = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)

    _sql_constraints = [
        (
            "archive_sha256_unique",
            "unique(archive_sha256)",
            "Este archivo del padrón ya fue importado.",
        ),
    ]

    def init(self):
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                korventis_dgii_rnc_version_one_active_idx
                ON korventis_dgii_rnc_version (state)
                WHERE state = 'active'
            """
        )

    def action_restore_previous(self):
        self.ensure_one()
        if not (
            self.env.user._is_system()
            or self.env.user.has_group(
                "korventis_partner_dgii.group_dgii_manager"
            )
        ):
            raise AccessError(
                _("Sólo un administrador DGII puede restaurar versiones.")
            )
        if self.state != "previous":
            raise UserError(_("Sólo puede restaurarse la versión anterior."))
        self.env.cr.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s))",
            ("korventis_partner_dgii.import",),
        )
        if not self.env.cr.fetchone()[0]:
            raise UserError(_("Existe una importación del padrón en ejecución."))
        active = self.sudo().search([("state", "=", "active")])
        if len(active) != 1:
            raise UserError(_("Debe existir exactamente una versión activa."))
        active.write({"state": "previous"})
        self.sudo().write(
            {
                "state": "active",
                "activated_at": fields.Datetime.now(),
            }
        )
        return True
