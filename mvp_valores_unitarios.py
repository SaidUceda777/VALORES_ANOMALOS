# ============================================================
# MVP: SP_VALORES_UNITARIOS
# Entregable 1 → Detección de outliers por registro
# Entregable 2 → Catálogo MIN / MAX por categoría R
#
# Flujo: INGESTA → CLASIFICACIÓN (_R,_C,_V) → CORE 1 (estadísticos)
#        → CORE 2 (modelos IA) → ANÁLISIS FINAL
# ============================================================

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from pyod.models.hbos import HBOS
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler

# ── 0. PARÁMETROS DE ENTRADA ───────────────────────────────────────────────────
COD_ANALISIS = "EXPORTACIONES_2023"   # nombre del análisis → se usa como nombre de tabla
FEC_INI      = "2023-01-01"
FEC_FIN       = "2023-12-31"

SERVIDOR   = r"DESKTOP-OGU19A7\SQLEXPRESS,56878"
BASE_DATOS = "DB_GEE_DW_ADUANAS"
ESQUEMA    = "SC_ADUANA"
DRIVER     = "ODBC+Driver+17+for+SQL+Server"

# ── 1. MOTOR SQLAlchemy ────────────────────────────────────────────────────────
URL_CONEXION = (
    f"mssql+pyodbc://{SERVIDOR}/{BASE_DATOS}"
    f"?driver={DRIVER}"
    "&Trusted_Connection=yes"
    "&fast_executemany=True"
)

motor = create_engine(URL_CONEXION, echo=False)

# ── 2. INGESTA: ejecutar SP y cargar resultado ─────────────────────────────────
sentencia_sp = text(
    f"EXEC [{BASE_DATOS}].[{ESQUEMA}].[SP_VALORES_UNITARIOS] "
    f"@ACCION       = 'OBTENER', "
    f"@COD_ANALISIS = '{COD_ANALISIS}', "
    f"@FEC_INI      = '{FEC_INI}', "
    f"@FEC_FIN       = '{FEC_FIN}'"
)

with motor.connect() as conn:
    resultado        = conn.execute(sentencia_sp)
    nombres_columnas = list(resultado.keys())
    filas            = resultado.fetchall()

df = pd.DataFrame.from_records(filas, columns=nombres_columnas)

# ── 2. CLASIFICACIÓN: identificar columnas _R, _C, _V ─────────────────────────
columnas_r = [c for c in df.columns if str(c).upper().endswith("_R")]
columnas_c = [c for c in df.columns if str(c).upper().endswith("_C")]
columnas_v = [c for c in df.columns if str(c).upper().endswith("_V")]

col_r = columnas_r[0] if columnas_r else None
col_c = columnas_c[0] if columnas_c else None
col_v = columnas_v[0] if columnas_v else None

# pyodbc devuelve DECIMAL como Decimal de Python → forzar float64 para operar
if col_v:
    df[col_v] = pd.to_numeric(df[col_v], errors="coerce")
if col_c:
    df[col_c] = pd.to_numeric(df[col_c], errors="coerce").astype("Int64")

# Si no existe columna _R, el análisis es global (ALL-R)
if col_r is None:
    df["__R"] = "ALL"
    col_r = "__R"

# ── 3. CORE 1: INDICADORES ESTADÍSTICOS ───────────────────────────────────────


# 3.1 IQR (regla de bigotes) — por grupo R
q1  = df.groupby(col_r)[col_v].transform("quantile", 0.25)
q3  = df.groupby(col_r)[col_v].transform("quantile", 0.75)
iqr = q3 - q1
limite_inf_iqr = q1 - 1.5 * iqr
limite_sup_iqr = q3 + 1.5 * iqr
df["IND_IQR"] = ((df[col_v] < limite_inf_iqr) | (df[col_v] > limite_sup_iqr)).astype(int)

# 3.2 Z-SCORE clásico — por grupo R
media_grupo    = df.groupby(col_r)[col_v].transform("mean")
desv_std_grupo = df.groupby(col_r)[col_v].transform("std").replace(0, np.nan)
z_score_clasico = (df[col_v] - media_grupo) / desv_std_grupo
df["IND_ZSCORE"] = (z_score_clasico.abs() > 3).astype(int)

# 3.3 Z-SCORE ROBUSTO (mediana + MAD) — por grupo R
mediana_grupo = df.groupby(col_r)[col_v].transform("median")
mad_grupo = df.groupby(col_r)[col_v].transform(
    lambda x: np.median(np.abs(x - np.median(x)))
).replace(0, np.nan)
z_score_robusto = 0.6745 * (df[col_v] - mediana_grupo) / mad_grupo
df["IND_ZSCORE_ROB"] = (z_score_robusto.abs() > 3.5).astype(int)

# ── 4. CORE 2: MODELOS IA ─────────────────────────────────────────────────────

# 4.1 Isolation Forest — por grupo R (excluye NaN del cálculo)
df["IND_IFOREST"] = 0

for nombre_grupo, grupo in df.groupby(col_r):
    filas_if = grupo[col_v].dropna()
    if len(filas_if) < 2:
        continue
    pred_if = IsolationForest(contamination=0.05, random_state=42).fit_predict(
        filas_if.values.reshape(-1, 1)
    )
    df.loc[filas_if.index, "IND_IFOREST"] = (pred_if == -1).astype(int)

# 4.2 Local Outlier Factor — por grupo R (excluye NaN del cálculo)
df["IND_LOF"] = 0

for nombre_grupo, grupo in df.groupby(col_r):
    filas_lof = grupo[col_v].dropna()
    if len(filas_lof) < 2:
        continue
    n_vecinos = min(20, len(filas_lof) - 1)
    pred_lof  = LocalOutlierFactor(n_neighbors=n_vecinos, contamination=0.05).fit_predict(
        filas_lof.values.reshape(-1, 1)
    )
    df.loc[filas_lof.index, "IND_LOF"] = (pred_lof == -1).astype(int)

# 4.3 DBSCAN — por grupo R (escalado por IQR via RobustScaler, excluye NaN)
# eps=0.5 → vecindad de medio IQR escalado; min_samples=3 → mínimo para formar cluster
df["IND_DBSCAN"] = 0

for nombre_grupo, grupo in df.groupby(col_r):
    filas_db = grupo[col_v].dropna()
    if len(filas_db) < 4:
        continue
    valores_db     = filas_db.values.reshape(-1, 1)
    valores_scaled = RobustScaler().fit_transform(valores_db)
    pred_db        = DBSCAN(eps=0.5, min_samples=3).fit_predict(valores_scaled)
    df.loc[filas_db.index, "IND_DBSCAN"] = (pred_db == -1).astype(int)

# 4.4 HBOS (Histogram-Based Outlier Score) — por grupo R
# n_bins adaptativo: min(10, n//3) para grupos pequeños; pyod devuelve 0=normal 1=outlier
df["IND_HBOS"] = 0

for nombre_grupo, grupo in df.groupby(col_r):
    filas_hbos = grupo[col_v].dropna()
    if len(filas_hbos) < 2:
        continue
    n_bins = min(10, max(2, len(filas_hbos) // 3))
    modelo_hbos = HBOS(n_bins=n_bins, contamination=0.05)
    modelo_hbos.fit(filas_hbos.values.reshape(-1, 1))
    pred_hbos = modelo_hbos.predict(filas_hbos.values.reshape(-1, 1))
    df.loc[filas_hbos.index, "IND_HBOS"] = pred_hbos  # 0=normal, 1=outlier

# ──────────────────────────────────────────────────────────────────────────────
# MODELOS DESCARTADOS — razones técnicas
# ──────────────────────────────────────────────────────────────────────────────
#
# Autoencoder simple (Keras/TF)
#   - Dependencia pesada: TensorFlow (~600 MB) innecesaria para 1 variable
#   - Hiperparámetros sensibles: capas, épocas, lr → no reproducible sin tuning
#   - No produce límite en USD/kg, solo error de reconstrucción
#
# Variational Autoencoder (VAE)
#   - Mayor complejidad que el simple sin ganancia para datos univariados
#   - Grupos pequeños (<50 filas) colapsan en el espacio latente (posterior collapse)
#   - Tiempo de entrenamiento 50-200x vs HBOS para el mismo resultado
#
# Deep SVDD
#   - Requiere PyTorch explícitamente
#   - Problema conocido de colapso hipoesferal en datos con poca varianza
#   - No convergencia garantizada en distribuciones univariadas asimétricas
#
# Deep Isolation Forest / modelos PyOD avanzados (ECOD, SUOD, IForest PyOD)
#   - ECOD y SUOD requieren scipy y numba como dependencias adicionales
#   - Tiempo O(n²) en algunos modos de SUOD
#   - Para 1 variable por partida aportan lo mismo que IF estándar de sklearn
#
# TabNet / modelos tabulares neuronales
#   - Diseñado para datasets anchos (muchas features); aquí solo hay 1 variable
#   - Requiere pytorch-tabnet → PyTorch como dependencia
#   - Overhead de GPU/CPU injustificado para detección univariada por grupo
#
# Autoencoder con PyTorch
#   - Mismo argumento que TF: overkill para 1 variable
#   - Reproducibilidad comprometida entre CPU/GPU y versiones de CUDA
#   - El modelo entrenado por partida (~790) requiere serializar 790 pesos
#
# Autoencoder con TensorFlow
#   - TF 2.x requiere ≥Python 3.8 y ~600 MB de instalación
#   - Conflictos frecuentes con versiones de numpy/scipy en el entorno actual
#   - Inferencia más lenta que HBOS/IQR para datasets del tamaño de cada partida
# ──────────────────────────────────────────────────────────────────────────────

# ── 5. ANÁLISIS FINAL: ES_OUTLIER ─────────────────────────────────────────────
# Es outlier si cumple al menos 2 de los 7 indicadores aplicados
suma_indicadores = (
    df["IND_IQR"]
    + df["IND_ZSCORE"]
    + df["IND_ZSCORE_ROB"]
    + df["IND_IFOREST"]
    + df["IND_LOF"]
    + df["IND_DBSCAN"]
    + df["IND_HBOS"]
)
df["ES_OUTLIER"] = (suma_indicadores >= 2).astype(int)

# ── 6. ENTREGABLE 1: R | C | V | indicadores | ES_OUTLIER ─────────────────────
columnas_e1 = [col_r]
if col_c:
    columnas_e1.append(col_c)
columnas_e1 += [
    col_v,
    "IND_IQR",
    "IND_ZSCORE",
    "IND_ZSCORE_ROB",
    "IND_IFOREST",
    "IND_LOF",
    "IND_DBSCAN",
    "IND_HBOS",
    "ES_OUTLIER",
]

entregable_1 = df[columnas_e1].copy()

# ── 7. ENTREGABLE 2: catálogo de límites por categoría R ──────────────────────
grp_cat  = df.groupby(col_r)[col_v]
_q1      = grp_cat.quantile(0.25)
_q3      = grp_cat.quantile(0.75)
_iqr     = _q3 - _q1
_media   = grp_cat.mean()
_desv    = grp_cat.std().fillna(0)
_mediana = grp_cat.median()
_mad     = grp_cat.apply(
    lambda x: np.median(np.abs(x.dropna() - np.median(x.dropna())))
).fillna(0)

entregable_2 = pd.DataFrame({
    "R"                  : _q1.index,
    "VAL_MIN"            : grp_cat.min().values,
    "VAL_MAX"            : grp_cat.max().values,
    "VAL_MIN_IQR"        : (_q1 - 1.5 * _iqr).round(6).values,
    "VAL_MAX_IQR"        : (_q3 + 1.5 * _iqr).round(6).values,
    "VAL_MIN_ZSCORE"     : (_media - 3 * _desv).round(6).values,
    "VAL_MAX_ZSCORE"     : (_media + 3 * _desv).round(6).values,
    "VAL_MIN_ZSCORE_ROB" : (_mediana - (3.5 / 0.6745) * _mad).round(6).values,
    "VAL_MAX_ZSCORE_ROB" : (_mediana + (3.5 / 0.6745) * _mad).round(6).values,
}).reset_index(drop=True)

# ── 8. FUNCIÓN DDL: genera CREATE TABLE según sufijos de columna ───────────────
def generar_ddl_tabla(df_ref, nombre_tabla_sql):
    """
    Función: Genera el DDL CREATE TABLE infiriendo el tipo SQL desde el sufijo
    de cada columna. Usa el primer registro para calcular el ancho de VARCHAR
    de forma holgada (× 6, mínimo 200).

    Args:
        df_ref (pd.DataFrame): DataFrame del que se infieren columnas y tipos.
        nombre_tabla_sql (str): Nombre completo [DB].[SC].[TABLA].

    Returns:
        str: Sentencias DROP (si existe) + CREATE TABLE listas para ejecutar.
    """
    columnas_ddl = []
    primera_fila = df_ref.iloc[0] if len(df_ref) > 0 else {}

    for col in df_ref.columns:
        col_up = col.upper()
        if col_up.endswith("_R") or col_up == "__R":
            ancho  = max(len(str(primera_fila.get(col, ""))) * 6, 200)
            tipo   = f"VARCHAR({ancho})"
        elif col_up.endswith("_C"):
            tipo   = "INT"
        elif col_up.endswith("_V"):
            tipo   = "DECIMAL(18, 6)"
        elif col_up.startswith("IND_") or col_up == "ES_OUTLIER":
            tipo   = "TINYINT"
        elif col_up.startswith("VAL_"):
            tipo   = "DECIMAL(18, 6)"
        else:
            ancho  = max(len(str(primera_fila.get(col, ""))) * 6, 200)
            tipo   = f"VARCHAR({ancho})"
        columnas_ddl.append(f"    [{col}] {tipo} NULL")

    cuerpo  = ",\n".join(columnas_ddl)
    drop    = f"IF OBJECT_ID('{nombre_tabla_sql}', 'U') IS NOT NULL DROP TABLE {nombre_tabla_sql};"
    create  = f"CREATE TABLE {nombre_tabla_sql} (\n{cuerpo}\n);"
    return drop, create

# ── 9. NOMBRES DE TABLA EN SQL SERVER ─────────────────────────────────────────
# Prefijo T → nombre de tabla coincide con la convención del SP (ej: TANA1)
base_nombre     = "T" + COD_ANALISIS.replace(" ", "_").replace("-", "_")
tabla_e1_sql    = f"[{BASE_DATOS}].[{ESQUEMA}].[{base_nombre}]"
tabla_e2_sql    = f"[{BASE_DATOS}].[{ESQUEMA}].[{base_nombre}_CATALOGO]"

# ── 10. EXPORT TXT con separador | ────────────────────────────────────────────
ruta_txt_e1 = f"{base_nombre}.txt"
ruta_txt_e2 = f"{base_nombre}_CATALOGO.txt"

entregable_1.to_csv(ruta_txt_e1, sep="|", index=False)
entregable_2.to_csv(ruta_txt_e2, sep="|", index=False)

print("=" * 60)
print("ENTREGABLE 1 — DETECCIÓN DE OUTLIERS")
print("=" * 60)
print(entregable_1.to_string(index=False))
print()
print("=" * 60)
print("ENTREGABLE 2 — CATÁLOGO MIN / MAX POR CATEGORÍA")
print("=" * 60)
print(entregable_2.to_string(index=False))

# ── 11. CREAR TABLAS Y CARGAR EN SQL SERVER (SQLAlchemy) ──────────────────────
drop_e1, create_e1 = generar_ddl_tabla(entregable_1, tabla_e1_sql)
drop_e2, create_e2 = generar_ddl_tabla(entregable_2, tabla_e2_sql)

# Crear estructura con DDL explícito (tipos controlados: VARCHAR/INT/DECIMAL/TINYINT)
with motor.begin() as conn:
    conn.execute(text(drop_e1))
    conn.execute(text(create_e1))
    conn.execute(text(drop_e2))
    conn.execute(text(create_e2))

# Insertar usando to_sql — tabla ya existe con tipos correctos, solo se apilan filas
entregable_1.to_sql(
    name        = base_nombre,
    schema      = ESQUEMA,
    con         = motor,
    if_exists   = "append",
    index       = False,
    chunksize   = 5_000,
)

entregable_2.to_sql(
    name        = f"{base_nombre}_CATALOGO",
    schema      = ESQUEMA,
    con         = motor,
    if_exists   = "append",
    index       = False,
    chunksize   = 1_000,
)

print()
print(f"[OK] Tablas cargadas en [{BASE_DATOS}].[{ESQUEMA}]:")
print(f"     [{base_nombre}]           ({len(entregable_1)} filas)")
print(f"     [{base_nombre}_CATALOGO]  ({len(entregable_2)} filas)")
print(f"[OK] TXT exportados: {ruta_txt_e1} | {ruta_txt_e2}")
