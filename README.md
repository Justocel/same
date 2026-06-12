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

1. `cp .env.example .env` and fill in `DATABASE_URL`
2. `make install`
3. `createdb same` (o el nombre que pongas en `DATABASE_URL`)
4. `make migrate`
5. `make run` — extrae el PDF de `data/raw/` y carga la tabla `intervenciones`

El PDF de origen vive en
[`data/raw/`](data/raw/intervenciones_same_unidades_penitenciarias.pdf).

## Tasks

`make lint` · `make format` · `make test` · `make migrate` · `make run`

> Pre-commit's ruff **is** the dev-group ruff (a `local` hook running
> `uv run ruff`), so it never drifts from `make lint`/`make format`. Anything
> that runs the hooks — including CI — must therefore have `uv` and run
> `uv sync` first.
