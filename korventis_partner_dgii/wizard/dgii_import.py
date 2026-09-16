from odoo import _, fields, models

from odoo.addons.korventis_partner_dgii.models.dgii_import_run import (
    PRIMARY_DGII_URL,
)
from odoo.addons.korventis_partner_dgii.services.importer import (
    DgiiRegistryImporter,
)


class KorventisDgiiImportWizard(models.TransientModel):
    _name = "korventis.dgii.import.wizard"
    _description = "Importar padrón local DGII"

    source_url = fields.Char(
        string="URL principal",
        required=True,
        default=PRIMARY_DGII_URL,
    )
    fallback_url = fields.Char(
        string="URL oficial alternativa",
        help="Sólo se admiten URLs HTTPS del dominio oficial dgii.gov.do.",
    )
    save_for_scheduled_import = fields.Boolean(
        string="Usar estas URLs en la tarea diaria",
        default=True,
    )

    def action_import(self):
        self.ensure_one()
        importer = DgiiRegistryImporter(
            self.env,
            self.env["korventis.dgii.import.run"],
        )
        source_url = importer._validate_official_url(self.source_url)
        fallback_url = (
            importer._validate_official_url(self.fallback_url)
            if self.fallback_url
            else None
        )
        if self.save_for_scheduled_import:
            parameters = self.env["ir.config_parameter"].sudo()
            parameters.set_param(
                "korventis_partner_dgii.source_url",
                source_url,
            )
            parameters.set_param(
                "korventis_partner_dgii.fallback_url",
                fallback_url or "",
            )
        run = self.env["korventis.dgii.import.run"].run_import(
            source_url,
            fallback_url=fallback_url,
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Ejecución de importación DGII"),
            "res_model": "korventis.dgii.import.run",
            "res_id": run.id,
            "view_mode": "form",
            "target": "current",
        }
