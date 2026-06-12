"""Extracción de las tablas del PDF de intervenciones del SAME.

El PDF tiene una tabla por página con 10 columnas. Cada página repite una fila
de título y una de encabezado que descartamos. Cada fila de datos restante es
una intervención (pdfplumber ya agrupa las celdas multilínea).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pdfplumber

# Orden de columnas tal como aparecen en la tabla del PDF.
COLUMNS = [
    "fecha_hora",
    "direccion",
    "altura",
    "dependencia",
    "motivo",
    "diagnostico",
    "traslado",
    "destino_traslado",
    "codigo_prioridad",
    "movil",
]

_TITULO = "intervenciones del same"  # fila de título repetida en cada página
_HEADER = "fecha y hora"  # primera celda de la fila de encabezado


def _clean(cell: str | None) -> str | None:
    """Colapsa espacios/saltos de línea; cadena vacía -> None."""
    if cell is None:
        return None
    text = " ".join(cell.split())
    return text or None


def _is_noise_row(row: list[str | None]) -> bool:
    """True para las filas de título y encabezado que se repiten por página."""
    first = (row[0] or "").strip().lower()
    if first.startswith(_HEADER):
        return True
    # Título: solo la primera celda tiene contenido.
    return _TITULO in first and not any((c or "").strip() for c in row[1:])


def extract_intervenciones(pdf_path: str | Path) -> pd.DataFrame:
    """Lee todas las páginas del PDF y devuelve un DataFrame de intervenciones.

    Columnas: las de ``COLUMNS`` (texto crudo normalizado) más ``fecha_hora``
    parseada a datetime, ``traslado`` booleano, y ``pagina``/``fila`` de origen.
    """
    rows: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            fila = 0
            for table in page.extract_tables():
                for raw in table:
                    if not raw or _is_noise_row(raw):
                        continue
                    # Normaliza ancho a 10 columnas por si alguna fila viene corta.
                    cells = [_clean(c) for c in raw[:10]] + [None] * (10 - len(raw))
                    fila += 1
                    record = dict(zip(COLUMNS, cells, strict=False))
                    record["pagina"] = page_idx
                    record["fila"] = fila
                    rows.append(record)

    df = pd.DataFrame(rows, columns=[*COLUMNS, "pagina", "fila"])

    # fecha_hora: "11/5/2026 17:45" -> datetime (día primero). Inparseables -> NaT.
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"], dayfirst=True, errors="coerce")

    # traslado: "Si"/"No" -> bool (pd.NA si está vacío o no se reconoce).
    df["traslado"] = df["traslado"].map(_parse_si_no).astype("boolean")

    return df


def _parse_si_no(value: str | None) -> bool | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v.startswith("s"):
        return True
    if v.startswith("n"):
        return False
    return None
