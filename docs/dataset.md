# Dataset — Exportaciones Peruanas (SUNAT)

**Proyecto:** Detección de variaciones en el valor unitario mediante algoritmos de aprendizaje no supervisado  
**Autor:** Said Leonardo Uceda Paredes  
**Institución:** UNI — Maestría en IA  
**Actualizado:** Mayo 2026

---

## Origen y licencia

| Campo | Detalle |
|-------|---------|
| **Fuente** | SUNAT — Superintendencia Nacional de Aduanas y de Administración Tributaria |
| **Área** | Oficina Nacional de Planeamiento y Estudios Económicos (ONPEE) |
| **Régimen** | Exportación definitiva (Ley General de Aduanas — D.Leg. N° 1053) |
| **Acceso** | Datos internos institucionales — uso académico restringido a SUNAT |
| **PII / Ética** | No contiene datos personales de personas naturales. Los exportadores son personas jurídicas (RUC empresarial). No requiere anonimización adicional. |
| **Restricción** | Los datos no se publican en repositorios públicos. Solo se versionan scripts y resultados agregados. |

---

## Tamaño y formato

| Campo | Detalle |
|-------|---------|
| **Archivo fuente** | `EXPORTACIONES_LIMPIO_UTF8_SIN_ERRORES.txt` |
| **Separador** | `|` (pipe) |
| **Encoding** | UTF-8 |
| **Primera fila** | Cabecera (FIRSTROW = 2 en BULK INSERT) |
| **Periodo inicial** | 2023 (piloto) |
| **Tabla SQL** | `[DB_GEE_DW_ADUANAS].[SC_ADUANA].[exportaciones_raw]` |

> El tamaño exacto de registros se actualiza en cada carga. Consultar:
> ```sql
> EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS] @ACCION='EDA_NULOS'
> ```

---

## Variable objetivo construida

El análisis **no opera sobre los campos crudos** directamente. El SP construye tres columnas derivadas que el pipeline Python recibe:

| Columna derivada | Fórmula / Origen | Tipo SQL | Rol en el modelo |
|-----------------|-----------------|----------|-----------------|
| `NUM_SPN_R` | `CONCAT(num_partida, '-', partida)` | VARCHAR | **_R** — variable de agrupación (categoría) |
| `ANIO_C` | `CAST(anio AS INT)` | INT | **_C** — variable temporal (contexto) |
| `MTO_VALOR_UNTARIO_V` | `fob_dolar / NULLIF(peso_neto, 0)` | DECIMAL(18,6) | **_V** — variable de análisis (USD/kg) |

> La convención de sufijos `_R`, `_C`, `_V` es el contrato del pipeline: cualquier SP nuevo que respete este naming funciona automáticamente con `mvp_valores_unitarios.py`.

---

## Diccionario de datos — `exportaciones_raw`

| # | Columna | Tipo SQL | Descripción | Valores esperados | Notas de calidad |
|---|---------|----------|-------------|-------------------|-----------------|
| 1 | `num_declaracion` | VARCHAR(50) | Número de la Declaración Aduanera de Mercancías (DAM). Identifica unívocamente cada despacho de exportación. | Alfanumérico, ej. `118-2023-10-000123` | Puede haber series de un mismo despacho (ver `num_secserie`) |
| 2 | `anio` | VARCHAR(10) | Año de la declaración de exportación. Almacenado como texto; se castea a INT para el análisis. | `2020`, `2021`, `2022`, `2023` | Verificar con `EDA_NULOS` que ISNUMERIC = 1 |
| 3 | `cod_canal` | VARCHAR(10) | Código numérico del canal de control aduanero asignado al despacho. | `1`=Verde, `2`=Naranja, `3`=Rojo | Útil como variable de control en análisis de riesgo futuro |
| 4 | `canal` | VARCHAR(100) | Descripción del canal de control: Verde (sin revisión), Naranja (revisión documental), Rojo (revisión física). | `VERDE`, `NARANJA`, `ROJO` | Relacionado con `cod_canal` |
| 5 | `cod_aduamanifiesto` | VARCHAR(10) | Código de la aduana donde se registra el manifiesto de carga. | Código numérico de 3 dígitos | Relacionado con `ann_manifiesto` y `num_manifiesto` |
| 6 | `ann_manifiesto` | VARCHAR(10) | Año del manifiesto de carga asociado al despacho. | `2020`–`2024` | Puede diferir de `anio` si el embarque cruza año |
| 7 | `num_manifiesto` | VARCHAR(50) | Número del manifiesto de carga (documento de transporte internacional). | Alfanumérico | Identifica el medio de transporte (buque, avión, camión) |
| 8 | `num_partida` | VARCHAR(50) | Código de la subpartida arancelaria del Sistema Armonizado (SA). 10 dígitos en el sistema peruano. | `7108120000`, `2603000000` | Clave para el agrupamiento del análisis (`_R`) |
| 9 | `partida` | VARCHAR(100) | Descripción oficial de la subpartida arancelaria según el Arancel de Aduanas peruano. | `ORO EN LAS DEMAS FORMAS EN BRUTO`, `UVAS FRESCAS` | Complementa `num_partida` en la etiqueta `NUM_SPN_R` |
| 10 | `num_secserie` | VARCHAR(50) | Número de serie/ítem dentro de la declaración. Una DAM puede tener múltiples ítems (series). | Numérico, usualmente `1`–`N` | Junto con `num_declaracion` identifica cada línea de producto |
| 11 | `cod_aduana` | VARCHAR(10) | Código de la aduana de salida (intendencia de aduana). | `118`=Callao Marítimo, `211`=Paita, `311`=Ilo | Útil para análisis geográfico futuro |
| 12 | `aduana` | VARCHAR(200) | Nombre de la aduana de salida donde se realizó el despacho. | `INTENDENCIA DE ADUANA MARITIMA DEL CALLAO` | Descripción de `cod_aduana` |
| 13 | `fob_dolar` | VARCHAR(50) | Valor FOB (Free On Board) declarado en dólares americanos. **Variable crítica** para el cálculo del valor unitario. | Numérico positivo, ej. `125000.50` | Almacenado como VARCHAR → castear con `TRY_CAST`. Verificar nulos y no numéricos con `EDA_NULOS` |
| 14 | `peso_neto` | VARCHAR(50) | Peso neto de la mercancía en kilogramos. **Denominador** del valor unitario. | Numérico positivo, ej. `5000.000` | No puede ser 0 (división por cero). Verificar con `EDA_NULOS`. Castear con `TRY_CAST` |
| 15 | `peso_bruto` | VARCHAR(50) | Peso bruto de la mercancía en kilogramos (incluye embalaje). | Numérico positivo, siempre ≥ `peso_neto` | No se usa en el cálculo actual del valor unitario |
| 16 | `sector` | VARCHAR(200) | Código o categoría del sector económico al que pertenece el producto exportado. | `01`=Agropecuario, `02`=Pesca, `03`=Minería | Útil para segmentar el análisis por sector en sprints futuros |
| 17 | `tipo_producto` | VARCHAR(200) | Clasificación interna del tipo de producto según SUNAT. | `TRADICIONAL`, `NO TRADICIONAL` | Los productos tradicionales (minería, petróleo, pesca) tienen alta varianza en valor unitario |
| 18 | `sector_name1` | VARCHAR(200) | Nombre del sector económico de primer nivel (clasificación SUNAT). | `MINERIA`, `AGROPECUARIO`, `PESCA` | Nivel 1 de jerarquía sectorial |
| 19 | `sector_name2` | VARCHAR(200) | Nombre del sector económico de segundo nivel (subsector o división). | `COBRE Y SUS CONCENTRADOS`, `FRUTAS FRESCAS` | Nivel 2 de jerarquía sectorial; más granular que `sector_name1` |
| 20 | `descripcion_comercial` | NVARCHAR(MAX) | Descripción libre del producto declarada por el exportador. Texto no estructurado. | Texto libre, puede ser muy largo | No se usa en el modelo actual. Potencial uso futuro con NLP |

---

## Preprocesamiento aplicado

### Filtros de calidad (aplicados en el SP antes de entregar a Python)

```sql
WHERE peso_neto IS NOT NULL
  AND ISNUMERIC(peso_neto) = 1
  AND CAST(peso_neto AS DECIMAL(18, 3)) <> 0
  AND fob_dolar IS NOT NULL
  AND ISNUMERIC(fob_dolar) = 1
```

### Conversiones de tipo (aplicadas en Python)

```python
df['MTO_VALOR_UNTARIO_V'] = pd.to_numeric(df['MTO_VALOR_UNTARIO_V'], errors='coerce')
df['ANIO_C']              = pd.to_numeric(df['ANIO_C'], errors='coerce').astype('Int64')
```

### Diagnóstico de calidad

Ejecutar antes del análisis:
```sql
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS] @ACCION='EDA_NULOS'
```

Retorna: `TOTAL_REGISTROS`, `FOB_NULOS`, `FOB_NO_NUMERICO`, `PESO_CERO_O_NEG`, `PARTIDA_NULOS`, `REGISTROS_VALIDOS_VU`.

---

## Variables para análisis futuro (no usadas en Sprint 1)

| Columna | Uso potencial |
|---------|--------------|
| `cod_canal` | Variable de control: ¿los outliers tienden a estar en canal rojo? |
| `aduana` | Análisis geográfico: ¿hay aduanas con más variaciones? |
| `sector_name1` / `sector_name2` | Segmentación sectorial del análisis |
| `tipo_producto` | Separar análisis tradicional vs. no tradicional |
| `descripcion_comercial` | NLP para validar coherencia entre descripción y valor |
| `num_manifiesto` | Análisis de concentración: ¿un manifiesto agrupa outliers? |
