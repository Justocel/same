"""Redacción de nombres propios en `motivo` con un LLM (Claude Haiku 4.5).

El scrub determinístico (`anonymize.py`) ya quitó la PII estructurada (teléfonos,
POC, DNI, Id.Remoto). Este paso quita lo que requiere comprensión del texto: los
NOMBRES de personas (oficiales, agentes, detenidos, internos, pacientes) y los
números de legajo policial (LP). Sobrescribe `motivo` en la base — el texto crudo
con nombres solo vive en el PDF local.

Costo/eficiencia: usa la **Message Batches API** (50% más barata) sobre los motivos
*distintos*, con caché local por hash SHA-256 en `data/cache/` para no re-llamar a
la API en re-corridas (la caché guarda solo el texto YA redactado → sin PII).

    make redact-names                                # lote completo (Batches API)
    uv run python -m same.redact_names --sample 5    # prueba sincrónica, sin tocar la DB

Requiere ANTHROPIC_API_KEY en `.env`. Flujo: `make run && make redact-names`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from pathlib import Path

MODEL = "claude-haiku-4-5"
PROMPT_VERSION = "names-v1"
ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "name_redactions.json"
CSV_PATH = ROOT / "data" / "processed" / "intervenciones.csv"

SYSTEM = """\
Sos un sistema de anonimización de datos médicos. Recibís el texto de una \
intervención del SAME (en MAYÚSCULAS, español rioplatense). Devolvé el MISMO texto \
con estos reemplazos, y NADA más:

- Todo NOMBRE de persona (nombres y apellidos de oficiales, agentes, detenidos, \
internos, pacientes o terceros) -> [NOMBRE].
- Todo número de legajo policial (p. ej. "LP 15798") -> [LP].

Reglas estrictas:
- Conservá TODO lo demás idéntico: diagnósticos, síntomas, direcciones, números de \
comisaría/alcaidía/unidad, los marcadores [NUM] existentes, mayúsculas y puntuación.
- Los cargos o títulos SIN nombre (OFICIAL, AGENTE, SR, SRA, DR, JS, ALCAIDIA, \
COMISARIA) se conservan; reemplazá solo el nombre propio que los acompaña.
- Si no hay ningún nombre, devolvé el texto EXACTAMENTE igual.

Respondé ÚNICAMENTE con el texto resultante: sin comillas, sin explicaciones, sin \
preámbulo."""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_cache() -> dict[str, str]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, str]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")


def missing_texts(distinct: list[str], cache: dict[str, str]) -> list[str]:
    """Textos distintos que todavía necesitan pasar por el LLM.

    Excluye lo ya cacheado (por hash) y lo que ya contiene `[NOMBRE]` (marca que
    solo pone el LLM): así re-correr `redact-names` sobre un `motivo` ya redactado
    —sin `make run` antes— no vuelve a lanzar el batch. El flujo es `make run`
    (repone el `motivo` determinístico) y luego `make redact-names`.
    """
    return [t for t in distinct if _hash(t) not in cache and "[NOMBRE]" not in t]


def _clean_output(text: str) -> str:
    """Quita comillas/espacios envolventes que el modelo pueda agregar."""
    out = text.strip()
    if len(out) >= 2 and out[0] == out[-1] and out[0] in "\"'":
        out = out[1:-1].strip()
    return out


def _redact_one(client, text: str) -> str:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    parts = [b.text for b in msg.content if b.type == "text"]
    return _clean_output("".join(parts)) if parts else text


def _redact_batch(client, texts: list[str], log: logging.Logger) -> dict[str, str]:
    """Redacta una lista de textos vía Batches API. Devuelve {texto: redactado}."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    requests = [
        Request(
            custom_id=f"r{i}",
            params=MessageCreateParamsNonStreaming(
                model=MODEL,
                max_tokens=400,
                system=SYSTEM,
                messages=[{"role": "user", "content": t}],
            ),
        )
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

    out: dict[str, str] = {}
    failures = 0
    for result in client.messages.batches.results(batch.id):
        idx = int(result.custom_id[1:])
        original = texts[idx]
        if result.result.type == "succeeded":
            blocks = [b.text for b in result.result.message.content if b.type == "text"]
            out[original] = _clean_output("".join(blocks)) if blocks else original
        else:
            out[original] = original  # conservá el texto ante un error (no perder dato)
            failures += 1
    if failures:
        log.warning("%d requests fallaron — se conservó el texto original en esos casos", failures)
    return out


def _export_csv(conn, log: logging.Logger) -> None:
    cols = (
        "fecha_hora, direccion, altura, dependencia, motivo, diagnostico, traslado, "
        "destino_traslado, codigo_prioridad, movil, pagina, fila"
    )
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    sql = f"COPY (SELECT {cols} FROM intervenciones ORDER BY id) TO STDOUT WITH CSV HEADER"
    with conn.cursor() as cur, CSV_PATH.open("wb") as f, cur.copy(sql) as copy:
        for chunk in copy:
            f.write(chunk)
    log.info("CSV re-exportado (anonimizado) en %s", CSV_PATH.relative_to(ROOT))


def _run_sample(client, log: logging.Logger, n: int) -> None:
    from same.db import connect

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT motivo FROM intervenciones "
            "WHERE motivo ~* 'DE NOMBRE|\\mSRA?\\.?\\M|\\mOFICIAL\\M|\\mAGENTE\\M|\\mLP \\d' "
            "LIMIT %s",
            (n,),
        )
        rows = [r[0] for r in cur.fetchall()]
    for text in rows:
        print("―" * 80)
        print("ORIG:", text)
        print("ANON:", _redact_one(client, text))


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
        log.info("motivos distintos: %d — sin redactar: %d", len(distinct), len(pending))

        if pending:
            redacted = _redact_batch(client, pending, log)
            for original, red in redacted.items():
                cache[_hash(original)] = red
            save_cache(cache)

        # Aplica la caché y pasa la salida del LLM por anonymize() como red de
        # seguridad (captura legajos/teléfonos que el LLM haya dejado pasar).
        from same.anonymize import anonymize

        updates = []
        for t in distinct:
            final = anonymize(cache.get(_hash(t), t))
            if final != t:
                updates.append((final, t))
        with conn.cursor() as cur:
            cur.executemany("UPDATE intervenciones SET motivo = %s WHERE motivo = %s", updates)
        log.info(
            "filas con nombres redactados: %d (sobre %d motivos distintos)",
            len(updates),
            len(distinct),
        )

        _export_csv(conn, log)


if __name__ == "__main__":
    main()
