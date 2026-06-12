-- Enlaza la tabla cruda `intervenciones` con las dimensiones y la dependencia,
-- agrega el enriquecimiento cualitativo por LLM, y expone una vista plana.

-- 1) FKs sobre la tabla cruda (las columnas de texto crudas se conservan).
ALTER TABLE intervenciones
    ADD COLUMN IF NOT EXISTS dependencia_id     BIGINT REFERENCES dependencias (id),
    ADD COLUMN IF NOT EXISTS diagnostico_codigo TEXT   REFERENCES dim_diagnostico (codigo),
    ADD COLUMN IF NOT EXISTS prioridad_codigo   TEXT   REFERENCES dim_prioridad (codigo),
    ADD COLUMN IF NOT EXISTS hospital_id        BIGINT REFERENCES dim_hospital (id);

CREATE INDEX IF NOT EXISTS idx_intervenciones_dependencia ON intervenciones (dependencia_id);

-- 2) Enriquecimiento cualitativo (1:1 con intervenciones). Modelo híbrido:
--    las variables del LLM viven en JSONB `atributos` (flexible mientras
--    iteramos qué variables medir); `modelo`/`prompt_version` dan trazabilidad
--    para re-correr y comparar versiones.
CREATE TABLE IF NOT EXISTS intervencion_analisis (
    intervencion_id BIGINT PRIMARY KEY REFERENCES intervenciones (id),
    atributos       JSONB NOT NULL DEFAULT '{}'::jsonb,
    modelo          TEXT,
    prompt_version  TEXT,
    analizado_at    TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analisis_atributos ON intervencion_analisis USING GIN (atributos);

-- 3) Vista plana: intervención + dependencia + variables cualitativas ya
--    estabilizadas promovidas desde el JSONB a columnas tipadas. A medida que
--    una variable se asienta, se agrega acá (sin migrar el esquema).
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
    COALESCE(d.nombre, 'dependencia_policial_' || d.id) AS dependencia_etiqueta,
    d.codigo_comisaria,
    d.lat,
    d.lon,
    (a.atributos ->> 'violencia_genero')::boolean AS violencia_genero,
    (a.atributos ->> 'autolesion')::boolean       AS autolesion,
    (a.atributos ->> 'intento_suicidio')::boolean AS intento_suicidio,
    (a.atributos ->> 'arma_blanca')::boolean      AS arma_blanca,
    a.atributos ->> 'sexo'                         AS sexo
FROM intervenciones i
LEFT JOIN dependencias d ON d.id = i.dependencia_id
LEFT JOIN intervencion_analisis a ON a.intervencion_id = i.id;
