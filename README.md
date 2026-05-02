# Detección de variaciones en el valor unitario mediante algoritmos de aprendizaje no supervisado en las exportaciones peruanas

**Autor:** Said Leonardo Uceda Paredes  
**Programa:** Maestría en Ciencias con mención en Inteligencia Artificial  
**Institución:** Universidad Nacional de Ingeniería — Unidad de Posgrado FIIS  
**Lugar de desarrollo:** SUNAT — Oficina Nacional de Planeamiento y Estudios Económicos  
**Periodo:** Julio 2025 – Julio 2026

---

## Descripción del proyecto

Sistema analítico basado en aprendizaje no supervisado para detectar variaciones atípicas en el **valor unitario de exportaciones peruanas** (USD/kg = FOB / Peso Neto) por subpartida arancelaria.

El sistema identifica registros con valores unitarios inusuales usando un **ensemble de 7 indicadores** (estadísticos + modelos IA). Un registro se marca como outlier cuando al menos 2 de los 7 indicadores lo detectan.

```
INGESTA (SQL Server)
    ↓
CLASIFICACIÓN de columnas (_R categoría · _C temporal · _V valor)
    ↓
CORE 1 — Indicadores estadísticos:  IQR · Z-Score · Z-Score Robusto
    ↓
CORE 2 — Modelos IA:  Isolation Forest · LOF · DBSCAN · HBOS
    ↓
ANÁLISIS FINAL — ES_OUTLIER (≥ 2 de 7 indicadores)
    ↓
ENTREGABLE 1: tabla de outliers por registro
ENTREGABLE 2: catálogo MIN/MAX por partida arancelaria
```

---

## Estructura del proyecto

```
TESIS_2/
├── README.md                              ← Este archivo
├── mvp_valores_unitarios.py               ← Pipeline principal (ejecutable)
├── pruebas_mvp.py                         ← Suite de pruebas (5 pruebas)
├── sp_valores_unitarios.sql               ← SP central + queries EDA
├── ESTRUCTURA_PROYECTO.TXT               ← Mapa completo de rutas
│
├── notebooks/
│   └── 01_eda/
│       └── eda_valores_unitarios.ipynb   ← Entregable 3: EDA + Baseline
│
└── docs/
    ├── MI_TESIS.TXT                      ← Borrador de tesis
    ├── GUIA_RESMUEN_SEMANAL.TXT          ← Plan de entregables
    ├── ENTREGABLES_SEMANALES.TXT         ← Criterios del profesor
    ├── EXAMEN_PARCIAL.TXT                ← Plantilla informe
    └── REFERENCIA_COMPAÑERO.TXT          ← Referencia de proyecto similar
```

---

## Dataset

| Campo | Descripción |
|-------|-------------|
| **Origen** | SUNAT — Declaraciones Aduaneras de Mercancías (DAM), régimen exportación definitiva |
| **Base de datos** | `DB_GEE_DW_ADUANAS` — SQL Server local |
| **Tabla raw** | `[SC_ADUANA].[exportaciones_raw]` |
| **Periodo inicial** | 2023 (análisis piloto) |
| **Variable objetivo** | `MTO_VALOR_UNTARIO_V` = `fob_dolar / peso_neto` (USD/kg) |
| **Variable de agrupación** | `NUM_SPN_R` = `NUM_PARTIDA + '-' + PARTIDA` |
| **Variable temporal** | `ANIO_C` = año de la declaración |

### Campos originales de exportaciones_raw

| Columna | Tipo SQL | Descripción |
|---------|----------|-------------|
| `num_declaracion` | VARCHAR(50) | Número de la declaración aduanera |
| `anio` | VARCHAR(10) | Año de exportación |
| `cod_canal` | VARCHAR(10) | Código de canal aduanero |
| `canal` | VARCHAR(100) | Descripción del canal |
| `num_partida` | VARCHAR(50) | Código de subpartida arancelaria |
| `partida` | VARCHAR(100) | Descripción de la partida |
| `fob_dolar` | VARCHAR(50) | Valor FOB en dólares (origen: VARCHAR → cast DECIMAL) |
| `peso_neto` | VARCHAR(50) | Peso neto en kg (origen: VARCHAR → cast DECIMAL) |
| `peso_bruto` | VARCHAR(50) | Peso bruto en kg |
| `sector` | VARCHAR(200) | Sector económico |
| `tipo_producto` | VARCHAR(200) | Tipo de producto |
| `aduana` | VARCHAR(200) | Aduana de salida |
| `descripcion_comercial` | NVARCHAR(MAX) | Descripción comercial del producto |

---

## Instalación

### Requisitos previos
- Python 3.10+
- SQL Server (local) con instancia SQLEXPRESS habilitada en TCP
- ODBC Driver 17 for SQL Server

### Instalar dependencias

```bash
pip install numpy pandas sqlalchemy pyodbc scikit-learn pyod matplotlib seaborn
```

### Variables de conexión

Editar en `mvp_valores_unitarios.py`:

```python
SERVIDOR   = r"DESKTOP-OGU19A7\SQLEXPRESS,56878"
BASE_DATOS = "DB_GEE_DW_ADUANAS"
ESQUEMA    = "SC_ADUANA"
```

---

## Ejecución

### 1. Cargar datos raw en SQL Server

```sql
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS]
    @ACCION       = 'INGESTA',
    @RUTA_ARCHIVO = 'C:\ruta\EXPORTACIONES_LIMPIO_UTF8_SIN_ERRORES.txt'
```

### 2. Ejecutar el pipeline de detección

```bash
python mvp_valores_unitarios.py
```

Parámetros configurables al inicio del script:

```python
COD_ANALISIS = "ANA1"         # código del análisis
FEC_INI      = "2023-01-01"   # fecha inicio
FEC_FIN      = "2023-12-31"   # fecha fin
```

### 3. Ejecutar pruebas

```bash
python pruebas_mvp.py                    # todas las pruebas (sin BD)
python pruebas_mvp.py --prueba1          # diagnóstico de conexión
python pruebas_mvp.py --prueba2          # modelos con datos sintéticos
python pruebas_mvp.py --prueba4          # flujo completo sin BD
python pruebas_mvp.py --prueba5 --cod ANA1 --ini 2023 --fin 2023
```

### 4. Consultar resultados en SQL Server

```sql
-- Todos los registros analizados
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS] @ACCION='ANALISIS_TODOS', @COD_ANALISIS='ANA1'

-- Solo outliers
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS] @ACCION='ANALISIS_OUTLIERS', @COD_ANALISIS='ANA1'

-- Resumen por partida
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS] @ACCION='ANALISIS_RESUMEN', @COD_ANALISIS='ANA1'

-- EDA: calidad de datos
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS] @ACCION='EDA_NULOS'

-- EDA: distribución temporal
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS] @ACCION='EDA_TEMPORAL'
```

---

## Outputs generados

El pipeline produce dos entregables por ejecución:

| Archivo / Tabla | Descripción |
|----------------|-------------|
| `TANA1.txt` | Entregable 1: cada registro con sus 7 indicadores y ES_OUTLIER |
| `TANA1_CATALOGO.txt` | Entregable 2: límites MIN/MAX por partida arancelaria |
| `[SC_ADUANA].[TANA1]` | Tabla SQL: resultados cargados en SQL Server |
| `[SC_ADUANA].[TANA1_CATALOGO]` | Tabla SQL: catálogo de límites |

### Estructura del Entregable 1

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `NUM_SPN_R` | VARCHAR | Partida arancelaria |
| `ANIO_C` | INT | Año |
| `MTO_VALOR_UNTARIO_V` | DECIMAL(18,6) | Valor unitario (USD/kg) |
| `IND_IQR` | TINYINT | 1 = outlier por IQR |
| `IND_ZSCORE` | TINYINT | 1 = outlier por Z-Score clásico |
| `IND_ZSCORE_ROB` | TINYINT | 1 = outlier por Z-Score robusto (MAD) |
| `IND_IFOREST` | TINYINT | 1 = outlier por Isolation Forest |
| `IND_LOF` | TINYINT | 1 = outlier por LOF |
| `IND_DBSCAN` | TINYINT | 1 = outlier por DBSCAN |
| `IND_HBOS` | TINYINT | 1 = outlier por HBOS |
| `ES_OUTLIER` | TINYINT | 1 = outlier confirmado (≥2 de 7) |

---

## Indicadores del ensemble

| Indicador | Tipo | Umbral | Mín. registros |
|-----------|------|--------|----------------|
| **IQR** | Estadístico | Q1 − 1.5×IQR · Q3 + 1.5×IQR | 1 |
| **Z-Score clásico** | Estadístico | \|z\| > 3 | 2 |
| **Z-Score robusto (MAD)** | Estadístico | \|z_rob\| > 3.5 | 2 |
| **Isolation Forest** | Árbol | contamination=0.05 | 2 |
| **LOF** | Densidad | n_neighbors=min(20,N-1), contamination=0.05 | 2 |
| **DBSCAN** | Densidad | eps=0.5 (RobustScaler), min_samples=3 | 4 |
| **HBOS** | Histograma | n_bins=min(10,N//3), contamination=0.05 | 2 |

**Decisión final:** `ES_OUTLIER = 1` si `suma_indicadores ≥ 2`

---

## Métricas de evaluación (Entregable 3)

Para detección de outliers no supervisada se evalúa con **datos sintéticos con ground truth conocido**:

- **Métrica principal:** F1-Score
- **Métricas secundarias:** Precision, Recall, ROC-AUC
- **Baseline:** IQR solo (modelo más simple, sin hiperparámetros)

Ver resultados completos en: `notebooks/01_eda/eda_valores_unitarios.ipynb`

---

## Sprint actual

| Sprint | Semana | Estado | Entregable |
|--------|--------|--------|------------|
| 1 | 1-2 | ✓ Completado | Pipeline mínimo reproducible |
| 1 | 3 | ✓ Completado | EDA + Baseline (`eda_valores_unitarios.ipynb`) |
| 1 | 4 | En progreso | EDA accionable |

---

## Reproducibilidad

- Semilla fija: `random_state=42` en todos los modelos con aleatoriedad
- Datos sintéticos: `np.random.default_rng(42)` para fallback sin BD
- Pipeline ejecutable de inicio a fin sin configuración adicional (modo sintético)
- Logs automáticos con `logging` (no prints manuales)

---

## Referencias normativas

- Ley General de Aduanas — Decreto Legislativo N° 1053
- Reglamento — Decreto Supremo N° 010-2009-EF
- Procedimiento General Exportación Definitiva INTA-PG.02
