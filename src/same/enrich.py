"""Enriquecimiento cualitativo de `motivo` con un LLM (Claude Haiku 4.5).

Extrae variables cualitativas estructuradas (violencia de género, autolesión,
sexo, …) de la descripción ya anonimizada, vía salida estructurada
(`output_config.format`). Usa la **Message Batches API** (50% más barata) sobre
los motivos distintos, con caché por hash en `data/cache/` (sin PII: solo guarda
las variables booleanas/categóricas, no el texto). Escribe a
`intervencion_analisis.atributos` (JSONB) con `modelo`/`prompt_version`.

    make enrich                                  # lote completo (Batches API)
    uv run python -m same.enrich --sample 8      # prueba sincrónica, sin tocar la DB

Requiere ANTHROPIC_API_KEY. Correr después de `make run && make redact-names`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from pathlib import Path

MODEL = "claude-haiku-4-5"
PROMPT_VERSION = "vars-v1"
ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "enrich.json"

# Variables a extraer. El orden/los nombres son el contrato con el JSONB.
_BOOLS = [
    "violencia_genero",
    "autolesion",
    "intento_suicidio",
    "agresion_por_terceros",
    "arma_blanca",
    "arma_de_fuego",
    "intoxicacion_sustancias",
    "crisis_psiquiatrica",
    "convulsiones",
    "perdida_de_conocimiento",
    "huelga_de_hambre",
    "embarazo",
    "menor_de_edad",
    "multiples_pacientes",
    "es_oficio_judicial",
]
_SEXO = ["M", "F", "desconocido"]

_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "sexo": {"type": "string", "enum": _SEXO},
            **{b: {"type": "boolean"} for b in _BOOLS},
        },
        "required": ["sexo", *_BOOLS],
        "additionalProperties": False,
    },
}

SYSTEM = """\
Analizás el texto de una intervención del SAME (en MAYÚSCULAS, español rioplatense)
y devolvés variables cualitativas. Marcá `true` SOLO si el texto lo indica con
claridad; ante la duda, `false`. El texto puede tener marcadores [NOMBRE]/[NUM]/[LP]
de anonimización — ignoralos.

- sexo: del paciente atendido. "M" (masculino/hombre/interno/detenido varón),
  "F" (femenino/mujer/interna), "desconocido" si no surge.
- violencia_genero: agresión en contexto de violencia de género / contra la mujer / pareja.
- autolesion: el paciente se autolesionó (cortes autoinfligidos, etc.).
- intento_suicidio: intento de quitarse la vida (ahorcamiento, etc.).
- agresion_por_terceros: lesiones por agresión de otra persona (pelea, riña, golpiza).
- arma_blanca: herida por arma blanca / corte / apuñalamiento.
- arma_de_fuego: herida por arma de fuego / disparo / bala.
- intoxicacion_sustancias: intoxicación por drogas, alcohol o sobredosis.
- crisis_psiquiatrica: crisis o brote psiquiátrico, excitación psicomotriz, salud mental aguda.
- convulsiones: episodio convulsivo / convulsiones / epilepsia.
- perdida_de_conocimiento: desmayo, inconsciencia, desvanecimiento o pérdida de conocimiento.
- huelga_de_hambre: el paciente está en huelga de hambre / no se alimenta.
- embarazo: paciente embarazada / parto / gestación.
- menor_de_edad: el paciente es menor de edad (niño/niña/adolescente, menos de 18 años).
- multiples_pacientes: la intervención involucra a más de un paciente o detenido.
- es_oficio_judicial: es un oficio o trámite judicial, no una atención médica real."""

_DEFAULT = {"sexo": "desconocido", **{b: False for b in _BOOLS}}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cache() -> dict[str, dict]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def missing_texts(distinct: list[str], cache: dict[str, dict]) -> list[str]:
    return [t for t in distinct if _hash(t) not in cache]


def _parse(message, log: logging.Logger) -> dict:
    text = "".join(b.text for b in message.content if b.type == "text")
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        log.warning("respuesta no parseable, uso default: %r", text[:80])
        return dict(_DEFAULT)


def _params(text: str) -> dict:
    return {
        "model": MODEL,
        "max_tokens": 300,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": text}],
        "output_config": {"format": _SCHEMA},
    }


def _extract_batch(client, texts: list[str], log: logging.Logger) -> dict[str, dict]:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    requests = [
        Request(custom_id=f"r{i}", params=MessageCreateParamsNonStreaming(**_params(t)))
        for i, t in enumerate(texts)
    ]
    batch = client.messages.batches.create(requests=requests)
    log.info("batch %s creado (%d requests) — esperando…", batch.id, len(texts))
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        log.info("  procesando: %s", batch.request_counts)
        time.sleep(15)

    out: dict[str, dict] = {}
    for result in client.messages.batches.results(batch.id):
        text = texts[int(result.custom_id[1:])]
        if result.result.type == "succeeded":
            out[text] = _parse(result.result.message, log)
        else:
            out[text] = dict(_DEFAULT)
    return out


def _run_sample(client, log: logging.Logger, n: int) -> None:
    from same.db import connect

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT motivo FROM intervenciones WHERE motivo IS NOT NULL "
            "ORDER BY length(motivo) DESC LIMIT %s",
            (n,),
        )
        rows = [r[0] for r in cur.fetchall()]
    for text in rows:
        msg = client.messages.create(**_params(text))
        attrs = _parse(msg, log)
        flags = ", ".join(k for k, v in attrs.items() if v is True) or "—"
        print("―" * 80)
        print("MOT :", text[:150])
        print(f"SEXO: {attrs.get('sexo')}  |  TRUE: {flags}")


def _apply(conn, cache: dict[str, dict], log: logging.Logger) -> None:
    from psycopg.types.json import Json

    with conn.cursor() as cur:
        cur.execute("SELECT id, motivo FROM intervenciones WHERE motivo IS NOT NULL")
        rows = cur.fetchall()
        cur.executemany(
            "INSERT INTO intervencion_analisis"
            " (intervencion_id, atributos, modelo, prompt_version, analizado_at)"
            " VALUES (%s, %s, %s, %s, now())"
            " ON CONFLICT (intervencion_id) DO UPDATE SET"
            " atributos = EXCLUDED.atributos, modelo = EXCLUDED.modelo,"
            " prompt_version = EXCLUDED.prompt_version, analizado_at = now()",
            [(iid, Json(cache.get(_hash(m), _DEFAULT)), MODEL, PROMPT_VERSION) for iid, m in rows],
        )
    log.info("intervencion_analisis: %d filas escritas", len(rows))


def main() -> None:
    import anthropic
    from dotenv import load_dotenv

    from same.db import connect
    from same.logging_config import setup_logging

    load_dotenv()
    log = setup_logging()
    client = anthropic.Anthropic()

    if len(sys.argv) > 2 and sys.argv[1] == "--sample":
        _run_sample(client, log, int(sys.argv[2]))
        return

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT motivo FROM intervenciones WHERE motivo IS NOT NULL")
            distinct = [r[0] for r in cur.fetchall()]
        cache = load_cache()
        pending = missing_texts(distinct, cache)
        log.info("motivos distintos: %d — sin analizar: %d", len(distinct), len(pending))
        if pending:
            for text, attrs in _extract_batch(client, pending, log).items():
                cache[_hash(text)] = attrs
            save_cache(cache)
        _apply(conn, cache, log)


if __name__ == "__main__":
    main()
