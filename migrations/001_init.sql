-- Migrations run in filename order via `make migrate`.
-- Keep them idempotent (IF NOT EXISTS) so re-running is safe.

-- Una fila por intervención del SAME extraída de las tablas del PDF.
-- Las columnas de texto conservan el valor crudo del PDF; fecha_hora y
-- traslado son versiones parseadas para facilitar el análisis.
CREATE TABLE IF NOT EXISTS intervenciones (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha_hora         TIMESTAMP,   -- parseado de "Fecha y Hora" (d/m/aaaa h:mm)
    direccion          TEXT,        -- "Dirección"
    altura             TEXT,        -- "Altura" (suele ser numérica; "0" = sin altura)
    dependencia        TEXT,        -- "Identificación de la dependencia policial o unidad penitenciaria"
    motivo             TEXT,        -- "Motivo de Intervención" (texto libre, incluye POC / Id.Remoto)
    diagnostico        TEXT,        -- "Diagnóstico" (p. ej. "04 - TRAUMATISMO LEVE")
    traslado           BOOLEAN,     -- "Traslado (SI/NO)" -> Si=true / No=false
    destino_traslado   TEXT,        -- "Destino de Traslado"
    codigo_prioridad   TEXT,        -- "Código de prioridad/criticidad" (p. ej. "1 - ROJO")
    movil              TEXT,        -- "Móvil interveniente"
    pagina             INT,         -- página del PDF de origen (1-based)
    fila               INT          -- fila dentro de la página (1-based)
);

CREATE INDEX IF NOT EXISTS idx_intervenciones_fecha_hora ON intervenciones (fecha_hora);
CREATE INDEX IF NOT EXISTS idx_intervenciones_codigo_prioridad ON intervenciones (codigo_prioridad);
