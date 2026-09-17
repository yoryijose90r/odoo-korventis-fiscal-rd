from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.korventis_partner_dgii.services.normalization import (
    normalize_identification,
)
from odoo.addons.korventis_partner_dgii.services.schema import (
    REGISTRY_TEST_VERSION_CONTEXT,
)


class ResPartner(models.Model):
    _inherit = "res.partner"

    korventis_registration_origin = fields.Selection(
        [
            ("dgii", "DGII"),
            ("manual", "Manual"),
        ],
        string="Origen de registro Korventis",
        readonly=True,
        copy=False,
    )
    korventis_verification_state = fields.Selection(
        [
            ("listed", "Incluido en padrón DGII"),
            ("pending", "Pendiente"),
        ],
        string="Estado de verificación",
        readonly=True,
        copy=False,
    )
    korventis_dgii_status = fields.Char(
        string="Estado del contribuyente DGII",
        readonly=True,
        copy=False,
    )
    korventis_dgii_activity = fields.Char(
        string="Actividad económica DGII",
        readonly=True,
        copy=False,
    )
    korventis_dgii_version_id = fields.Many2one(
        "korventis.dgii.rnc.version",
        string="Versión del padrón consultada",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    korventis_dgii_lookup_at = fields.Datetime(
        string="Fecha de consulta al padrón",
        readonly=True,
        copy=False,
    )
    korventis_identification_normalized = fields.Char(
        compute="_compute_korventis_identification_normalized",
        store=True,
        index=True,
        copy=False,
    )

    @api.depends("vat")
    def _compute_korventis_identification_normalized(self):
        for partner in self:
            partner.korventis_identification_normalized = (
                normalize_identification(partner.vat)
            )

    @api.model
    def _korventis_spanish_language(self):
        Lang = self.env["res.lang"]
        dominican = Lang._lang_get("es_DO")
        if dominican:
            return dominican.code
        installed = Lang.get_installed()
        spanish = next(
            (code for code, _name in installed if code.startswith("es_")),
            False,
        )
        if not spanish:
            raise UserError(
                _(
                    "Debe instalar y activar al menos un idioma español antes "
                    "de registrar clientes con el asistente Korventis."
                )
            )
        return spanish

    @api.model
    def _korventis_check_lookup_access(self):
        if not (
            self.env.user._is_system()
            or self.env.user.has_group(
                "korventis_partner_dgii.group_dgii_user"
            )
            or self.env.user.has_group("account.group_account_invoice")
        ):
            raise AccessError(
                _("No tiene permisos para registrar clientes mediante el padrón DGII.")
            )

    @api.model
    def _korventis_lock_identification(self, normalized):
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            ("korventis_partner_dgii.partner.%s" % normalized,),
        )

    @api.model
    def _korventis_existing_by_identification(self, identification):
        normalized = normalize_identification(identification)
        if not normalized:
            return self.browse()
        partners = self.with_context(active_test=False).search(
            [("korventis_identification_normalized", "=", normalized)],
            order="active desc, id",
            limit=1,
        )
        return partners.commercial_partner_id

    @api.model
    def _korventis_registry_record_selectable(self, registry_record):
        version = registry_record.version_padron_id
        if version.state == "active":
            return True
        test_version_id = self.env.context.get(REGISTRY_TEST_VERSION_CONTEXT)
        return bool(test_version_id) and version.id == int(test_version_id)

    @api.model
    def korventis_create_from_dgii(self, registry_record):
        self._korventis_check_lookup_access()
        registry_record.ensure_one()
        if not self._korventis_registry_record_selectable(registry_record):
            raise UserError(
                _("El resultado seleccionado ya no pertenece al padrón activo.")
            )
        normalized = registry_record.rnc_normalizado
        self._korventis_lock_identification(normalized)
        existing = self._korventis_existing_by_identification(normalized)
        if existing:
            return existing
        e31 = self.env.ref("korventis_l10n_do_fiscal.document_type_e31")
        country = self.env.ref("base.do")
        return self.create(
            {
                "name": registry_record.razon_social,
                "vat": registry_record.rnc,
                "country_id": country.id,
                "company_type": "company" if len(normalized) == 9 else "person",
                "customer_rank": 1,
                "lang": self._korventis_spanish_language(),
                "korventis_fiscal_document_type_id": e31.id,
                "korventis_registration_origin": "dgii",
                "korventis_verification_state": "listed",
                "korventis_dgii_status": registry_record.estado,
                "korventis_dgii_activity": registry_record.actividad_economica,
                "korventis_dgii_version_id": registry_record.version_padron_id.id,
                "korventis_dgii_lookup_at": fields.Datetime.now(),
            }
        )

    @api.model
    def korventis_create_manual_customer(
        self,
        name,
        identification,
        fiscal_document_type,
    ):
        self._korventis_check_lookup_access()
        name = (name or "").strip()
        normalized = normalize_identification(identification)
        if not name:
            raise UserError(_("Debe indicar el nombre o razón social del cliente."))
        if not normalized:
            raise UserError(_("Debe indicar el RNC o la cédula del cliente."))
        if not normalized.isdigit() or len(normalized) not in (9, 11):
            raise ValidationError(
                _(
                    "El RNC debe tener 9 dígitos o la cédula 11 dígitos. "
                    "No se agregan ceros ni se valida el identificador ante DGII."
                )
            )
        if not fiscal_document_type:
            raise UserError(
                _("Debe seleccionar explícitamente un tipo de comprobante fiscal.")
            )
        if (
            not fiscal_document_type.partner_assignable
            or not fiscal_document_type.active
        ):
            raise UserError(
                _("El tipo fiscal seleccionado no puede asignarse a clientes.")
            )
        self._korventis_lock_identification(normalized)
        existing = self._korventis_existing_by_identification(normalized)
        if existing:
            return existing
        return self.create(
            {
                "name": name,
                "vat": normalized,
                "country_id": self.env.ref("base.do").id,
                "company_type": "company" if len(normalized) == 9 else "person",
                "customer_rank": 1,
                "lang": self._korventis_spanish_language(),
                "korventis_fiscal_document_type_id": fiscal_document_type.id,
                "korventis_registration_origin": "manual",
                "korventis_verification_state": "pending",
            }
        )

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == "form":
            for node in arch.xpath("//field[@name='name' or @name='vat']"):
                if node.get("widget") == "field_partner_autocomplete":
                    node.attrib.pop("widget")
        return arch, view
