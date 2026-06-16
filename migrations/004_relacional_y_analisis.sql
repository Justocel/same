-- Enlaza la tabla cruda `intervenciones` con las dimensiones y la ubicación,
-- agrega la identidad de la dependencia (institución) por fila, el enriquecimiento
-- cualitativo por LLM, y expone una vista plana.

-- 1) FKs + identidad de la institución sobre la tabla cruda.
ALTER TABLE intervenciones
    ADD COLUMN IF NOT EXISTS ubicacion_id       BIGINT REFERENCES ubicaciones (id),
    ADD COLUMN IF NOT EXISTS diagnostico_codigo TEXT   REFERENCES dim_diagnostico (codigo),
    ADD COLUMN IF NOT EXISTS prioridad_codigo   TEXT   REFERENCES dim_prioridad (codigo),
    ADD COLUMN IF NOT EXISTS hospital_id        BIGINT REFERENCES dim_hospital (id),
    -- Identidad de la dependencia (institución), extraída de `motivo` por fila.
    -- No es una dirección: la sede canónica se resolvería con un roster externo.
    ADD COLUMN IF NOT EXISTS codigo_comisaria   TEXT,   -- p. ej. "7A" (NULL si no se menciona)
    ADD COLUMN IF NOT EXISTS tipo_dependencia   TEXT;   -- policial | penitenciaria | desconocido

CREATE INDEX IF NOT EXISTS idx_intervenciones_ubicacion ON intervenciones (ubicacion_id);
CREATE INDEX IF NOT EXISTS idx_intervenciones_codigo_comisaria ON intervenciones (codigo_comisaria);

-- 2) Enriquecimiento cualitativo (1:1 con intervenciones). Modelo híbrido:
--    las variables del LLM viven en JSONB `atributos` (flexible mientras
--    iteramos qué variables medir); `modelo`/`prompt_version` dan trazabilidad.
CREATE TABLE IF NOT EXISTS intervencion_analisis (
    intervencion_id BIGINT PRIMARY KEY REFERENCES intervenciones (id),
    atributos       JSONB NOT NULL DEFAULT '{}'::jsonb,
    modelo          TEXT,
    prompt_version  TEXT,
    analizado_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analisis_atributos ON intervencion_analisis USING GIN (atributos);

-- 3) Vista plana: intervención + ubicación (a geocodificar) + identidad de la
--    dependencia + variables cualitativas promovidas desde el JSONB.
CREATE OR REPLACE VIEW v_intervenciones AS
SELECT
    i.id,
    i.fecha_hora,
    i.direccion,
    i.altura,
    i.motivo,
    i.diagnostico,
    i.traslado,
    i.destino_traslado,
    i.codigo_prioridad,
    i.movil,
    i.pagina,
    i.fila,
    i.codigo_comisaria,
    i.tipo_dependencia,
    u.lat,
    u.lon,
    (a.atributos ->> 'violencia_genero')::boolean AS violencia_genero,
    (a.atributos ->> 'autolesion')::boolean       AS autolesion,
    (a.atributos ->> 'intento_suicidio')::boolean AS intento_suicidio,
    (a.atributos ->> 'arma_blanca')::boolean      AS arma_blanca,
    a.atributos ->> 'sexo'                         AS sexo
FROM intervenciones i
LEFT JOIN ubicaciones u ON u.id = i.ubicacion_id
LEFT JOIN intervencion_analisis a ON a.intervencion_id = i.id;
