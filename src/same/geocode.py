"""Geocoding de `ubicaciones` con el normalizador USIG (GCBA).

USIG es gratuito y específico para CABA. Para cada `(direccion, altura)` consulta
el endpoint, toma la primera dirección normalizada con coordenadas y guarda
`lat`/`lon`/`geom` (`Point,4326`). Caché local en `data/cache/geocode.json` (sin
PII — son direcciones públicas). Idempotente: solo geocodifica las ubicaciones que
todavía no tienen `geom`.

Las direcciones con `altura = 0` no se geocodifican (USIG no da un punto confiable
para una calle sin altura).

Además asigna `ubicaciones.comuna` por spatial join con `dim_comuna` (polígonos de
comunas de BA Data, descargados y cacheados). Todo idempotente.

    make geocode
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from pathlib import Path

USIG_URL = "https://servicios.usig.buenosaires.gob.ar/normalizar"
COMUNAS_URL = (
    "https://cdn.buenosaires.gob.ar/datosabiertos/datasets/"
    "ministerio-de-educacion/comunas/comunas.geojson"
)
ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "geocode.json"
COMUNAS_CACHE = ROOT / "data" / "cache" / "comunas_caba.geojson"
_PAUSE = 0.3  # segundos entre consultas en vivo (cortesía con el servicio público)
# Bounding box de CABA. USIG a veces resuelve calles ambiguas a un punto en GBA;
# como todas las dependencias son de CABA, descartamos lo que cae afuera.
_CABA = {"lat": (-34.71, -34.52), "lon": (-58.54, -58.33)}


def _in_caba(lat: float, lon: float) -> bool:
    return _CABA["lat"][0] <= lat <= _CABA["lat"][1] and _CABA["lon"][0] <= lon <= _CABA["lon"][1]


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def _query_usig(direccion: str) -> list[float] | None:
    """Devuelve [lat, lon] de la primera normalización con coordenadas, o None."""
    url = USIG_URL + "?" + urllib.parse.urlencode({"direccion": direccion, "geocodificar": "true"})
    req = urllib.request.Request(url, headers={"User-Agent": "same-sandbox/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    for d in data.get("direccionesNormalizadas") or []:
        c = d.get("coordenadas") or {}
        if c.get("x") and c.get("y"):
            return [float(c["y"]), float(c["x"])]  # lat, lon (y, x)
    return None


def geocode(direccion: str, altura: int, cache: dict) -> list[float] | None:
    """Geocodifica (direccion, altura) usando la caché; consulta USIG si falta.

    Devuelve [lat, lon] o None. No cachea errores de red (se reintentan).
    """
    if not direccion or altura <= 0:
        return None
    key = f"{direccion}|{altura}"
    if key in cache:
        res = cache[key]
    else:
        try:
            res = _query_usig(f"{direccion} {altura}")
        except Exception:
            return None  # error de red: no cachear, reintentar en la próxima corrida
        cache[key] = res  # cachea aciertos y misses determinísticos (None)
        time.sleep(_PAUSE)
    # Descarta mal-geocodes fuera de CABA (USIG es CABA-only).
    if res and not _in_caba(res[0], res[1]):
        return None
    return res


_UPDATE = (
    "UPDATE ubicaciones SET lat = %s, lon = %s,"
    " geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326),"
    " geocode_fuente = 'usig', geocoded_at = now() WHERE id = %s"
)


def _load_comunas(conn, log: logging.Logger) -> None:
    """Carga los polígonos de comunas (BA Data) en dim_comuna si está vacía."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM dim_comuna")
        if cur.fetchone()[0]:
            return
        if not COMUNAS_CACHE.exists():
            req = urllib.request.Request(COMUNAS_URL, headers={"User-Agent": "same-sandbox/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                COMUNAS_CACHE.write_bytes(r.read())
        gj = json.loads(COMUNAS_CACHE.read_text(encoding="utf-8"))
        for f in gj["features"]:
            p = f["properties"]
            cur.execute(
                "INSERT INTO dim_comuna (comuna, barrios, geom) VALUES"
                " (%s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))"
                " ON CONFLICT (comuna) DO NOTHING",
                (int(float(p["comuna"])), p.get("barrios"), json.dumps(f["geometry"])),
            )
    conn.commit()
    log.info("dim_comuna: %d comunas cargadas", len(gj["features"]))


def _assign_comunas(conn, log: logging.Logger) -> None:
    """Asigna `ubicaciones.comuna` por spatial join con dim_comuna. Idempotente."""
    _load_comunas(conn, log)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE ubicaciones u SET comuna = c.comuna FROM dim_comuna c"
            " WHERE u.comuna IS NULL AND u.geom IS NOT NULL AND ST_Contains(c.geom, u.geom)"
        )
        n = cur.rowcount
    conn.commit()
    log.info("comuna asignada a %d ubicaciones", n)


def run(conn, log: logging.Logger) -> None:
    cache = load_cache()
    with conn.cursor() as cur:
        cur.execute("SELECT id, direccion, altura FROM ubicaciones WHERE geom IS NULL")
        pend = cur.fetchall()
    log.info("ubicaciones a geocodificar (sin geom): %d", len(pend))

    hits = 0
    with conn.cursor() as cur:
        for i, (uid, direccion, altura) in enumerate(pend, start=1):
            res = geocode(direccion, altura, cache)
            if res:
                lat, lon = res
                cur.execute(_UPDATE, (lat, lon, lon, lat, uid))
                hits += 1
            if i % 100 == 0:
                conn.commit()
                save_cache(cache)
                log.info("  %d/%d procesadas — %d geocodificadas", i, len(pend), hits)
    conn.commit()
    save_cache(cache)
    log.info("listo: %d/%d ubicaciones geocodificadas", hits, len(pend))
    _assign_comunas(conn, log)


def main() -> None:
    from dotenv import load_dotenv

    from same.db import connect
    from same.logging_config import setup_logging

    load_dotenv()
    log = setup_logging()
    with connect() as conn:
        run(conn, log)


if __name__ == "__main__":
    main()
