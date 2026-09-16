from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.korventis_partner_dgii.services.normalization import (
    escape_like,
    normalize_identification,
    normalize_name,
)
from odoo.addons.korventis_partner_dgii.services.schema import (
    ensure_custom_indexes,
)


class KorventisDgiiRnc(models.Model):
    _name = "korventis.dgii.rnc"
    _description = "Contribuyente del padrón local DGII"
    _rec_name = "razon_social"
    _order = "razon_social, rnc"

    rnc = fields.Char(required=True, index=True)
    rnc_normalizado = fields.Char(required=True, index=True)
    razon_social = fields.Char(required=True)
    razon_social_normalizada = fields.Char(required=True)
    actividad_economica = fields.Char()
    fecha_inicio_operaciones = fields.Date()
    estado = fields.Char(required=True, index=True)
    regimen_pago = fields.Char(required=True)
    fecha_importacion = fields.Datetime(required=True, readonly=True)
    version_padron_id = fields.Many2one(
        "korventis.dgii.rnc.version",
        required=True,
        index=True,
        ondelete="cascade",
    )

    _sql_constraints = [
        (
            "version_rnc_unique",
            "unique(version_padron_id, rnc)",
            "El identificador debe ser único dentro de una versión del padrón.",
        ),
    ]

    def init(self):
        ensure_custom_indexes(self.env.cr)

    @api.model
    def search_active_registry(self, query, limit=20):
        if not (
            self.env.user._is_system()
            or self.env.user.has_group(
                "korventis_partner_dgii.group_dgii_user"
            )
            or self.env.user.has_group("account.group_account_invoice")
        ):
            raise AccessError(_("No tiene permisos para consultar el padrón DGII."))
        limit = min(max(int(limit or 20), 1), 50)
        query = (query or "").strip()
        if not query:
            return self.browse()
        normalized_id = normalize_identification(query)
        normalized_name = normalize_name(query)
        like_escape = " ESCAPE '\\\\'"
        if normalized_id.isdigit():
            where = "r.rnc_normalizado LIKE %s" + like_escape
            filter_parameters = [escape_like(normalized_id) + "%"]
        else:
            where = (
                """
                (
                    r.razon_social_normalizada LIKE %s"""
                + like_escape
                + """
                    OR to_tsvector(
                        'simple'::regconfig,
                        r.razon_social_normalizada
                    ) @@ plainto_tsquery('simple'::regconfig, %s)
                )
                """
            )
            filter_parameters = [escape_like(normalized_name) + "%", normalized_name]
        self.env.cr.execute(
            f"""
            SELECT r.id
              FROM korventis_dgii_rnc r
              JOIN korventis_dgii_rnc_version v
                ON v.id = r.version_padron_id
             WHERE v.state = 'active'
               AND {where}
             ORDER BY
                   CASE WHEN r.rnc_normalizado = %s
                             OR r.razon_social_normalizada = %s
                        THEN 0 ELSE 1 END,
                   r.razon_social,
                   r.rnc
             LIMIT %s
            """,
            tuple(filter_parameters + [normalized_id, normalized_name, limit]),
        )
        return self.browse([row[0] for row in self.env.cr.fetchall()])
