# Project context for Claude

**What this is:** Análisis (sandbox) de las intervenciones del SAME en unidades
penitenciarias y dependencias policiales. La fuente es un PDF de 317 páginas
(`data/raw/`) con una tabla de 10 columnas por página. El pipeline extrae esas
tablas con `pdfplumber`, las normaliza con `pandas` y las carga en Postgres.

**Run order:** `make install` → `createdb same` → `make migrate` → `make run`
→ `make redact-names`. `make run` = extraer PDF → cargar `intervenciones` cruda →
transform relacional. `make transform` re-corre solo el transform (idempotente).
`make redact-names` redacta nombres con LLM (paso final de anonimización; needs
`ANTHROPIC_API_KEY`). Requiere **PostGIS** (`CREATE EXTENSION postgis`, migración 003).

**Pipeline (`src/same`):**
- `extract.py` — `extract_intervenciones(pdf_path) -> pd.DataFrame`. Recorre las
  páginas, descarta título/encabezado repetidos, parsea `fecha_hora` y `traslado`,
  y anonimiza `motivo` (llama a `anonymize`) antes de devolver el DataFrame.
- `anonymize.py` — `anonymize(text)`: scrub determinístico de PII estructurada en
  texto libre (quita `[Id.Remoto: …]`, legajos `LP`/`LEGAJO <n>` → `[LP]`, y toda
  corrida de ≥7 dígitos → `[NUM]`: teléfonos —incluso partidos por espacio—, POC,
  DNI). Conserva números cortos (códigos de dependencia, direcciones, vitales).
  Nombres de persona → `redact_names.py`.
- `redact_names.py` — redacción de NOMBRES con Claude Haiku 4.5 vía **Batches API**
  (50% más barata) sobre los motivos distintos, con caché por hash en `data/cache/`
  (sin PII). Pasa la salida del LLM por `anonymize()` como red de seguridad (los
  legajos los garantiza esa capa, no el LLM). Sobrescribe `motivo` en la DB y
  re-exporta el CSV. `--sample N` prueba sincrónica sin tocar la DB.
  **Ojo:** corré `make redact-names` SOLO después de `make run` (sobre el `motivo`
  determinístico); un guard evita re-batchear textos que ya tienen `[NOMBRE]`.
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
comisaría es el riesgo a evitar. Dos capas, ambas implementadas:
1. **Determinística** (`anonymize.py`, en `extract.py`): el DB y el CSV no contienen
   teléfonos/POC/DNI/Id.Remoto.
2. **Nombres por LLM** (`redact_names.py`, `make redact-names`): redacta nombres de
   oficiales/detenidos y legajos. Es un paso aparte (cuesta y necesita API key); el
   flujo completo es `make run && make redact-names`. Si re-corrés `make run`, la
   capa de nombres hay que re-aplicarla — pero la caché por hash la hace instantánea
   (sin re-llamar a la API).

(El PDF estuvo brevemente en commits públicos ya purgados de la rama; los objetos
viejos pueden seguir cacheados en GitHub hasta su GC.)

**Pendiente (próximos pasos):**
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
