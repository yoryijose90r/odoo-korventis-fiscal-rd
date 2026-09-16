import base64
import csv
import datetime
import hashlib
import io
import json
import logging
import os
import pathlib
import re
import shutil
import stat
import tempfile
import zipfile
from urllib.parse import urljoin, urlparse

import requests

from odoo import _, fields
from odoo.exceptions import UserError, ValidationError

from .normalization import (
    has_unsafe_control_characters,
    normalize_identification,
    normalize_name,
)


_logger = logging.getLogger(__name__)

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024
MAX_COMPRESSION_RATIO = 25
MAX_LOGGED_ISSUES = 50
DOWNLOAD_ATTEMPTS = 3
MAX_REDIRECTS = 3
CONNECT_TIMEOUT = 15
READ_TIMEOUT = 120
REDIRECT_STATUS = {301, 302, 303, 307, 308}
CONTENT_RANGE_RE = re.compile(r"bytes (\d+)-(\d+)/(\d+|\*)$")
COPY_BATCH_SIZE = 5000
CSV_HEADERS = [
    "RNC",
    "RAZÓN SOCIAL",
    "ACTIVIDAD ECONÓMICA",
    "FECHA DE INICIO OPERACIONES",
    "ESTADO",
    "RÉGIMEN DE PAGO",
]


class DgiiRegistryImporter:
    def __init__(self, env, run):
        self.env = env
        self.run = run
        self.archive_sha256 = None
        self.stats = self._empty_stats()

    def _empty_stats(self):
        return {
            "total_rows": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "warning_count": 0,
            "duplicate_count": 0,
            "rejections": [],
            "warnings": [],
        }

    def execute(self, source_url, fallback_url=None):
        urls = [self._validate_official_url(source_url)]
        if fallback_url:
            validated_fallback = self._validate_official_url(fallback_url)
            if validated_fallback not in urls:
                urls.append(validated_fallback)
        last_error = None
        for url in urls:
            self.stats = self._empty_stats()
            self.archive_sha256 = None
            try:
                with self.env.cr.savepoint():
                    return self._execute_url(url)
            except (requests.RequestException, UserError) as exc:
                last_error = exc
                _logger.warning("DGII source failed: %s: %s", url, exc)
        raise last_error or UserError(_("No se pudo descargar el padrón DGII."))

    def _execute_url(self, source_url):
        active = self.env["korventis.dgii.rnc.version"].sudo().search(
            [("state", "=", "active"), ("source_url", "=", source_url)],
            limit=1,
        )
        path = None
        try:
            download = self._download(source_url, active)
            if download["not_modified"]:
                return {
                    "state": "unchanged",
                    "source_url": source_url,
                    "archive_sha256": active.archive_sha256,
                    "version_id": active.id,
                    "total_rows": active.record_count,
                    "accepted_count": active.record_count,
                    "rejected_count": active.rejected_count,
                    "warning_count": active.warning_count,
                    "details": _("La DGII indicó que el archivo no cambió (HTTP 304)."),
                }
            path = download["path"]
            archive_hash = self._sha256(path)
            self.archive_sha256 = archive_hash
            member = self._validate_zip(path)
            existing = self.env["korventis.dgii.rnc.version"].sudo().search(
                [("archive_sha256", "=", archive_hash)],
                limit=1,
            )
            if existing:
                self._validate_member_schema(path, member)
                if existing.state == "previous":
                    existing.action_restore_previous()
                return {
                    "state": "unchanged",
                    "source_url": source_url,
                    "archive_sha256": archive_hash,
                    "version_id": existing.id,
                    "total_rows": existing.record_count,
                    "accepted_count": existing.record_count,
                    "rejected_count": existing.rejected_count,
                    "warning_count": existing.warning_count,
                    "details": _("El SHA-256 ya corresponde a una versión importada."),
                }
            imported_at = fields.Datetime.now()
            source_filename = pathlib.PurePosixPath(
                member.filename.replace("\\", "/")
            ).name
            version = self.env["korventis.dgii.rnc.version"].sudo().create(
                {
                    "name": source_filename,
                    "state": "staging",
                    "source_url": source_url,
                    "source_filename": source_filename,
                    "source_last_modified": download.get("last_modified"),
                    "source_etag": download.get("etag"),
                    "archive_size": os.path.getsize(path),
                    "archive_sha256": archive_hash,
                    "imported_at": imported_at,
                }
            )
            self._create_staging_table()
            self._stream_to_staging(path, member, imported_at)
            self._validate_staging()
            self._insert_candidate(version)
            attachment = self._store_source_archive(version, path)
            version.write(
                {
                    "source_attachment_id": attachment.id,
                    "record_count": self.stats["accepted_count"],
                    "rejected_count": self.stats["rejected_count"],
                    "warning_count": self.stats["warning_count"],
                }
            )
            self._activate(version)
            return {
                "state": "success",
                "source_url": source_url,
                "archive_sha256": archive_hash,
                "version_id": version.id,
                "total_rows": self.stats["total_rows"],
                "accepted_count": self.stats["accepted_count"],
                "rejected_count": self.stats["rejected_count"],
                "warning_count": self.stats["warning_count"],
                "duplicate_count": self.stats["duplicate_count"],
                "details": self._details(),
            }
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    _logger.warning("Could not remove temporary DGII ZIP %s", path)

    def _validate_official_url(self, url):
        parsed = urlparse((url or "").strip())
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"dgii.gov.do", "www.dgii.gov.do"}
            or not parsed.path.lower().endswith(".zip")
            or parsed.username
            or parsed.password
        ):
            raise UserError(
                _("La URL del padrón debe ser un ZIP HTTPS del dominio oficial dgii.gov.do.")
            )
        return parsed.geturl()

    def _download(self, url, active):
        local = (
            self.env["ir.config_parameter"].sudo().get_param(
                "korventis_partner_dgii.shared_archive_path",
                "",
            )
            or ""
        ).strip()
        if local:
            return self._copy_shared_archive(local)
        descriptor, path = tempfile.mkstemp(prefix="korventis-dgii-", suffix=".zip")
        os.close(descriptor)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; "
                "Korventis-Odoo-DGII-Registry/1.0)"
            ),
            "Accept": "application/zip, application/octet-stream",
            "Referer": "https://dgii.gov.do/herramientas/consultas/Paginas/RNC.aspx",
        }
        if active:
            if active.source_etag:
                headers["If-None-Match"] = active.source_etag
            if active.source_last_modified:
                headers["If-Modified-Since"] = active.source_last_modified
        try:
            last_error = None
            for attempt in range(DOWNLOAD_ATTEMPTS):
                offset = os.path.getsize(path)
                request_headers = dict(headers)
                if offset:
                    request_headers.pop("If-None-Match", None)
                    request_headers.pop("If-Modified-Since", None)
                    request_headers["Range"] = "bytes=%s-" % offset
                try:
                    with self._request_download(url, request_headers) as response:
                        if response.status_code == 304 and active:
                            os.unlink(path)
                            return {"not_modified": True, "path": None}
                        if response.status_code == 416 and offset:
                            with open(path, "wb"):
                                pass
                            raise requests.RequestException(
                                "HTTP 416: se reinicia la descarga desde el inicio"
                            )
                        if response.status_code not in (200, 206):
                            response.raise_for_status()
                            raise UserError(
                                _("Respuesta HTTP inesperada de DGII: %s")
                                % response.status_code
                            )
                        if offset and response.status_code == 200:
                            offset = 0
                        if response.status_code == 206:
                            range_start = self._content_range_start(response)
                            if range_start != offset:
                                raise requests.RequestException(
                                    "Content-Range no coincide con el desplazamiento local"
                                )
                        mode = "ab" if offset and response.status_code == 206 else "wb"
                        expected = self._expected_download_size(response, offset)
                        if expected and expected > MAX_ARCHIVE_BYTES:
                            raise UserError(_("El ZIP DGII supera el tamaño máximo permitido."))
                        with open(path, mode) as output:
                            for chunk in response.iter_content(chunk_size=1024 * 1024):
                                if not chunk:
                                    continue
                                output.write(chunk)
                                if output.tell() > MAX_ARCHIVE_BYTES:
                                    raise UserError(
                                        _("El ZIP DGII supera el tamaño máximo permitido.")
                                    )
                        actual = os.path.getsize(path)
                        if expected and actual != expected:
                            raise requests.RequestException(
                                "Descarga incompleta: %s de %s bytes"
                                % (actual, expected)
                            )
                        return {
                            "not_modified": False,
                            "path": path,
                            "etag": response.headers.get("ETag"),
                            "last_modified": response.headers.get("Last-Modified"),
                        }
                except requests.RequestException as exc:
                    last_error = exc
                    if attempt + 1 == DOWNLOAD_ATTEMPTS:
                        raise
            raise last_error
        except Exception:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise

    def _copy_shared_archive(self, local):
        source = pathlib.Path(local)
        if not source.is_absolute():
            raise UserError(
                _("La ruta del archivo compartido DGII debe ser absoluta.")
            )
        resolved = source.resolve()
        if resolved.suffix.lower() != ".zip" or not resolved.is_file():
            raise UserError(
                _("El archivo compartido DGII debe ser un ZIP existente.")
            )
        size = resolved.stat().st_size
        if size <= 0 or size > MAX_ARCHIVE_BYTES:
            raise UserError(_("El ZIP compartido supera el tamaño máximo permitido."))
        descriptor, path = tempfile.mkstemp(prefix="korventis-dgii-", suffix=".zip")
        os.close(descriptor)
        try:
            shutil.copyfile(resolved, path)
        except OSError:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
        return {
            "not_modified": False,
            "path": path,
            "etag": False,
            "last_modified": False,
        }

    def _request_download(self, url, headers):
        current_url = url
        for _redirect in range(MAX_REDIRECTS + 1):
            current_url = self._validate_official_url(current_url)
            response = requests.get(
                current_url,
                headers=headers,
                stream=True,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=False,
            )
            if response.status_code not in REDIRECT_STATUS:
                return response
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise UserError(_("La DGII redirigió sin un destino válido."))
            current_url = urljoin(current_url, location)
        raise UserError(_("La DGII excedió el número de redirecciones permitidas."))

    def _content_range_start(self, response):
        parsed = self._parse_content_range(response)
        return parsed[0] if parsed else None

    def _parse_content_range(self, response):
        header = (response.headers.get("Content-Range") or "").strip()
        match = CONTENT_RANGE_RE.match(header)
        if not match:
            return None
        total = match.group(3)
        return (
            int(match.group(1)),
            int(match.group(2)),
            int(total) if total.isdigit() else None,
        )

    def _expected_download_size(self, response, offset):
        parsed = self._parse_content_range(response)
        if parsed and parsed[2] is not None:
            return parsed[2]
        content_length = response.headers.get("Content-Length")
        if content_length and content_length.isdigit():
            return offset + int(content_length)
        return None

    def _sha256(self, path):
        digest = hashlib.sha256()
        with open(path, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _validate_zip(self, path):
        if not zipfile.is_zipfile(path):
            raise UserError(_("El archivo descargado no es un ZIP válido."))
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise UserError(_("El ZIP DGII debe contener exactamente un archivo de datos."))
            member = members[0]
            pure_name = pathlib.PurePosixPath(member.filename.replace("\\", "/"))
            mode = member.external_attr >> 16
            suffix = pure_name.suffix.lower()
            allowed_path = (
                suffix == ".csv" and len(pure_name.parts) == 1
            ) or (
                tuple(part.lower() for part in pure_name.parts)
                == ("tmp", "dgii_rnc.txt")
            )
            if (
                member.is_dir()
                or pure_name.is_absolute()
                or ".." in pure_name.parts
                or not allowed_path
                or stat.S_ISLNK(mode)
                or member.flag_bits & 0x1
            ):
                raise UserError(_("El ZIP DGII contiene una ruta o miembro no permitido."))
            if suffix not in {".csv", ".txt"}:
                raise UserError(_("El ZIP DGII no contiene un CSV/TXT reconocido."))
            ratio = member.file_size / max(member.compress_size, 1)
            if (
                member.file_size <= 0
                or member.file_size > MAX_UNCOMPRESSED_BYTES
                or ratio > MAX_COMPRESSION_RATIO
            ):
                raise UserError(_("El contenido descomprimido del ZIP no es razonable."))
            if archive.testzip() is not None:
                raise UserError(_("El ZIP DGII está corrupto."))
            return member

    def _validate_member_schema(self, path, member):
        iterator = self._iter_rows(path, member)
        try:
            next(iterator)
        except StopIteration as exc:
            raise UserError(_("El archivo DGII está vacío.")) from exc

    def _create_staging_table(self):
        self.env.cr.execute("DROP TABLE IF EXISTS pg_temp.korventis_dgii_stage")
        self.env.cr.execute(
            """
            CREATE TEMP TABLE korventis_dgii_stage (
                source_line bigint NOT NULL,
                rnc text NOT NULL,
                rnc_normalizado text NOT NULL,
                razon_social text NOT NULL,
                razon_social_normalizada text NOT NULL,
                actividad_economica text,
                fecha_inicio_operaciones date,
                estado text NOT NULL,
                regimen_pago text NOT NULL,
                fecha_importacion timestamp NOT NULL
            ) ON COMMIT DROP
            """
        )

    def _stream_to_staging(self, path, member, imported_at):
        buffer = io.StringIO()
        writer = csv.writer(
            buffer,
            delimiter="\t",
            quotechar='"',
            lineterminator="\n",
        )
        batch_count = 0
        for source_line, row in self._iter_rows(path, member):
            self.stats["total_rows"] += 1
            parsed = self._validate_row(source_line, row)
            if not parsed:
                continue
            writer.writerow(
                [
                    source_line,
                    parsed["rnc"],
                    parsed["rnc_normalizado"],
                    parsed["razon_social"],
                    parsed["razon_social_normalizada"],
                    parsed["actividad_economica"] or "",
                    parsed["fecha_inicio_operaciones"] or "",
                    parsed["estado"],
                    parsed["regimen_pago"],
                    fields.Datetime.to_string(imported_at),
                ]
            )
            self.stats["accepted_count"] += 1
            batch_count += 1
            if batch_count >= COPY_BATCH_SIZE:
                self._copy_buffer(buffer)
                buffer = io.StringIO()
                writer = csv.writer(
                    buffer,
                    delimiter="\t",
                    quotechar='"',
                    lineterminator="\n",
                )
                batch_count = 0
        if batch_count:
            self._copy_buffer(buffer)

    def _copy_buffer(self, buffer):
        buffer.seek(0)
        self.env.cr.copy_expert(
            """
            COPY korventis_dgii_stage (
                source_line, rnc, rnc_normalizado, razon_social,
                razon_social_normalizada, actividad_economica,
                fecha_inicio_operaciones, estado, regimen_pago,
                fecha_importacion
            )
            FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '', QUOTE '"')
            """,
            buffer,
        )

    def _iter_rows(self, path, member):
        if member.filename.lower().endswith(".csv"):
            yield from self._iter_csv_rows(path, member)
        else:
            yield from self._iter_txt_rows(path, member)

    def _iter_csv_rows(self, path, member):
        with zipfile.ZipFile(path) as archive, archive.open(member) as binary:
            with io.TextIOWrapper(
                binary,
                encoding="latin-1",
                errors="strict",
                newline="",
            ) as text:
                reader = csv.reader(text, dialect="excel", strict=True)
                try:
                    header = next(reader)
                except StopIteration as exc:
                    raise UserError(_("El CSV DGII está vacío.")) from exc
                except csv.Error as exc:
                    raise UserError(_("El encabezado CSV DGII es inválido.")) from exc
                if [value.strip() for value in header] != CSV_HEADERS:
                    raise UserError(_("Las columnas del CSV DGII no son las esperadas."))
                try:
                    for row in reader:
                        yield reader.line_num, row
                except csv.Error as exc:
                    raise UserError(
                        _("El CSV DGII está truncado o tiene comillas inválidas.")
                    ) from exc

    def _iter_txt_rows(self, path, member):
        with zipfile.ZipFile(path) as archive, archive.open(member) as binary:
            for line_number, raw_line in enumerate(binary, 1):
                line = raw_line.rstrip(b"\r\n")
                if not line:
                    continue
                pipe_count = line.count(b"|")
                if pipe_count != 10 or len(line) > 4096:
                    self._reject(
                        line_number,
                        _("Registro TXT truncado o con separadores inesperados."),
                    )
                    self.stats["total_rows"] += 1
                    continue
                columns = line.decode("latin-1").split("|")
                yield line_number, [
                    columns[0],
                    columns[1],
                    columns[3],
                    columns[8],
                    columns[9],
                    columns[10],
                ]

    def _validate_row(self, source_line, row):
        if len(row) != 6:
            self._reject(source_line, _("Cantidad de columnas distinta de seis."))
            return None
        values = [(value or "").strip() for value in row]
        rnc, name, activity, date_value, status, regime = values
        normalized_rnc = normalize_identification(rnc)
        if (
            not normalized_rnc.isdigit()
            or len(normalized_rnc) not in (9, 11)
            or normalized_rnc != rnc
        ):
            self._reject(source_line, _("RNC/cédula inválido o con longitud no admitida."))
            return None
        if not name or not status or not regime:
            self._reject(source_line, _("Falta razón social, estado o régimen de pago."))
            return None
        if any(has_unsafe_control_characters(value) for value in values):
            # 0x90 is a C1 control in Latin-1 and is undefined in cp1252.
            # Stripping it would invent a different name, so the row is rejected
            # while the original ZIP remains attached to the imported version.
            self._reject(
                source_line,
                _("El registro contiene caracteres de control inseguros."),
            )
            return None
        normalized_name = normalize_name(name)
        if not normalized_name:
            self._reject(source_line, _("La razón social no puede normalizarse de forma segura."))
            return None
        parsed_date = None
        if date_value:
            try:
                parsed_date = datetime.datetime.strptime(
                    date_value,
                    "%d/%m/%Y",
                ).date()
            except ValueError:
                self._warn(
                    source_line,
                    _("Fecha de inicio inválida; se importará como fecha vacía."),
                )
        return {
            "rnc": rnc,
            "rnc_normalizado": normalized_rnc,
            "razon_social": name,
            "razon_social_normalizada": normalized_name,
            "actividad_economica": activity or None,
            "fecha_inicio_operaciones": (
                fields.Date.to_string(parsed_date) if parsed_date else None
            ),
            "estado": status,
            "regimen_pago": regime,
        }

    def _reject(self, line, reason):
        self.stats["rejected_count"] += 1
        if len(self.stats["rejections"]) < MAX_LOGGED_ISSUES:
            self.stats["rejections"].append({"line": line, "reason": str(reason)})

    def _warn(self, line, reason):
        self.stats["warning_count"] += 1
        if len(self.stats["warnings"]) < MAX_LOGGED_ISSUES:
            self.stats["warnings"].append({"line": line, "reason": str(reason)})

    def _validate_staging(self):
        if not self.stats["total_rows"] or not self.stats["accepted_count"]:
            raise ValidationError(_("El padrón DGII no contiene registros válidos."))
        self.env.cr.execute(
            """
            SELECT count(*) - count(DISTINCT rnc)
              FROM korventis_dgii_stage
            """
        )
        self.stats["duplicate_count"] = int(self.env.cr.fetchone()[0])
        if self.stats["duplicate_count"]:
            raise ValidationError(_("El padrón DGII contiene identificadores duplicados."))
        parameters = self.env["ir.config_parameter"].sudo()
        minimum = int(
            parameters.get_param(
                "korventis_partner_dgii.minimum_records",
                "100000",
            )
        )
        if self.stats["accepted_count"] < minimum:
            raise ValidationError(
                _("El volumen válido del padrón es menor que el mínimo configurado.")
            )
        maximum_rejections = max(100, int(self.stats["total_rows"] * 0.001))
        if self.stats["rejected_count"] > maximum_rejections:
            raise ValidationError(_("El padrón excede el límite de filas rechazadas."))
        active = self.env["korventis.dgii.rnc.version"].sudo().search(
            [("state", "=", "active")],
            limit=1,
        )
        if active and active.record_count:
            ratio = self.stats["accepted_count"] / active.record_count
            minimum_ratio = float(
                parameters.get_param(
                    "korventis_partner_dgii.minimum_volume_ratio",
                    "0.70",
                )
            )
            maximum_ratio = float(
                parameters.get_param(
                    "korventis_partner_dgii.maximum_volume_ratio",
                    "1.30",
                )
            )
            if not minimum_ratio <= ratio <= maximum_ratio:
                raise ValidationError(
                    _("El volumen difiere excesivamente de la versión activa.")
                )

    def _insert_candidate(self, version):
        self.env.cr.execute(
            """
            INSERT INTO korventis_dgii_rnc (
                rnc, rnc_normalizado, razon_social,
                razon_social_normalizada, actividad_economica,
                fecha_inicio_operaciones, estado, regimen_pago,
                fecha_importacion, version_padron_id,
                create_uid, write_uid, create_date, write_date
            )
            SELECT rnc, rnc_normalizado, razon_social,
                   razon_social_normalizada, actividad_economica,
                   fecha_inicio_operaciones, estado, regimen_pago,
                   fecha_importacion, %s,
                   %s, %s,
                   (now() AT TIME ZONE 'UTC'),
                   (now() AT TIME ZONE 'UTC')
              FROM korventis_dgii_stage
            """,
            (version.id, self.env.uid, self.env.uid),
        )
        if self.env.cr.rowcount != self.stats["accepted_count"]:
            raise ValidationError(_("La copia desde staging quedó incompleta."))
        self.env["korventis.dgii.rnc"].invalidate_model()

    def _store_source_archive(self, version, path):
        with open(path, "rb") as source:
            encoded = base64.b64encode(source.read())
        return self.env["ir.attachment"].sudo().create(
            {
                "name": version.source_filename + ".zip",
                "type": "binary",
                "datas": encoded,
                "mimetype": "application/zip",
                "res_model": version._name,
                "res_id": version.id,
            }
        )

    def _activate(self, version):
        Version = self.env["korventis.dgii.rnc.version"].sudo()
        previous_active = Version.search([("state", "=", "active")])
        if len(previous_active) > 1:
            raise ValidationError(_("Existe más de una versión activa del padrón."))
        now = fields.Datetime.now()
        if previous_active:
            previous_active.write({"state": "previous"})
        version.write({"state": "active", "activated_at": now})
        obsolete = Version.search(
            [
                ("state", "=", "previous"),
                ("id", "!=", previous_active.id if previous_active else 0),
            ],
            order="activated_at desc, imported_at desc, id desc",
        )
        for old_version in obsolete:
            attachment = old_version.source_attachment_id
            old_version.unlink()
            if attachment:
                attachment.unlink()

    def _details(self):
        return json.dumps(
            {
                "rejections": self.stats["rejections"],
                "warnings": self.stats["warnings"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
