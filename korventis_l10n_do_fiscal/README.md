# korventis_l10n_do_fiscal

Núcleo fiscal dominicano para Odoo 18 Community (Korventis Fiscal RD).

## Dependencias

- `base`
- `account`
- `l10n_do`

No depende de POS, OCA ni Enterprise.

## Qué hace (Fase 1)

- Catálogo de tipos e-CF E31–E47 (fuente DGII Formato e-CF V1.0).
- Tipo predeterminado en `res.partner` (solo tipos `partner_assignable`).
- Snapshot del tipo en `account.move` (no se recalcula si cambia el partner).
- Rangos/secuencias por compañía y tipo.
- Asignación atómica de e-NCF (`SELECT … FOR UPDATE`) con formato `E` + tipo(2) + 10 dígitos.
- Documento fiscal interno (`draft` / `reserved` / `issued` / `cancelled`).
- Eventos append-only.

## Qué no hace

POS, XML, firma, JWT, TrackID, QR, 606/607/608, contingencia, Alanube.

## Consumidor Final

Crear un partner (por ejemplo “Consumidor Final”) y asignarle el tipo **E32**. No se generan partners masivos.

## Identificación

Se reutiliza `res.partner.vat`. Si el país es DO, se exige longitud 9 (RNC) u 11 (Cédula). **No hay checksum.** [REQUIERE VALIDACIÓN DGII]

## Tests

```
odoo-bin -d <db> -i korventis_l10n_do_fiscal --test-enable --stop-after-init
```

`test_concurrent_sequence_allocation` hace `commit()` para abrir dos conexiones PostgreSQL. Ejecutar en base de pruebas.

## Licencia

Pendiente: ver `LICENSE_PENDING.md` en la raíz del repositorio.
