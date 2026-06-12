# Project context for Claude

**What this is:** Análisis (sandbox) de las intervenciones del SAME en unidades
penitenciarias y dependencias policiales. La fuente es un PDF de 317 páginas
(`data/raw/`) con una tabla de 10 columnas por página. El pipeline extrae esas
tablas con `pdfplumber`, las normaliza con `pandas` y las carga en Postgres.

**Run order:** `make install` → `createdb same` → `make migrate` → `make run`

**Pipeline (`src/same`):**
- `extract.py` — `extract_intervenciones(pdf_path) -> pd.DataFrame`. Recorre las
  páginas, descarta la fila de título y la de encabezado que se repiten en cada
  página, normaliza nombres de columnas y parsea `fecha_hora` y `traslado`.
- `db.py` — `connect()`: context manager sobre `psycopg` (commit/rollback).
- `__main__.py` — orquesta: extrae el PDF de `data/raw/` y carga la tabla
  `intervenciones` (truncate + insert, idempotente).

**Datos / esquema:** una sola tabla `intervenciones` (ver `migrations/001_init.sql`).
Columnas crudas del PDF + `fecha_hora` parseada, `traslado` booleano y
`pagina`/`fila` de origen.

**Conventions:**
- Secrets live in `.env` (never commit). `.env.example` documents the keys.
- Migrations are idempotent SQL (`IF NOT EXISTS`) so re-running is safe.
- Use stdlib `logging` via `same.logging_config.setup_logging()`.
- Datos crudos en `data/raw/` (versionados), derivados en `data/processed/`.
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
