-- Ubicaciones de intervención: un punto por (direccion, altura) distinto de la
-- tabla cruda. Es "a dónde fue el SAME" (el dato a geocodificar).
-- OJO: NO es la sede de la dependencia — la columna direccion/altura varía por
-- incidente (un mismo código de comisaría aparece con muchas direcciones). La
-- institución (comisaría/alcaidía) se identifica aparte, por fila, en
-- `intervenciones` (codigo_comisaria / tipo_dependencia). Requiere PostGIS.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS ubicaciones (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    direccion      TEXT NOT NULL,
    altura         INT  NOT NULL,           -- 0 = sin altura conocida
    lat            DOUBLE PRECISION,
    lon            DOUBLE PRECISION,
    geom           geometry(Point, 4326),   -- GeoJSON vía ST_AsGeoJSON(geom)
    geocode_fuente TEXT,                     -- p. ej. "usig"
    geocoded_at    TIMESTAMP,
    UNIQUE (direccion, altura)
);

CREATE INDEX IF NOT EXISTS idx_ubicaciones_geom ON ubicaciones USING GIST (geom);
