-- Enlaza la tabla cruda `intervenciones` con las dimensiones y la ubicación,
-- agrega la identidad de la dependencia (institución) por fila, el enriquecimiento
-- cualitativo por LLM, y expone una vista plana.

-- 1) FKs + identidad de la institución sobre la tabla cruda.
ALTER TABLE intervenciones
    ADD COLUMN IF NOT EXISTS ubicacion_id       BIGINT REFERENCES ubicaciones (id),
    ADD COLUMN IF NOT EXISTS diagnostico_codigo TEXT   REFERENCES dim_diagnostico (codigo),
    ADD COLUMN IF NOT EXISTS prioridad_codigo   TEXT   REFERENCES dim_prioridad (codigo),
    ADD COLUMN IF NOT EXISTS hospital_id        BIGINT REFERENCES dim_hospital (id),
    -- Identidad de la dependencia: el código de comisaría se extrae de `motivo`
    -- (regex, en el transform). El `tipo_dependencia` lo infiere el LLM (atributos).
    ADD COLUMN IF NOT EXISTS codigo_comisaria   TEXT;   -- p. ej. "7A" (NULL si no se menciona)

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

-- 3) Vista plana: cruda + ubicación + derivadas (gratis) + variables del LLM.
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
    -- Derivadas determinísticas (gratis):
    substring(i.motivo from '([0-9]{1,3}) ?A[ÑN]OS')::int           AS edad,
    (i.codigo_prioridad LIKE '6 %' OR i.motivo ~* 'OFICIO JUDICIAL') AS es_oficio_judicial,
    (i.traslado OR i.destino_traslado IS NOT NULL)                   AS trasladado,
    u.lat,
    u.lon,
    -- Variables del LLM (atributos JSONB) promovidas a columnas:
    a.atributos ->> 'sexo'             AS sexo,
    a.atributos ->> 'tipo_sujeto'      AS tipo_sujeto,
    a.atributos ->> 'tipo_dependencia' AS tipo_dependencia,
    a.atributos ->> 'quien_solicita'   AS quien_solicita,
    (a.atributos ->> 'violencia_genero')::boolean       AS violencia_genero,
    (a.atributos ->> 'autolesion')::boolean             AS autolesion,
    (a.atributos ->> 'agresion_por_terceros')::boolean  AS agresion_por_terceros,
    (a.atributos ->> 'crisis_psiquiatrica')::boolean    AS crisis_psiquiatrica,
    (a.atributos ->> 'ingesta_cuerpo_extrano')::boolean AS ingesta_cuerpo_extrano,
    (a.atributos ->> 'fallecimiento')::boolean          AS fallecimiento
FROM intervenciones i
LEFT JOIN ubicaciones u ON u.id = i.ubicacion_id
LEFT JOIN intervencion_analisis a ON a.intervencion_id = i.id;
