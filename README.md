# same

Análisis de las **intervenciones del SAME** realizadas en unidades penitenciarias
y dependencias policiales (datos desde 01/2022). Los datos vienen en tablas dentro
de un PDF de 317 páginas; el pipeline las extrae con `pdfplumber`, las normaliza con
`pandas` y las carga en Postgres para analizarlas con SQL.

Proyecto **sandbox** — pensado para explorar y analizar, no para producción.

## Setup

> **WSL:** keep this repo under `~/`, never `/mnt/c` — disk I/O is ~10x slower there.
>
> **Postgres client required** for `make migrate` (and `createdb`): install
> the `psql`/`createdb` CLI tools (e.g. `apt install postgresql-client`).
>
> **PostGIS required** (la migración `003` hace `CREATE EXTENSION postgis`):
> `apt install postgresql-NN-postgis-3` y un rol con permiso de crear extensiones.

1. `cp .env.example .env` and fill in `DATABASE_URL` (con auth peer: `postgresql:///same`)
2. `make install`
3. `createdb same` (o el nombre que pongas en `DATABASE_URL`)
4. `make migrate`
5. `make run` — extrae el PDF, carga `intervenciones` y corre el transform relacional
6. `make redact-names` — redacta nombres de la descripción con un LLM (paso final de
   anonimización; necesita `ANTHROPIC_API_KEY` en `.env`)

`make transform` re-corre solo el transform sin re-extraer el PDF. El PDF de origen
**no se versiona** (puede contener PII en las descripciones): se coloca localmente
en [`data/raw/`](data/raw/) y `make run` toma el primer `*.pdf` que encuentre ahí.

> **Anonimización en dos capas:** `make run` ya quita la PII estructurada (teléfonos,
> POC, DNI, Id.Remoto) de forma determinística; `make redact-names` agrega la
> redacción de **nombres** con Claude Haiku 4.5 (Batches API, con caché local).

## Tasks

`make lint` · `make format` · `make test` · `make migrate` · `make run` · `make transform` · `make redact-names` · `make geocode` · `make enrich`

> `make geocode` geocodifica las `ubicaciones` (calle+altura) con el normalizador
> USIG (GCBA, gratis, CABA) → `lat/lon/geom`. `make enrich` extrae 16 variables
> cualitativas de `motivo` con Claude Haiku 4.5 → `intervencion_analisis`. Ambos
> idempotentes, con caché local, necesitan `ANTHROPIC_API_KEY` (enrich).

> Pre-commit's ruff **is** the dev-group ruff (a `local` hook running
> `uv run ruff`), so it never drifts from `make lint`/`make format`. Anything
> that runs the hooks — including CI — must therefore have `uv` and run
> `uv sync` first.
