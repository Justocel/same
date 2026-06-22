"""Enriquecimiento cualitativo de `motivo` con un LLM (Claude Haiku 4.5).

Extrae variables cualitativas estructuradas (quién es el paciente, autolesión,
violencia, etc.) de la descripción ya anonimizada, vía salida estructurada
(`output_config.format`). Usa la **Message Batches API** (50% más barata) sobre
los motivos distintos, con caché por hash en `data/cache/` (sin PII: solo guarda
las variables, no el texto). Escribe a `intervencion_analisis.atributos` (JSONB).

La caché se versiona por `PROMPT_VERSION`: al cambiar el set de variables, la caché
vieja deja de matchear y se re-analiza todo (un set nuevo = otro batch pago).

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
PROMPT_VERSION = "vars-v2"
ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "enrich.json"

# Categóricas: nombre -> valores posibles (el PRIMERO es el default / "no surge").
_CATS = {
    "sexo": ["desconocido", "M", "F"],
    "tipo_sujeto": ["desconocido", "detenido", "personal_policial", "civil"],
    "tipo_dependencia": ["desconocido", "comisaria", "alcaidia", "unidad_penitenciaria", "otra"],
    "quien_solicita": [
        "desconocido",
        "alcaidia",
        "personal_policial",
        "jefe_servicio",
        "paciente",
        "tercero",
    ],
}

# Booleanas. El orden/los nombres son el contrato con el JSONB.
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
    # nuevas en v2 (es_oficio_judicial salió del LLM -> regex en la vista)
    "ingesta_cuerpo_extrano",
    "fallecimiento",
    "motin_o_conflicto_colectivo",
    "negativa_del_paciente",
    "condicion_cronica",
    "episodio_previo_mencionado",
]

_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            **{c: {"type": "string", "enum": vals} for c, vals in _CATS.items()},
            **{b: {"type": "boolean"} for b in _BOOLS},
        },
        "required": [*_CATS, *_BOOLS],
        "additionalProperties": False,
    },
}

SYSTEM = """\
Analizás el texto de una intervención del SAME (en MAYÚSCULAS, español rioplatense)
y devolvés variables. Marcá `true` SOLO si el texto lo indica con claridad; ante la
duda, `false`. En las categóricas, "desconocido" si no surge. El texto puede tener
marcadores [NOMBRE]/[NUM]/[LP] de anonimización — ignoralos.

Categóricas:
- sexo: del paciente. "M" (masculino/hombre/interno/detenido varón), "F" (femenino/
  mujer/interna), "desconocido".
- tipo_sujeto: QUIÉN es el paciente atendido. "detenido" (interno/preso/prevenido/
  demorado), "personal_policial" (oficial/agente/personal de la dependencia), "civil"
  (denunciante, transeúnte, persona que se acercó a pedir ayuda, familiar), "desconocido".
- tipo_dependencia: tipo de establecimiento donde ocurre. "comisaria", "alcaidia",
  "unidad_penitenciaria" (complejo/unidad penitenciaria/CPF), "otra", "desconocido".
- quien_solicita: quién pidió el SAME. "alcaidia", "personal_policial" (oficial/agente),
  "jefe_servicio" (JS), "paciente" (el propio paciente), "tercero" (familiar/otro),
  "desconocido".

Booleanas:
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
- menor_de_edad: el paciente es menor de edad (menos de 18 años).
- multiples_pacientes: la intervención involucra a más de un paciente o detenido.
- ingesta_cuerpo_extrano: ingirió/tragó un objeto o elemento corto-punzante (hoja de
  afeitar, gillette, cuchilla, pila, etc.).
- fallecimiento: constatación de muerte / óbito / paciente fallecido.
- motin_o_conflicto_colectivo: motín, riña masiva o conflicto colectivo entre varios.
- negativa_del_paciente: el paciente se niega a la atención o al traslado.
- condicion_cronica: se menciona una enfermedad crónica de base (diabetes, hipertensión,
  HIV, TBC, epilepsia, EPOC, etc.).
- episodio_previo_mencionado: el texto menciona un episodio previo o recurrente del mismo
  paciente ("nuevamente", "ya había", "reiterado")."""

_DEFAULT = {**{c: vals[0] for c, vals in _CATS.items()}, **{b: False for b in _BOOLS}}


def _key(text: str) -> str:
    """Clave de caché por (prompt_version, texto), para invalidar al cambiar el set."""
    return hashlib.sha256(f"{PROMPT_VERSION}|{text}".encode()).hexdigest()


def load_cache() -> dict[str, dict]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, dict]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def missing_texts(distinct: list[str], cache: dict[str, dict]) -> list[str]:
    return [t for t in distinct if _key(t) not in cache]


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
        "max_tokens": 400,
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
        attrs = _parse(client.messages.create(**_params(text)), log)
        cats = " ".join(f"{c}={attrs.get(c)}" for c in _CATS)
        flags = ", ".join(b for b in _BOOLS if attrs.get(b) is True) or "—"
        print("―" * 80)
        print("MOT :", text[:150])
        print(f"  {cats}")
        print(f"  TRUE: {flags}")


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
            [(iid, Json(cache.get(_key(m), _DEFAULT)), MODEL, PROMPT_VERSION) for iid, m in rows],
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

    # Conexión corta para leer los motivos: NO se mantiene abierta durante el batch
    # (una transacción idle ~1h sostendría un lock que bloquea cualquier DDL).
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT DISTINCT motivo FROM intervenciones WHERE motivo IS NOT NULL")
        distinct = [r[0] for r in cur.fetchall()]

    cache = load_cache()
    pending = missing_texts(distinct, cache)
    log.info(
        "motivos distintos: %d — sin analizar (%s): %d",
        len(distinct),
        PROMPT_VERSION,
        len(pending),
    )
    if pending:
        for text, attrs in _extract_batch(client, pending, log).items():
            cache[_key(text)] = attrs
        save_cache(cache)

    with connect() as conn:  # conexión corta para aplicar
        _apply(conn, cache, log)


if __name__ == "__main__":
    main()
