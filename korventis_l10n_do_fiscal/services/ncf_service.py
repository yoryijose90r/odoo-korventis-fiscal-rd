import logging

from odoo import _, fields
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class NcfService:
    """Atomic e-NCF allocation. Does not contact DGII."""

    def __init__(self, env):
        self.env = env

    def format_fiscal_number(self, prefix, sequence_number, sequence_length):
        number = int(sequence_number)
        padded = str(number).zfill(sequence_length)
        if len(padded) > sequence_length:
            raise ValidationError(
                _("Sequence number %(number)s exceeds length %(length)s.", number=number, length=sequence_length)
            )
        return "%s%s" % (prefix, padded)

    def allocate(self, sequence):
        """Lock the sequence row and return (fiscal_number, sequence_number)."""
        if not sequence:
            raise UserError(_("A fiscal sequence is required."))
        cr = self.env.cr
        cr.execute(
            """
            SELECT id, next_number, range_start, range_end, prefix, active,
                   valid_from, valid_until, company_id, document_type_id
              FROM korventis_fiscal_sequence
             WHERE id = %s
               FOR UPDATE
            """,
            (sequence.id,),
        )
        row = cr.fetchone()
        if not row:
            raise UserError(_("Fiscal sequence not found."))
        (
            _sid,
            next_number,
            range_start,
            range_end,
            prefix,
            active,
            valid_from,
            valid_until,
            company_id,
            document_type_id,
        ) = row
        if not active:
            raise UserError(_("The fiscal sequence is not active."))
        today = fields.Date.context_today(sequence)
        if valid_from and today < valid_from:
            raise UserError(_("The fiscal sequence is not yet valid."))
        if valid_until and today > valid_until:
            raise UserError(_("The fiscal sequence is expired."))
        if next_number < range_start or next_number > range_end:
            raise UserError(
                _(
                    "The fiscal sequence is exhausted or next_number is outside the authorized range (%s-%s).",
                    range_start,
                    range_end,
                )
            )
        dtype = self.env["korventis.fiscal.document.type"].browse(document_type_id)
        fiscal_number = self.format_fiscal_number(
            prefix, next_number, dtype.sequence_length or 10
        )
        if dtype.electronic and len(fiscal_number) != 13:
            raise ValidationError(
                _(
                    "Electronic fiscal number %(number)s must have 13 characters (E + type + 10-digit sequence).",
                    number=fiscal_number,
                )
            )
        cr.execute(
            """
            UPDATE korventis_fiscal_sequence
               SET next_number = next_number + 1
             WHERE id = %s
            """,
            (sequence.id,),
        )
        sequence.invalidate_recordset(["next_number"])
        _logger.info(
            "korventis fiscal allocated company_id=%s type_id=%s number=%s correlation_id=%s",
            company_id,
            document_type_id,
            fiscal_number,
            self.env.context.get("korventis_correlation_id") or sequence.id,
        )
        return fiscal_number, next_number

    def find_sequence(self, company, document_type, when=None):
        when = when or fields.Date.context_today(self.env.user)
        sequences = self.env["korventis.fiscal.sequence"].search(
            [
                ("company_id", "=", company.id),
                ("document_type_id", "=", document_type.id),
                ("active", "=", True),
            ],
            order="range_start asc, id asc",
        )
        for seq in sequences:
            if seq.valid_from and when < seq.valid_from:
                continue
            if seq.valid_until and when > seq.valid_until:
                continue
            if seq.next_number < seq.range_start or seq.next_number > seq.range_end:
                continue
            return seq
        raise UserError(
            _(
                "No active fiscal sequence found for company %(company)s and type %(type)s.",
                company=company.display_name,
                type=document_type.code,
            )
        )

    def reserve_for_move(self, move):
        move.ensure_one()
        if move.korventis_fiscal_document_id:
            return move.korventis_fiscal_document_id
        if not move.company_id.korventis_fiscal_enabled:
            raise UserError(_("Fiscal core is not enabled for this company."))
        dtype = move.korventis_fiscal_document_type_id
        if not dtype:
            raise UserError(_("Select a fiscal document type on the invoice before issuing."))
        self._check_move_direction(move, dtype)
        sequence = self.find_sequence(move.company_id, dtype)
        fiscal_number, sequence_number = self.allocate(sequence)
        document = self.env["korventis.fiscal.document"].create(
            {
                "company_id": move.company_id.id,
                "move_id": move.id,
                "partner_id": move.partner_id.id,
                "document_type_id": dtype.id,
                "sequence_id": sequence.id,
                "fiscal_number": fiscal_number,
                "sequence_number": sequence_number,
                "state": "reserved",
                "currency_id": move.currency_id.id,
                "amount_untaxed": move.amount_untaxed,
                "amount_tax": move.amount_tax,
                "amount_total": move.amount_total,
            }
        )
        document._korventis_log_event(
            "reserved",
            old_value=False,
            new_value=fiscal_number,
            notes="Number reserved from sequence %s" % sequence.display_name,
        )
        move.korventis_fiscal_document_id = document
        return document

    def issue_document(self, document):
        document.ensure_one()
        if document.state == "issued":
            return document
        if document.state == "cancelled":
            raise UserError(_("A cancelled fiscal document cannot be issued."))
        if document.state != "reserved":
            raise UserError(_("Only reserved fiscal documents can be issued."))
        document.with_context(korventis_skip_immutability=True).write(
            {
                "state": "issued",
                "issue_datetime": fields.Datetime.now(),
                "amount_untaxed": document.move_id.amount_untaxed if document.move_id else document.amount_untaxed,
                "amount_tax": document.move_id.amount_tax if document.move_id else document.amount_tax,
                "amount_total": document.move_id.amount_total if document.move_id else document.amount_total,
            }
        )
        document._korventis_log_event(
            "issued",
            old_value="reserved",
            new_value="issued",
        )
        return document

    def create_and_issue_for_move(self, move):
        document = self.reserve_for_move(move)
        return self.issue_document(document)

    def cancel_document(self, document, notes=False):
        document.ensure_one()
        if document.state == "cancelled":
            return document
        old_state = document.state
        if old_state not in ("draft", "reserved", "issued"):
            raise UserError(_("This fiscal document cannot be cancelled."))
        document.with_context(korventis_skip_immutability=True).write({"state": "cancelled"})
        document._korventis_log_event(
            "cancelled",
            old_value=old_state,
            new_value="cancelled",
            notes=notes,
        )
        return document

    def _check_move_direction(self, move, dtype):
        sale_types = {"out_invoice", "out_refund", "out_receipt"}
        purchase_types = {"in_invoice", "in_refund", "in_receipt"}
        if dtype.direction == "sale" and move.move_type in purchase_types:
            raise UserError(
                _(
                    "Fiscal type %(type)s is outbound/sale and cannot be used on a vendor bill.",
                    type=dtype.code,
                )
            )
        if dtype.direction == "purchase" and move.move_type in sale_types:
            raise UserError(
                _(
                    "Fiscal type %(type)s is inbound/purchase and cannot be used on a customer invoice.",
                    type=dtype.code,
                )
            )
