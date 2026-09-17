"""Build tiny fictional DGII ZIP/CSV fixtures. Not official data."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path


HEADERS = [
    "RNC",
    "RAZÓN SOCIAL",
    "ACTIVIDAD ECONÓMICA",
    "FECHA DE INICIO OPERACIONES",
    "ESTADO",
    "RÉGIMEN DE PAGO",
]


def csv_bytes(rows, encoding="latin-1", header=None, bom=False):
    buffer = io.StringIO()
    writer = csv.writer(buffer, dialect="excel")
    writer.writerow(header or HEADERS)
    for row in rows:
        writer.writerow(row)
    text = buffer.getvalue()
    data = text.encode(encoding)
    if bom:
        data = b"\xef\xbb\xbf" + data
    return data


def write_zip(path, payload, member="padron.csv"):
    path = Path(path)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if isinstance(payload, dict):
            for name, data in payload.items():
                archive.writestr(name, data)
        else:
            archive.writestr(member, payload)
    return path


def valid_rows():
    return [
        ["131000001", "ACME SRL", "COMERCIO", "01/01/2010", "ACTIVO", "NORMAL"],
        ["012345678", "ÑAÑO & CIA, SRL", "SERVICIOS", "15/03/1999", "ACTIVO", "NORMAL"],
        ["131000002", "SUSPENDIDA SA", "INDUSTRIA", "", "SUSPENDIDO", "NORMAL"],
    ]
