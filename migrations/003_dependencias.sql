-- Dependencias policiales / unidades penitenciarias.
-- Se derivan de las combinaciones distintas de (direccion, altura) de la tabla
-- cruda. El nombre suele ser desconocido (la columna del PDF viene vacía); en
-- ese caso la etiqueta legible es "dependencia_policial_<id>" (ver vista en 004).
-- Requiere PostGIS para la columna de geometría y las consultas espaciales.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS dependencias (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre           TEXT,                    -- NULL si no se conoce
    tipo             TEXT,                    -- policial | penitenciaria | otra
    codigo_comisaria TEXT,                    -- extraído de `motivo` (p. ej. "4D")
    direccion        TEXT NOT NULL,
    altura           INT  NOT NULL,           -- 0 = sin altura conocida
    lat              DOUBLE PRECISION,
    lon              DOUBLE PRECISION,
    geom             geometry(Point, 4326),   -- GeoJSON vía ST_AsGeoJSON(geom)
    geocode_fuente   TEXT,                    -- p. ej. "usig"
    geocoded_at      TIMESTAMP,
    UNIQUE (direccion, altura)
);

CREATE INDEX IF NOT EXISTS idx_dependencias_geom ON dependencias USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_dependencias_codigo_comisaria ON dependencias (codigo_comisaria);
