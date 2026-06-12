-- Tablas de lookup derivadas de campos que ya vienen codificados en el PDF.
-- Se pueblan desde la tabla cruda `intervenciones` en el paso de transform
-- (INSERT ... SELECT DISTINCT), no se cargan a mano.

-- "04 - TRAUMATISMO LEVE" -> codigo "04", nombre "TRAUMATISMO LEVE"
CREATE TABLE IF NOT EXISTS dim_diagnostico (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL
);

-- "1 - ROJO" -> codigo "1", nombre "ROJO"
CREATE TABLE IF NOT EXISTS dim_prioridad (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL
);

-- destino_traslado normalizado (28 hospitales distintos en los datos actuales).
CREATE TABLE IF NOT EXISTS dim_hospital (
    id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);
