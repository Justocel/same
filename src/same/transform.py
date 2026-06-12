"""Transform relacional: puebla dimensiones, construye dependencias y linkea FKs.

Trabaja set-based (SQL puro vía psycopg) sobre la tabla cruda `intervenciones`.
Idempotente: re-correr no duplica (ON CONFLICT DO NOTHING) y los UPDATE se
re-aplican por dirección / código. Pensado para iterar sin re-extraer el PDF:

    make transform        # o: uv run python -m same.transform
"""

from __future__ import annotations

import logging

# Cada paso: (descripción, SQL). Se ejecutan en orden, en una transacción.
_STEPS: list[tuple[str, str]] = [
    (
        "dim_diagnostico",
        """
        INSERT INTO dim_diagnostico (codigo, nombre)
        SELECT DISTINCT split_part(diagnostico, ' - ', 1),
                        regexp_replace(diagnostico, '^[0-9]+ - ', '')
        FROM intervenciones WHERE diagnostico IS NOT NULL
        ON CONFLICT (codigo) DO NOTHING
        """,
    ),
    (
        "dim_prioridad",
        """
        INSERT INTO dim_prioridad (codigo, nombre)
        SELECT DISTINCT split_part(codigo_prioridad, ' - ', 1),
                        regexp_replace(codigo_prioridad, '^[0-9]+ - ', '')
        FROM intervenciones WHERE codigo_prioridad IS NOT NULL
        ON CONFLICT (codigo) DO NOTHING
        """,
    ),
    (
        "dim_hospital",
        """
        INSERT INTO dim_hospital (nombre)
        SELECT DISTINCT destino_traslado FROM intervenciones
        WHERE destino_traslado IS NOT NULL
        ON CONFLICT (nombre) DO NOTHING
        """,
    ),
    (
        "dependencias",
        # Un lugar por (direccion, altura). codigo_comisaria = la moda de los
        # códigos extraídos de `motivo`; tipo es una heurística provisional
        # (se refinará con el enriquecimiento por LLM).
        """
        INSERT INTO dependencias (direccion, altura, tipo, codigo_comisaria)
        SELECT direccion, altura::int,
            CASE
                WHEN bool_or(motivo ~* 'COMPLEJO|PENITENCIAR|UNIDAD [0-9]|C\\.?P\\.?F')
                    THEN 'penitenciaria'
                WHEN bool_or(motivo ~* 'COMISAR') THEN 'policial'
                ELSE 'desconocido'
            END,
            mode() WITHIN GROUP (
                ORDER BY substring(motivo from 'COMISAR[IÍ]A[ ]*([0-9]{1,2}[A-Z]?)')
            ) FILTER (WHERE motivo ~ 'COMISAR[IÍ]A[ ]*[0-9]')
        FROM intervenciones WHERE direccion IS NOT NULL
        GROUP BY direccion, altura::int
        ON CONFLICT (direccion, altura) DO NOTHING
        """,
    ),
    (
        "link diagnostico_codigo",
        "UPDATE intervenciones SET diagnostico_codigo = split_part(diagnostico, ' - ', 1)"
        " WHERE diagnostico IS NOT NULL",
    ),
    (
        "link prioridad_codigo",
        "UPDATE intervenciones SET prioridad_codigo = split_part(codigo_prioridad, ' - ', 1)"
        " WHERE codigo_prioridad IS NOT NULL",
    ),
    (
        "link hospital_id",
        "UPDATE intervenciones i SET hospital_id = h.id"
        " FROM dim_hospital h WHERE i.destino_traslado = h.nombre",
    ),
    (
        "link dependencia_id",
        "UPDATE intervenciones i SET dependencia_id = d.id"
        " FROM dependencias d WHERE i.direccion = d.direccion AND i.altura::int = d.altura",
    ),
]


def transform(conn, log: logging.Logger | None = None) -> None:
    """Ejecuta todos los pasos del transform en una transacción sobre `conn`."""
    log = log or logging.getLogger("same")
    with conn.cursor() as cur:
        for desc, sql in _STEPS:
            cur.execute(sql)
            log.info("transform  %-24s filas: %s", desc, cur.rowcount)


def main() -> None:
    from dotenv import load_dotenv

    from same.db import connect
    from same.logging_config import setup_logging

    load_dotenv()
    log = setup_logging()
    with connect() as conn:
        transform(conn, log)


if __name__ == "__main__":
    main()
