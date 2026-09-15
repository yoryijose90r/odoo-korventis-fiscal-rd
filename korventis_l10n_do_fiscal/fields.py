"""PostgreSQL BIGINT integer fields for 10-digit e-NCF counters.

Odoo 18 ``fields.Integer`` uses ``_column_type = ('int4', 'int4')``
(see odoo/fields.py). int4 cannot store 8_000_000_001.

This subclass keeps the Integer ORM type (Python ``int``, widgets, convert_to_*)
and only changes the PostgreSQL column to ``int8``. On ``-u``,
``Field.update_db_column`` converts when ``udt_name`` differs from
``column_type[0]`` via ``sql.convert_column``.
"""

from odoo import fields


class FiscalBigInt(fields.Integer):
    _column_type = ("int8", "int8")
