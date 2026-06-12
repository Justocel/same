"""Anonimización determinística del texto libre (columna `motivo`).

Quita los identificadores estructurados que son PII de alta confianza:
- bloques `[Id.Remoto: ...]` (referencia interna del sistema),
- números largos (teléfonos, POC, DNI, Id): toda corrida de >= 7 dígitos.

Conserva los números cortos (1-4 díg.) que identifican dependencias o
direcciones (p. ej. "COMISARIA 4D", "ALCAIDIA 9", "GANA 430") y los signos
vitales (p. ej. "36.5", "120/80").

La redacción de NOMBRES/APELLIDOS NO se hace acá: el texto está en mayúsculas
(NER por casing no sirve) y es infrecuente; se delega al paso de enriquecimiento
por LLM. Se aplica en `extract.py`, antes de cargar o derivar cualquier dato.
"""

from __future__ import annotations

import re

_MIN_DIGITS = 7  # corridas con >= 7 dígitos se asumen identificadores (tel/POC/DNI/Id)

# Bloque [Id.Remoto: 48132107]. Corchetes y el nº son opcionales para tolerar
# bloques truncados al borde de celda; acotado a dígitos para no comer texto.
_ID_REMOTO = re.compile(r"\[?\s*id\.?\s*remoto\s*:?\s*[\d.\-]*\]?", re.IGNORECASE)
# Corrida de dígitos con separadores internos de teléfono (punto, guion, espacio).
# Incluye espacios porque algunos teléfonos vienen partidos: "11-2271- 2171".
_NUM_RUN = re.compile(r"\d[\d.\- ]*\d")
_MULTISPACE = re.compile(r"[ \t]{2,}")


def _redact_num(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group())
    return "[NUM]" if len(digits) >= _MIN_DIGITS else match.group()


def anonymize(text: str | None) -> str | None:
    """Devuelve `text` sin identificadores estructurados (None pasa como None)."""
    if not text:
        return text
    text = _ID_REMOTO.sub("", text)
    text = _NUM_RUN.sub(_redact_num, text)
    return _MULTISPACE.sub(" ", text).strip()
