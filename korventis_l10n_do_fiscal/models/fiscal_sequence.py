from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class KorventisFiscalSequence(models.Model):
    _name = "korventis.fiscal.sequence"
    _description = "Korventis Fiscal Sequence Range"
    _order = "company_id, document_type_id, range_start"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    document_type_id = fields.Many2one(
        "korventis.fiscal.document.type",
        required=True,
        index=True,
        ondelete="restrict",
        check_company=False,
    )
    prefix = fields.Char(required=True)
    range_start = fields.Integer(required=True)
    range_end = fields.Integer(required=True)
    next_number = fields.Integer(required=True)
    valid_from = fields.Date()
    valid_until = fields.Date()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "range_order",
            "CHECK(range_start <= range_end)",
            "Range start cannot be greater than range end.",
        ),
        (
            "range_start_positive",
            "CHECK(range_start >= 1)",
            "Range start must be at least 1.",
        ),
        (
            "next_in_range",
            "CHECK(next_number >= range_start AND next_number <= range_end + 1)",
            "Next number must stay within the authorized range (or one past the end when exhausted).",
        ),
    ]

    @api.depends("company_id", "document_type_id", "prefix", "range_start", "range_end")
    def _compute_name(self):
        for rec in self:
            type_code = rec.document_type_id.code or ""
            rec.name = "%s %s %s-%s" % (
                rec.company_id.display_name or "",
                type_code,
                rec.range_start or 0,
                rec.range_end or 0,
            )

    @api.onchange("document_type_id")
    def _onchange_document_type_id(self):
        if self.document_type_id:
            self.prefix = self.document_type_id.prefix

    def _advisory_lock_pair(self, company_id, type_id):
        """Serialize range writes per company+type. Session lock, released at COMMIT/ROLLBACK.

        Does not lock the whole table. Residual: bypasses if rows are inserted via raw SQL.
        Requires PostgreSQL hashtext() (built-in, not an extra extension).
        """
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            ("korventis.fiscal.sequence.%s.%s" % (company_id, type_id),),
        )

    def _has_consumed_numbers(self):
        self.ensure_one()
        return bool(
            self.env["korventis.fiscal.document"].search_count(
                [
                    ("sequence_id", "=", self.id),
                    ("state", "in", ("reserved", "issued", "cancelled")),
                ]
            )
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for vals in vals_list:
            if vals.get("document_type_id") and not vals.get("prefix"):
                dtype = self.env["korventis.fiscal.document.type"].browse(
                    vals["document_type_id"]
                )
                vals["prefix"] = dtype.prefix
            if vals.get("range_start") and not vals.get("next_number"):
                vals["next_number"] = vals["range_start"]
            company_id = vals.get("company_id") or self.env.company.id
            type_id = vals.get("document_type_id")
            if company_id and type_id:
                self._advisory_lock_pair(company_id, type_id)
            records |= super().create([vals])
        return records

    @api.constrains("prefix", "document_type_id")
    def _check_prefix_matches_type(self):
        for rec in self:
            if rec.document_type_id and rec.prefix != rec.document_type_id.prefix:
                raise ValidationError(
                    _(
                        "Sequence prefix %(prefix)s must match document type prefix %(type_prefix)s.",
                        prefix=rec.prefix,
                        type_prefix=rec.document_type_id.prefix,
                    )
                )

    @api.constrains("valid_from", "valid_until")
    def _check_validity_dates(self):
        for rec in self:
            if rec.valid_from and rec.valid_until and rec.valid_from > rec.valid_until:
                raise ValidationError(
                    _("Valid from cannot be later than valid until.")
                )

    @api.constrains(
        "company_id",
        "document_type_id",
        "range_start",
        "range_end",
        "valid_from",
        "valid_until",
        "active",
    )
    def _check_incompatible_ranges(self):
        for rec in self:
            if not rec.active:
                continue
            others = self.search(
                [
                    ("id", "!=", rec.id),
                    ("company_id", "=", rec.company_id.id),
                    ("document_type_id", "=", rec.document_type_id.id),
                    ("active", "=", True),
                    ("range_start", "<=", rec.range_end),
                    ("range_end", ">=", rec.range_start),
                ]
            )
            for other in others:
                if rec._dates_overlap(other):
                    raise ValidationError(
                        _(
                            "An overlapping active range already exists for company %(company)s and type %(type)s.",
                            company=rec.company_id.display_name,
                            type=rec.document_type_id.code,
                        )
                    )

    def _dates_overlap(self, other):
        self.ensure_one()
        start_a = self.valid_from or fields.Date.to_date("1970-01-01")
        end_a = self.valid_until or fields.Date.to_date("2999-12-31")
        start_b = other.valid_from or fields.Date.to_date("1970-01-01")
        end_b = other.valid_until or fields.Date.to_date("2999-12-31")
        return start_a <= end_b and start_b <= end_a

    def write(self, vals):
        protected_after_use = {"range_start", "range_end", "prefix", "document_type_id", "company_id"}
        for rec in self:
            rec._advisory_lock_pair(rec.company_id.id, rec.document_type_id.id)
            new_company = vals.get("company_id") or rec.company_id.id
            new_type = vals.get("document_type_id") or rec.document_type_id.id
            if (new_company, new_type) != (rec.company_id.id, rec.document_type_id.id):
                rec._advisory_lock_pair(new_company, new_type)
            used = rec._has_consumed_numbers()
            if used and protected_after_use.intersection(vals):
                raise UserError(
                    _(
                        "Cannot change range bounds, company or type of a sequence that already "
                        "issued or reserved fiscal numbers. Administrative rewind is not implemented."
                    )
                )
            if "next_number" in vals and used:
                new_next = vals["next_number"]
                if new_next < rec.next_number:
                    raise UserError(
                        _(
                            "next_number cannot be rewound from %(old)s to %(new)s after the sequence "
                            "has been used. The counter is monotonic.",
                            old=rec.next_number,
                            new=new_next,
                        )
                    )
        return super().write(vals)
