from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.korventis_partner_dgii.services.normalization import (
    normalize_identification,
)


class KorventisPartnerLookupWizard(models.TransientModel):
    _name = "korventis.partner.lookup.wizard"
    _description = "Buscar o registrar cliente Korventis"

    state = fields.Selection(
        [
            ("search", "Búsqueda"),
            ("confirm_dgii", "Confirmación DGII"),
            ("manual", "Registro manual"),
        ],
        default="search",
        required=True,
    )
    query = fields.Char(string="Nombre, razón social, RNC o cédula")
    result_ids = fields.One2many(
        "korventis.partner.lookup.line",
        "wizard_id",
        string="Resultados",
    )
    selected_registry_id = fields.Many2one(
        "korventis.dgii.rnc",
        string="Contribuyente DGII",
        readonly=True,
    )
    selected_registry_rnc = fields.Char(
        related="selected_registry_id.rnc",
        string="RNC/Cédula",
        readonly=True,
    )
    selected_registry_name = fields.Char(
        related="selected_registry_id.razon_social",
        string="Razón social",
        readonly=True,
    )
    selected_registry_status = fields.Char(
        related="selected_registry_id.estado",
        string="Estado DGII",
        readonly=True,
    )
    selected_registry_activity = fields.Char(
        related="selected_registry_id.actividad_economica",
        string="Actividad económica",
        readonly=True,
    )
    registry_available = fields.Boolean(compute="_compute_registry_available")
    manual_name = fields.Char(string="Nombre o razón social")
    manual_identification = fields.Char(string="RNC o cédula")
    manual_fiscal_type_id = fields.Many2one(
        "korventis.fiscal.document.type",
        string="Tipo de comprobante fiscal",
        domain="[('partner_assignable', '=', True), ('active', '=', True)]",
    )

    @api.depends()
    def _compute_registry_available(self):
        available = bool(
            self.env["korventis.dgii.rnc.version"].sudo().search_count(
                [("state", "=", "active")],
                limit=1,
            )
        )
        for wizard in self:
            wizard.registry_available = available

    def action_search(self):
        self.ensure_one()
        query = (self.query or "").strip()
        if len(query) < 3:
            raise UserError(_("Escriba al menos tres caracteres para buscar."))
        self.result_ids.unlink()
        Partner = self.env["res.partner"]
        normalized = normalize_identification(query)
        if normalized.isdigit():
            domain = [
                ("korventis_identification_normalized", "=like", normalized + "%"),
            ]
        else:
            domain = [("name", "ilike", query)]
        partners = Partner.search(domain, order="name, id", limit=20)
        lines = []
        existing_identifications = set()
        for partner in partners.mapped("commercial_partner_id"):
            identification = partner.korventis_identification_normalized
            if identification:
                existing_identifications.add(identification)
            lines.append(
                (
                    0,
                    0,
                    {
                        "source": "partner",
                        "partner_id": partner.id,
                        "name": partner.display_name,
                        "identification": partner.vat,
                        "status": _("Contacto existente"),
                    },
                )
            )
        remaining = max(20 - len(lines), 0)
        if remaining:
            registry_records = self.env[
                "korventis.dgii.rnc"
            ].search_active_registry(query, limit=remaining)
            for record in registry_records:
                existing = Partner._korventis_existing_by_identification(record.rnc)
                if existing or record.rnc_normalizado in existing_identifications:
                    continue
                lines.append(
                    (
                        0,
                        0,
                        {
                            "source": "dgii",
                            "registry_id": record.id,
                            "name": record.razon_social,
                            "identification": record.rnc,
                            "status": record.estado,
                            "activity": record.actividad_economica,
                        },
                    )
                )
        self.write({"state": "search", "result_ids": lines})
        return self._reopen()

    def action_manual(self):
        self.ensure_one()
        self.state = "manual"
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        self.state = "search"
        self.selected_registry_id = False
        return self._reopen()

    def action_confirm_dgii(self):
        self.ensure_one()
        if not self.selected_registry_id:
            raise UserError(_("Seleccione un contribuyente del padrón."))
        partner = self.env["res.partner"].korventis_create_from_dgii(
            self.selected_registry_id
        )
        return self._use_partner(partner)

    def action_create_manual(self):
        self.ensure_one()
        partner = self.env["res.partner"].korventis_create_manual_customer(
            self.manual_name,
            self.manual_identification,
            self.manual_fiscal_type_id,
        )
        return self._use_partner(partner)

    def _use_partner(self, partner):
        active_model = self.env.context.get("active_model")
        active_id = self.env.context.get("active_id")
        if active_model == "account.move" and active_id:
            move = self.env["account.move"].browse(active_id).exists()
            if (
                not move
                or move.state != "draft"
                or move.korventis_fiscal_document_id
            ):
                raise UserError(
                    _("Sólo puede cambiarse el cliente de una factura fiscal en borrador.")
                )
            move.write({"partner_id": partner.id})
            return {"type": "ir.actions.act_window_close"}
        return {
            "type": "ir.actions.act_window",
            "name": _("Cliente"),
            "res_model": "res.partner",
            "res_id": partner.id,
            "view_mode": "form",
            "target": "current",
        }

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "name": _("Buscar o registrar cliente"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context),
        }


class KorventisPartnerLookupLine(models.TransientModel):
    _name = "korventis.partner.lookup.line"
    _description = "Resultado de búsqueda de cliente Korventis"
    _order = "id"

    wizard_id = fields.Many2one(
        "korventis.partner.lookup.wizard",
        required=True,
        ondelete="cascade",
    )
    source = fields.Selection(
        [
            ("partner", "Odoo"),
            ("dgii", "DGII"),
        ],
        required=True,
    )
    partner_id = fields.Many2one("res.partner", readonly=True)
    registry_id = fields.Many2one("korventis.dgii.rnc", readonly=True)
    name = fields.Char(readonly=True)
    identification = fields.Char(readonly=True)
    status = fields.Char(readonly=True)
    activity = fields.Char(readonly=True)

    def action_select(self):
        self.ensure_one()
        if self.source == "partner":
            return self.wizard_id._use_partner(self.partner_id)
        self.wizard_id.write(
            {
                "state": "confirm_dgii",
                "selected_registry_id": self.registry_id.id,
            }
        )
        return self.wizard_id._reopen()
