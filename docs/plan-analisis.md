# Plan de análisis — Intervenciones del SAME en dependencias

> Documento vivo. Decisiones y próximos pasos del análisis, una vez que el dataset
> quedó extraído, anonimizado, geocodificado y enriquecido (ver `CLAUDE.md`).

## 0. Encuadre — qué SON estos datos (y qué NO)

**Corrección importante (no es solo población detenida).** El paciente atendido NO
siempre es un detenido. La sample y el sondeo del corpus muestran que conviven:
- **detenidos / internos / "prevenidos"** (`DETENIDO` 921, `PREVENIDO` 299, `INTERNO` 190);
- **personal policial** (oficiales, agentes) como paciente (`OFICIAL` 454, `PERSONAL` 322);
- **civiles** que denuncian o se acercan a la comisaría pidiendo asistencia (~7%);
- visitas/familiares (marginal).

⟹ **Distinguir QUIÉN es el paciente es la variable que falta y que segmenta todo el
análisis.** No se puede con regex ("COMISARIA" contamina "comisario"). Va como
variable LLM `tipo_sujeto` (ver §3). Sin esto, mezclar oficiales + detenidos + civiles
confunde cualquier conclusión sobre "salud en el encierro".

**Numeradores, no denominadores.** Tenemos *cuántas* intervenciones, no *sobre cuánta
población*. Hasta conseguir el denominador (población alojada por dependencia y período,
ver §9), **se cuenta, no se calculan tasas**.

## 1. Procedencia y marco legal (del comunicado de respuesta — `data/raw/comunicado-ley104.pdf`, local)

Respuesta a un **pedido de acceso a la información pública (Ley 104 CABA, t.c. Ley
6.764)**. Datos provistos por la Dirección General de Emergencias SAME (DGESAME), GCABA.

- **Sistemas de origen**: `SAE CAD` (Sistema de Atención de Emergencias – Despacho
  Asistido por Computadora) y `SiSEP` (Sistema Integral de Seguridad Pública), vía la
  Central Operativa / ECUES.
- **Confirma nuestro hallazgo clave**: el organismo declara que **no existe un campo
  estructurado** para el tipo de establecimiento — por eso la columna "Identificación
  de la dependencia" viene **vacía**, y la identidad del establecimiento "se encuentra
  consignada de manera no estructurada dentro del campo *Motivo de Intervención*, como
  texto libre... sin código o categoría sistémica que permita su extracción o filtrado
  automático". → **Nuestro pipeline (extraer `codigo_comisaria`/`tipo_dependencia` del
  `motivo`) hace exactamente el "análisis manual registro por registro" que el Estado
  dijo que no podía/iba a hacer.** Ese es, en sí, parte del valor del proyecto.
- **Contradicción de privacidad**: el comunicado invoca la Ley 1.845 (datos personales
  CABA) y la Ley 26.529 (derechos del paciente, datos sensibles de salud) y afirma que
  NO se brinda info que identifique pacientes. **Sin embargo, la planilla adjunta SÍ
  contenía PII** (nombres, teléfonos, POC, Id.Remoto) — que tuvimos que anonimizar. El
  organismo afirmó una protección que no cumplió.
- **Alcance del pedido**: intervenciones realizadas *en* unidades penitenciarias y
  dependencias policiales (y cualquier dependencia donde se aloje a personas demoradas/
  detenidas). La *ubicación* es la dependencia; el *paciente* varía (ver §0).
- **"En el estado en que se encuentra" (art. 5)**: el dato se entrega tal cual; el
  organismo no certifica completitud ni procesa/desagrega → **la calidad/completitud
  hay que validarla internamente** (ver §7).

## 2. Unidad de análisis

- **Ubicación de intervención** (`ubicaciones`, geocodificada): a dónde fue el SAME.
- **Dependencia/institución** (`codigo_comisaria`, `tipo_dependencia` en `intervenciones`):
  identidad, no dirección.
- **Sujeto/paciente** (`tipo_sujeto`, a crear): de quién es la atención. **Filtro
  primario** para casi todo análisis.

## 3. Enriquecimiento — plan en 3 buckets (un solo pase pago)

El `diagnostico` estructurado ya cubre lo clínico; el LLM solo captura lo
**contextual/comportamental**. Como cambiar el set LLM invalida la caché (= re-batch
completo ~US$2), se empuja todo lo posible a lo gratis y se corre **un único pase
`vars-v2`** con TODO. Tres buckets:

### Bucket 1 — LLM `vars-v2` (paga, un solo batch)
Se mantienen las v1 **excepto `es_oficio_judicial`** (pasa a regex). Categóricas:
- `sexo` (M | F | desconocido)
- **`tipo_sujeto`** (detenido | personal_policial | civil | desconocido) — segmenta todo
- **`tipo_dependencia`** (comisaria | alcaidia | unidad_penitenciaria | otra | desconocido)
  — se **mueve del heurístico de `transform.py` al LLM** (más preciso)
- **`quien_solicita`** (alcaidia | personal_policial | jefe_servicio | paciente | tercero | desconocido)

Booleanas (v1 que siguen): `violencia_genero`, `autolesion`, `intento_suicidio`,
`agresion_por_terceros`, `arma_blanca`, `arma_de_fuego`, `intoxicacion_sustancias`,
`crisis_psiquiatrica`, `convulsiones`, `perdida_de_conocimiento`, `huelga_de_hambre`,
`embarazo`, `menor_de_edad`, `multiples_pacientes`.
Booleanas nuevas:
- **`ingesta_cuerpo_extrano`** — hoja de afeitar/objeto tragado (hipótesis instrumental, §5)
- **`fallecimiento`** — muerte en custodia (raro pero crítico)
- **`motin_o_conflicto_colectivo`** — distinto de agresión individual
- **`negativa_del_paciente`** — se niega a atención/traslado
- **`condicion_cronica`** — comorbilidad de base (diabetes/HTA/HIV/epilepsia…)
- **`episodio_previo_mencionado`** — proxy de reincidencia (no podemos linkear personas)

### Bucket 2 — determinístico/regex (gratis, fuera del LLM)
- **`edad`** (int): regex `DE \d+ AÑOS` cubre la mayoría.
- **`es_oficio_judicial`**: regex literal `OFICIO JUDICIAL` → arregla la sobre-inclusión
  del LLM (14.8%) y lo saca del set pago. (Va como columna en `transform` o en la vista.)

### Bucket 3 — derivado/geográfico (gratis, SQL/PostGIS)
- **`trasladado`** = `traslado OR destino_traslado IS NOT NULL` → promover a la vista.
- **`comuna`/`barrio`** por ubicación: reverse-geocode USIG o spatial join con el polígono
  de comunas (BA Data).
- **Features de tiempo** (hora, franja, día de semana, mes, año) de `fecha_hora`.

> **Implementación pendiente al construir v2**: decidir si `tipo_dependencia` (ahora LLM)
> y `es_oficio_judicial` (ahora regex) viven como columnas en `intervenciones` o en
> `atributos`+vista; `transform.py` deja de setear `tipo_dependencia`. Bumpear
> `PROMPT_VERSION` a `vars-v2`.
>
> v1 ya corrida (16 vars): `sexo` + `violencia_genero`, `autolesion`, `intento_suicidio`,
> `agresion_por_terceros`, `arma_blanca`, `arma_de_fuego`, `intoxicacion_sustancias`,
> `crisis_psiquiatrica`, `convulsiones`, `perdida_de_conocimiento`, `huelga_de_hambre`,
> `embarazo`, `menor_de_edad`, `multiples_pacientes`, `es_oficio_judicial`.

## 4. Líneas de análisis

- **Temporal** (2022→2026): tendencia (Poisson/binomial-negativa o Mann-Kendall),
  estacionalidad, día de semana, **hora del día**. Cola de COVID en datos tempranos.
- **Por sujeto** (`tipo_sujeto`): perfil de morbilidad detenido vs policía vs civil.
- **Por dependencia/tipo**: `policial` vs `penitenciaria`; alcaidías vs comisarías.
- **Clínico**: distribución de `diagnostico`/`prioridad`; traslado por diagnóstico.
- **Cualitativo**: prevalencia de autolesión, crisis psiquiátrica, violencia entre
  internos, intoxicación → marcadores de condiciones de encierro.

## 5. Hipótesis (asociacionales, no causales)

- **Autolesión instrumental ("hoja de afeitar")**: las autolesiones / ingestas de cuerpo
  extraño tienen una **tasa de traslado anormalmente alta** porque serían un medio para
  ser trasladado al hospital y salir de la comisaría. → Cruzar `ingesta_cuerpo_extrano` /
  `autolesion` × `traslado`; comparar con la tasa de traslado basal. (N chico ~30-40 para
  ingesta → también análisis cualitativo/case-study, no solo test.)
- **Salud mental nocturna**: autolesión / crisis psiquiátrica más frecuentes de noche → χ²
  por franja horaria.
- **Condiciones de encierro**: `penitenciaria` (alojamiento prolongado) tiene más
  autolesión/violencia que `policial` (tránsito) → χ².
- **Sujeto vs cuadro**: el perfil clínico del personal policial difiere del de detenidos
  (ej. cardiovascular vs autolesión/violencia).
- Corregir por multiplicidad (FDR). Todo observacional.

## 6. Calidad de datos — hallazgos (verificado)

- **`traslado` NO es confiable como "no hubo traslado"** (confirmado):
  - 138 filas con `traslado=No` pero **con** `destino_traslado` (mal cargadas → sí se
    trasladaron); 65 con `traslado=Sí` **sin** destino (destino no completado).
  - **72.4% de los `1-ROJO` figuran sin traslado** (1665/2301) — implausible para máxima
    criticidad → fuerte subregistro del campo.
  - Validez interna OK: la tasa por diagnóstico ordena bien (POLITRAUMATISMO 70%,
    NEUROLÓGICAS 63%, PSIQUIÁTRICAS 63%, ARMA BLANCA 53% vs "OTROS" 12%) → el campo
    captura señal pero **subcuenta**.
  - **Tratamiento adoptado**: usar `trasladado = traslado OR (destino_traslado IS NOT
    NULL)` como señal de "sí se trasladó"; `No` se trata como *ambiguo*, no como "no
    trasladado" (sobre todo en casos graves). Conviene promover esta variable derivada
    a la vista.
- **Completitud temporal**: ✅ **53/53 meses presentes, sin huecos** (01/2022–05/2026;
  2026-05 parcial por corte el 11/05). Pero hay **tendencia ~3x** (de ~40-55/mes en 2022
  a ~125-160/mes en 2026) — probablemente **expansión del sistema de alcaidías CABA /
  mejor registro**, no necesariamente más morbilidad (denominador, §0).
- **`es_oficio_judicial`**: ~7% son trámites, no atención médica → filtrar para análisis
  clínico.

## 7. Clustering y análisis multifactorial

Features mayormente **binarias/categóricas** ⟹ NO K-means/PCA. Lo adecuado:
- **MCA** (Análisis de Correspondencias Múltiples) / **FAMD** (si se mezcla tiempo continuo).
- **LCA** (Latent Class Analysis) o **K-modes/K-prototypes** para tipologías.
- Dos objetivos: (a) tipología de **intervenciones**; (b) clusters de **dependencias** por
  perfil agregado.
- **Logística**: `traslado` ~ factores (cierre multifactorial); `autolesion` ~ dependencia/
  hora/tipo_sujeto. Validar con silhouette + interpretación de dominio. Exploratorio.

## 8. Visualizaciones

Serie temporal mensual (stack por prioridad) · heatmap hora×día · **mapa** de puntos +
densidad por comuna · overlays por variable (dónde se concentran crisis/autolesión) ·
barras de diagnóstico y top dependencias · **Sankey** diagnóstico→traslado→hospital ·
small multiples de prevalencia por `tipo_sujeto`/`tipo_dependencia`.

## 9. Fuentes externas (APIs / CSVs públicos)

**El faltante #1 = denominadores** (población alojada por dependencia y período) — sin
esto solo hay conteos. Probablemente requiera otro pedido Ley 104 específico a la Policía
de la Ciudad / CABA (las comisarías no publican ocupación diaria abierta).

| Fuente | Uso | Acceso |
|---|---|---|
| **BA Data** — `data.buenosaires.gob.ar` | comisarías (ubicación/jurisdicción), hospitales/efectores, barrios y comunas (polígonos) | CSV / GeoJSON descargables |
| **USIG** — `servicios.usig.buenosaires.gob.ar` | geocoding (ya usado) + reverse-geocode a comuna/barrio | API REST |
| **Georef (nacional)** — `apis.datos.gob.ar/georef` | normalización de direcciones, provincias/deptos | API REST |
| **INDEC — Censo 2022** — `indec.gob.ar` | población e indicadores por comuna CABA | CSV/XLSX |
| **SNEEP / datos.jus.gob.ar** — `datos.jus.gob.ar`, `argentina.gob.ar/justicia/.../sneep` | población penal por unidad (SPF/provincial; CABA parcial) | CSV anual / PDF |
| **Procuración Penitenciaria (PPN)** — `ppn.gov.ar` | informes de muertes/autolesiones y condiciones en encierro | PDF (extracción manual) |
| **CELS** — `cels.org.ar` | informes de condiciones de detención (triangulación cualitativa) | PDF |
| **SMN — datos abiertos** — `smn.gob.ar/descarga-de-datos` | clima histórico (hipótesis calor→agresión/crisis) | CSV |

Pendiente: confirmar el **dataset exacto y el link directo** de cada uno cuando se use
(varios son PDFs que requieren extracción, no API).

## 10. Limitaciones

- **Población mixta y sin denominador** (§0): conteos, no tasas; segmentar por `tipo_sujeto`.
- **Sesgo de registro**: solo incidentes donde se llamó al SAME y se tipeó; subregistro;
  filtrado por la decisión policial de llamar.
- **Texto libre** inconsistente (typos, abreviaturas); extracción LLM best-effort.
- **Sin outcomes** (ni diagnóstico confirmado, ni tiempo de respuesta, ni resultado/mortalidad).
- **Sin demografía** salvo `sexo`/`menor` inferidos (no edad estructurada, ni nacionalidad).
- **Anonimización (trade-off correcto)**: sin linkage de persona → no se puede estudiar
  reincidencia / paciente-frecuente.
- **Geografía = instituciones**, no salud poblacional (el punto es la dependencia).
- **Falacia ecológica** al agregar a dependencia e inferir sobre individuos.

## 11. Reflexión sobre el pedido de información pública

- **El formato es un hallazgo**: el Estado entregó un **PDF de 317 páginas** (lo menos
  usable) en vez de CSV/API. Transparencia "de cumplimiento", no "de utilidad".
- **Doble falla del organismo**: entregó PII en un documento que circuló, *y* en mal
  formato — ni privacidad ni usabilidad, pese a invocar leyes de ambas.
- **El dato existe y es granular**: el Estado SÍ registra esto; la pregunta es por qué no
  se publica proactivamente como dato abierto.
- **El Estado declaró que clasificar por tipo de establecimiento requiere "análisis manual
  registro por registro"** — que es justo lo que automatizamos. El valor cívico del
  proyecto es convertir el PDF opaco en un dataset consultable/anonimizado/geocodificado/
  enriquecido. El análisis siempre estará acotado por lo que el FOIA entregó (sin
  denominadores ni outcomes): típico de FOIA — responde "qué pasó", no "sobre qué base".

## 12. Roadmap priorizado

1. **EDA descriptivo** + verificar completitud temporal y calidad de `traslado` (§6). Rápido, sin gastar.
2. **Enriquecimiento v2**: `tipo_sujeto` (+ `ingesta_cuerpo_extrano`) — desbloquea la
   segmentación por paciente y la hipótesis instrumental.
3. **Conseguir denominadores** (otro pedido Ley 104 / SNEEP) — desbloquea tasas.
4. **MCA + LCA/K-modes** → tipología de intervenciones.
5. **Mapa + tests temporales** (noche, tendencia).
6. **Logística sobre `traslado`** como cierre multifactorial.
