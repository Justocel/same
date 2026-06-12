# Project context for Claude

**What this is:** Análisis (sandbox) de las intervenciones del SAME en unidades
penitenciarias y dependencias policiales. La fuente es un PDF de 317 páginas
(`data/raw/`) con una tabla de 10 columnas por página. El pipeline extrae esas
tablas con `pdfplumber`, las normaliza con `pandas` y las carga en Postgres.

**Run order:** `make install` → `createdb same` → `make migrate` → `make run`.
`make run` = extraer PDF → cargar `intervenciones` cruda → transform relacional.
`make transform` re-corre solo el transform (idempotente, sin re-extraer el PDF).
Requiere **PostGIS** en el server (`CREATE EXTENSION postgis` en la migración 003).

**Pipeline (`src/same`):**
- `extract.py` — `extract_intervenciones(pdf_path) -> pd.DataFrame`. Recorre las
  páginas, descarta título/encabezado repetidos, parsea `fecha_hora` y `traslado`.
- `transform.py` — `transform(conn)`: SQL set-based idempotente. Puebla las dims,
  construye `dependencias` desde los `(direccion, altura)` distintos (extrae
  `codigo_comisaria` de `motivo` con regex; `tipo` es heurístico **provisional**),
  y linkea las FKs de `intervenciones`.
- `db.py` — `connect()`: context manager sobre `psycopg` (commit/rollback).
- `__main__.py` — orquesta extract → load (`TRUNCATE … CASCADE` + insert) →
  transform; además exporta `data/processed/intervenciones.csv`. Carga `.env` con
  `python-dotenv`. Si no hay `DATABASE_URL`, solo resume + CSV (sin DB).

**Esquema (relacional, ver `migrations/`):**
- `intervenciones` (001) — tabla cruda de aterrizaje + FKs (004): `dependencia_id`,
  `diagnostico_codigo`, `prioridad_codigo`, `hospital_id`.
- dims (002): `dim_diagnostico`, `dim_prioridad`, `dim_hospital` (split de los
  campos ya codificados; se pueblan en el transform).
- `dependencias` (003, PostGIS) — un lugar por `(direccion, altura)`; `geom`
  `Point,4326`; etiqueta `dependencia_policial_N` cuando `nombre` es NULL.
- `intervencion_analisis` (004) — 1:1, enriquecimiento LLM en `atributos` JSONB
  (modelo híbrido: variables estables se promueven a columnas en la vista).
- `v_intervenciones` (004) — vista plana que une todo.

**Privacidad / PII:** la columna `motivo` (descripción) contiene datos personales
ocasionales — nombres y apellidos, teléfonos, números POC, `Id.Remoto`. El **PDF
crudo no se versiona** (vive solo en `data/raw/`, gitignored); `data/processed/`
(CSV) también está gitignored. Poder trazar una persona a una atención en una
comisaría es el riesgo a evitar: **anonimizar `motivo` antes de exponer cualquier
dato derivado**. (El PDF estuvo brevemente en commits públicos ya purgados de la
rama; los objetos viejos pueden seguir cacheados en GitHub hasta su GC.)

**Pendiente (próximos pasos):**
- **Anonimización de `motivo`**: scrub determinístico (teléfonos, POC, `Id.Remoto`,
  DNI) por regex + redacción de nombres con NER/LLM, antes de cargar/derivar.
- Geocoding USIG (GCBA) para llenar `lat/lon/geom` de `dependencias`.
- Enriquecimiento LLM (Haiku) → `intervencion_analisis.atributos` (variables como
  `violencia_genero`, `autolesion`, `sexo`, …).

**Conventions:**
- Secrets live in `.env` (never commit). `.env.example` documents the keys.
- Migrations are idempotent SQL (`IF NOT EXISTS`) so re-running is safe.
- Use stdlib `logging` via `same.logging_config.setup_logging()`.
- `data/raw/` (PDF crudo) y `data/processed/` (CSV derivado) están **gitignored**;
  ningún dato (crudo o derivado) se versiona — ver Privacidad/PII.
- Pre-commit runs the **dev-group ruff** via a `local` hook (not a pinned
  mirror), so the hook and `make lint`/`make format` can't drift. The
  trade-off: any environment that runs the hooks — **CI included** — must have
  `uv` and the dev group installed (`uv sync`).

**Keep it legible.** This project should stay readable to someone who never
worked on it:
- No `scripts/` graveyard of 40+ one-off files. If something is worth keeping,
  give it a home in `src/same` with a clear name; if it was a throwaway, delete it.
- Prefer a few well-named modules over many tiny ones.
- A new reader should understand the pipeline from `src/same` + this file alone.

**Don't:**
- Add dependencies for things the stdlib already does.
- Optimize for scale we don't have yet.
- Add stages, abstractions, or folders no one asked for.
