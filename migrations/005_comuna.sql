-- Polígonos de las 15 comunas de CABA (fuente: BA Data) para el spatial join que
-- asigna `ubicaciones.comuna`. La tabla es DDL acá; los polígonos y el join los
-- puebla `make geocode` (descarga el GeoJSON, carga dim_comuna y hace ST_Contains).
-- Requiere PostGIS (migración 003).
CREATE TABLE IF NOT EXISTS dim_comuna (
    comuna  SMALLINT PRIMARY KEY,
    barrios TEXT,
    geom    geometry(MultiPolygon, 4326)
);

CREATE INDEX IF NOT EXISTS idx_dim_comuna_geom ON dim_comuna USING GIST (geom);
