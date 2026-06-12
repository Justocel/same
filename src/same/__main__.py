"""Pipeline: extrae las tablas del PDF y carga la tabla `intervenciones`.

Uso:
    python -m same [ruta_al_pdf]

Si no se pasa ruta, toma el primer PDF de `data/raw/`. Si `DATABASE_URL` no
está definida, solo imprime un resumen (modo análisis sin DB).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from same.extract import COLUMNS, extract_intervenciones
from same.logging_config import setup_logging

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
DB_COLUMNS = [*COLUMNS, "pagina", "fila"]


def _find_pdf() -> Path:
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No hay PDFs en {RAW_DIR}")
    return pdfs[0]


def _log_summary(log, df: pd.DataFrame) -> None:
    log.info("intervenciones extraídas: %d", len(df))
    fechas = df["fecha_hora"].dropna()
    if not fechas.empty:
        log.info("rango de fechas: %s — %s", fechas.min(), fechas.max())
    log.info("tasa de traslado: %.1f%%", 100 * df["traslado"].mean(skipna=True))
    top = df["codigo_prioridad"].value_counts().head(6)
    log.info("prioridades más frecuentes:\n%s", top.to_string())


def _load(log, df: pd.DataFrame) -> None:
    from same.db import connect

    # NaT/NaN -> None para que psycopg los inserte como NULL.
    frame = df[DB_COLUMNS].astype(object).where(pd.notna(df[DB_COLUMNS]), None)
    records = list(frame.itertuples(index=False, name=None))
    placeholders = ", ".join(["%s"] * len(DB_COLUMNS))
    cols = ", ".join(DB_COLUMNS)
    with connect() as conn, conn.cursor() as cur:
        # CASCADE vacía también intervencion_analisis (cuelga de intervencion_id);
        # el análisis se re-deriva tras recargar la tabla cruda.
        cur.execute("TRUNCATE intervenciones RESTART IDENTITY CASCADE")
        cur.executemany(
            f"INSERT INTO intervenciones ({cols}) VALUES ({placeholders})",
            records,
        )
    log.info("cargadas %d filas en la tabla intervenciones", len(df))


def main() -> None:
    load_dotenv()  # lee DATABASE_URL / LOG_LEVEL desde .env
    log = setup_logging()
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _find_pdf()
    log.info("extrayendo %s", pdf_path.name)

    df = extract_intervenciones(pdf_path)
    _log_summary(log, df)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = PROCESSED_DIR / "intervenciones.csv"
    df.to_csv(csv_path, index=False)
    log.info("CSV escrito en %s", csv_path.relative_to(ROOT))

    if os.getenv("DATABASE_URL"):
        _load(log, df)
    else:
        log.warning("DATABASE_URL no definida — omito la carga (solo resumen)")


if __name__ == "__main__":
    main()
