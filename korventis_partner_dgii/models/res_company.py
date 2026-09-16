from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == "form":
            for node in arch.xpath("//field[@name='name' or @name='vat']"):
                if node.get("widget") == "field_partner_autocomplete":
                    node.attrib.pop("widget")
        return arch, view
