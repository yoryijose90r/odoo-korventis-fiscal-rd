import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.korventis_l10n_do_fiscal.fields import FiscalBigInt

_logger = logging.getLogger(__name__)

# e-NCF sequential width is 10 digits. Exhausted sequences store range_end + 1
# (see next_in_range), which may be 10_000_000_000 and still fits in BIGINT.
FISCAL_SEQUENTIAL_MAX = 9_999_999_999


class KorventisFiscalSequence(models.Model):
    _name = "korventis.fiscal.sequence"
    _inherit = ["mail.thread", "mail.activity.mixin"]
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
    range_start = FiscalBigInt(required=True)
    range_end = FiscalBigInt(required=True)
    next_number = FiscalBigInt(required=True)
    valid_from = fields.Date()
    valid_until = fields.Date()
    active = fields.Boolean(default=True)
    warning_threshold_percent = fields.Float(
        string="Warning threshold (%)",
        default=20.0,
        required=True,
        help="Korventis operational policy. It does not represent a DGII rule.",
    )
    total_numbers = FiscalBigInt(compute="_compute_usage_metrics")
    used_numbers = FiscalBigInt(compute="_compute_usage_metrics")
    remaining_numbers = FiscalBigInt(compute="_compute_usage_metrics")
    used_percent = fields.Float(compute="_compute_usage_metrics", digits=(16, 2))
    remaining_percent = fields.Float(compute="_compute_usage_metrics", digits=(16, 2))
    operational_state = fields.Selection(
        [
            ("available", "Available"),
            ("warning", "Near exhaustion"),
            ("exhausted", "Exhausted"),
            ("expired", "Expired"),
        ],
        compute="_compute_operational_state",
        string="Operational status",
    )
    warning_triggered = fields.Boolean(
        readonly=True,
        copy=False,
        help="Set once the range first produces a low-availability activity.",
    )
    warning_triggered_at = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [
        (
            "range_order",
            "CHECK(range_start <= range_end)",
            "Range start cannot be greater than range end.",
        ),
        (
            "range_start_non_negative",
            "CHECK(range_start >= 1)",
            "Range start must be at least 1.",
        ),
        (
            "range_end_ten_digits",
            "CHECK(range_end >= 0 AND range_end <= 9999999999)",
            "Range end must be between 0 and 9,999,999,999 (10 e-NCF digits).",
        ),
        (
            "next_in_range",
            "CHECK(next_number >= range_start AND next_number <= range_end + 1)",
            "Next number must stay within the authorized range (or one past the end when exhausted).",
        ),
    ]

    @api.depends("range_start", "range_end", "next_number")
    def _compute_usage_metrics(self):
        for rec in self:
            total = max((rec.range_end or 0) - (rec.range_start or 0) + 1, 0)
            used = min(max((rec.next_number or 0) - (rec.range_start or 0), 0), total)
            remaining = max(total - used, 0)
            rec.total_numbers = total
            rec.used_numbers = used
            rec.remaining_numbers = remaining
            rec.used_percent = (used / total * 100.0) if total else 0.0
            rec.remaining_percent = (remaining / total * 100.0) if total else 0.0

    @api.depends(
        "valid_until",
        "next_number",
        "range_end",
        "remaining_numbers",
        "remaining_percent",
        "warning_threshold_percent",
    )
    def _compute_operational_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.valid_until and today > rec.valid_until:
                rec.operational_state = "expired"
            elif rec.next_number > rec.range_end:
                rec.operational_state = "exhausted"
            elif (
                rec.remaining_numbers > 0
                and rec.remaining_percent <= rec.warning_threshold_percent
            ):
                rec.operational_state = "warning"
            else:
                rec.operational_state = "available"

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
            if "next_number" not in vals and "range_start" in vals:
                vals["next_number"] = vals["range_start"]
            company_id = vals.get("company_id") or self.env.company.id
            type_id = vals.get("document_type_id")
            if company_id and type_id:
                self._advisory_lock_pair(company_id, type_id)
            records |= super().create([vals])
        return records

    @api.constrains("range_start", "range_end", "next_number")
    def _check_ten_digit_bounds(self):
        for rec in self:
            if rec.range_start < 1 or rec.range_start > FISCAL_SEQUENTIAL_MAX:
                raise ValidationError(
                    _("range_start must be between 1 and 9,999,999,999.")
                )
            if rec.range_end < 0 or rec.range_end > FISCAL_SEQUENTIAL_MAX:
                raise ValidationError(
                    _("range_end must be between 0 and 9,999,999,999.")
                )
            if rec.next_number < rec.range_start:
                raise ValidationError(_("next_number cannot be below range_start."))
            if rec.next_number > rec.range_end + 1:
                raise ValidationError(
                    _("next_number cannot exceed range_end by more than one (exhausted sentinel).")
                )

    @api.constrains("warning_threshold_percent")
    def _check_warning_threshold_percent(self):
        for rec in self:
            if not 1.0 <= rec.warning_threshold_percent <= 100.0:
                raise ValidationError(
                    _("Warning threshold must be between 1 and 100 percent.")
                )

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

    def _korventis_warning_responsible(self):
        self.ensure_one()
        group = self.env.ref(
            "korventis_l10n_do_fiscal.group_fiscal_manager",
            raise_if_not_found=False,
        )
        managers = group.sudo().users.filtered(
            lambda user: user.active and self.company_id in user.company_ids
        )
        return managers.sorted("id")[:1] or self.env.user

    def _korventis_trigger_warning_if_needed(self):
        """Schedule one non-blocking operational warning after allocation.

        ``allocate()`` holds the sequence row lock while calling this method,
        which serializes the anti-spam flag across PostgreSQL sessions.
        """
        self.ensure_one()
        try:
            self.invalidate_recordset(
                [
                    "next_number",
                    "warning_triggered",
                    "warning_triggered_at",
                ]
            )
            if self.warning_triggered or self.operational_state != "warning":
                return False
            responsible = self._korventis_warning_responsible()
            with self.env.cr.savepoint():
                self.sudo().activity_schedule(
                    "mail.mail_activity_data_todo",
                    summary=_("Secuencia fiscal próxima a agotarse"),
                    note=_(
                        "Esta secuencia fiscal está próxima a agotarse. "
                        "Quedan %(remaining)s de %(total)s comprobantes disponibles. "
                        "Considere gestionar una nueva secuencia ante DGII.",
                        remaining=self.remaining_numbers,
                        total=self.total_numbers,
                    ),
                    user_id=responsible.id,
                )
                self.sudo().write(
                    {
                        "warning_triggered": True,
                        "warning_triggered_at": fields.Datetime.now(),
                    }
                )
        except Exception:  # noqa: BLE001
            # An operational notification must never block fiscal issuance.
            _logger.exception(
                "Could not schedule fiscal sequence warning for sequence_id=%s",
                self.id,
            )
            return False
        self.invalidate_recordset(["warning_triggered", "warning_triggered_at"])
        return True

    def unlink(self):
        today = fields.Date.context_today(self)
        for rec in self:
            expired = bool(rec.valid_until and today > rec.valid_until)
            if expired or rec.next_number > rec.range_start or rec._has_consumed_numbers():
                raise UserError(
                    _(
                        "Used, exhausted or expired fiscal ranges must be kept "
                        "for historical audit."
                    )
                )
        return super().unlink()
