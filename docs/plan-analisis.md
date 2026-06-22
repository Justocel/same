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

## 3. Enriquecimiento v2 (próximo batch LLM)

El `diagnostico` estructurado ya cubre lo clínico (traumatismo, respiratorio, digestivo,
psiquiátrico, etc.), así que el LLM debe capturar lo **contextual/comportamental** que el
diagnóstico NO trae. Variables a agregar (cambian el schema ⟹ otro batch ~US$2):

- **`tipo_sujeto`** (categórica: `detenido` | `personal_policial` | `civil` | `desconocido`).
  Máxima prioridad — segmenta todo.
- **`ingesta_cuerpo_extrano`** (bool): tragó hoja de afeitar / objeto / cuchilla. ~30-40
  casos detectados; habilita la hipótesis de autolesión instrumental (§5).
- (Opcional) **`caida`** (bool) y **`condicion_cronica`** (bool: diabetes/HTA/epilepsia/
  asma/HIV-TBC) — evaluar si aportan sobre `diagnostico` antes de gastar.

> Nota: las 16 variables v1 (`vars-v1`) ya corridas: `sexo`, `violencia_genero`,
> `autolesion`, `intento_suicidio`, `agresion_por_terceros`, `arma_blanca`,
> `arma_de_fuego`, `intoxicacion_sustancias`, `crisis_psiquiatrica`, `convulsiones`,
> `perdida_de_conocimiento`, `huelga_de_hambre`, `embarazo`, `menor_de_edad`,
> `multiples_pacientes`, `es_oficio_judicial`.

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
