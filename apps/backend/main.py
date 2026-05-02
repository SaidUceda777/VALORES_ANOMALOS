"""
main.py — API FastAPI para detección de outliers en valores unitarios
Proyecto: Detección de variaciones en el valor unitario — SUNAT
Autor   : Said Leonardo Uceda Paredes · UNI FIIS · 2026

Levantar:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Documentación automática:
    http://localhost:8000/docs
"""

import logging
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler
from pyod.models.hbos import HBOS

# ── Logger ─────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger('api_outliers')

# ── Parámetros de conexión ─────────────────────────────────────────────────────
SERVIDOR   = r'DESKTOP-OGU19A7\SQLEXPRESS,56878'
BASE_DATOS = 'DB_GEE_DW_ADUANAS'
ESQUEMA    = 'SC_ADUANA'
DRIVER     = 'ODBC+Driver+17+for+SQL+Server'

URL_CONEXION = (
    f'mssql+pyodbc://{SERVIDOR}/{BASE_DATOS}'
    f'?driver={DRIVER}&Trusted_Connection=yes&fast_executemany=True'
)

# ── App FastAPI ────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = 'API Detección de Outliers — SUNAT Exportaciones',
    description = 'Detección de variaciones atípicas en el valor unitario '
                  'de exportaciones peruanas mediante aprendizaje no supervisado.',
    version     = '1.0.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ['*'],   # en producción: restringir a dominio específico
    allow_methods     = ['*'],
    allow_headers     = ['*'],
)


# ── Modelos Pydantic ───────────────────────────────────────────────────────────
class ParametrosAnalisis(BaseModel):
    """Parámetros de entrada para ejecutar el pipeline de detección."""
    cod_analisis: str = 'ANA1'
    fec_ini     : str = '2023-01-01'
    fec_fin     : str = '2023-12-31'


class ResumenIndicadores(BaseModel):
    """Conteo de detecciones por cada indicador individual."""
    IND_IQR       : int
    IND_ZSCORE    : int
    IND_ZSCORE_ROB: int
    IND_IFOREST   : int
    IND_LOF       : int
    IND_DBSCAN    : int
    IND_HBOS      : int


class RespuestaAnalisis(BaseModel):
    """Respuesta completa del pipeline de detección."""
    cod_analisis    : str
    fec_ini         : str
    fec_fin         : str
    total_registros : int
    total_outliers  : int
    pct_outlier     : float
    indicadores     : ResumenIndicadores
    outliers        : list[dict]
    timestamp       : str


# ── Funciones del pipeline ─────────────────────────────────────────────────────
def obtener_datos_sp(
    cod_analisis: str,
    fec_ini     : str,
    fec_fin     : str,
) -> pd.DataFrame:
    """
    Función: Conecta a SQL Server y ejecuta el SP con @ACCION='OBTENER'
    para obtener los registros a analizar.

    Args:
        cod_analisis (str): Código del análisis (ej. 'ANA1').
        fec_ini      (str): Fecha de inicio en formato YYYY-MM-DD.
        fec_fin      (str): Fecha de fin en formato YYYY-MM-DD.

    Returns:
        pd.DataFrame: Datos con columnas _R, _C, _V.

    Raises:
        HTTPException 503: Si la conexión a SQL Server falla.
        HTTPException 404: Si el SP retorna 0 registros.
    """
    try:
        motor     = create_engine(URL_CONEXION, echo=False)
        sentencia = text(
            f"EXEC [{BASE_DATOS}].[{ESQUEMA}].[SP_VALORES_UNITARIOS] "
            f"@ACCION='OBTENER', "
            f"@COD_ANALISIS='{cod_analisis}', "
            f"@FEC_INI='{fec_ini}', "
            f"@FEC_FIN='{fec_fin}'"
        )
        with motor.connect() as conn:
            resultado = conn.execute(sentencia)
            cols      = list(resultado.keys())
            filas     = resultado.fetchall()
    except Exception as exc:
        log.error('Error de conexión: %s', exc)
        raise HTTPException(
            status_code = 503,
            detail      = f'No se pudo conectar a SQL Server [{SERVIDOR}]. Detalle: {exc}',
        ) from exc

    df = pd.DataFrame.from_records(filas, columns=cols)

    if df.empty:
        raise HTTPException(
            status_code = 404,
            detail      = f'El SP no retornó registros para COD={cod_analisis} '
                          f'entre {fec_ini} y {fec_fin}. Verificar INGESTA.',
        )

    log.info('SP ejecutado — %d registros | COD=%s', len(df), cod_analisis)
    return df


def ejecutar_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """
    Función: Aplica los 7 indicadores de detección de outliers sobre el
    DataFrame y genera la columna ES_OUTLIER (≥ 2 de 7 indicadores).

    Args:
        df (pd.DataFrame): Datos con columnas _R, _C, _V.

    Returns:
        pd.DataFrame: DataFrame original con indicadores y ES_OUTLIER agregados.
    """
    col_r = next((c for c in df.columns if str(c).upper().endswith('_R')), None)
    col_v = next((c for c in df.columns if str(c).upper().endswith('_V')), None)

    if col_r is None:
        df['__R'] = 'ALL'
        col_r     = '__R'

    df[col_v] = pd.to_numeric(df[col_v], errors='coerce')

    # ── IQR ───────────────────────────────────────────────────────────────────
    q1  = df.groupby(col_r)[col_v].transform('quantile', 0.25)
    q3  = df.groupby(col_r)[col_v].transform('quantile', 0.75)
    iqr = q3 - q1
    df['IND_IQR'] = ((df[col_v] < q1 - 1.5 * iqr) | (df[col_v] > q3 + 1.5 * iqr)).astype(int)

    # ── Z-Score clásico ───────────────────────────────────────────────────────
    media = df.groupby(col_r)[col_v].transform('mean')
    desv  = df.groupby(col_r)[col_v].transform('std').replace(0, np.nan)
    df['IND_ZSCORE'] = ((df[col_v] - media) / desv).abs().gt(3).astype(int)

    # ── Z-Score robusto (MAD) ─────────────────────────────────────────────────
    mediana = df.groupby(col_r)[col_v].transform('median')
    mad     = df.groupby(col_r)[col_v].transform(
        lambda x: np.median(np.abs(x - np.median(x)))
    ).replace(0, np.nan)
    df['IND_ZSCORE_ROB'] = (0.6745 * (df[col_v] - mediana) / mad).abs().gt(3.5).astype(int)

    # ── Isolation Forest ──────────────────────────────────────────────────────
    df['IND_IFOREST'] = 0
    for _, grupo in df.groupby(col_r):
        filas = grupo[col_v].dropna()
        if len(filas) < 2:
            continue
        pred = IsolationForest(contamination=0.05, random_state=42).fit_predict(
            filas.values.reshape(-1, 1)
        )
        df.loc[filas.index, 'IND_IFOREST'] = (pred == -1).astype(int)

    # ── LOF ───────────────────────────────────────────────────────────────────
    df['IND_LOF'] = 0
    for _, grupo in df.groupby(col_r):
        filas = grupo[col_v].dropna()
        if len(filas) < 2:
            continue
        n_vec = min(20, len(filas) - 1)
        pred  = LocalOutlierFactor(n_neighbors=n_vec, contamination=0.05).fit_predict(
            filas.values.reshape(-1, 1)
        )
        df.loc[filas.index, 'IND_LOF'] = (pred == -1).astype(int)

    # ── DBSCAN ────────────────────────────────────────────────────────────────
    df['IND_DBSCAN'] = 0
    for _, grupo in df.groupby(col_r):
        filas = grupo[col_v].dropna()
        if len(filas) < 4:
            continue
        scaled = RobustScaler().fit_transform(filas.values.reshape(-1, 1))
        pred   = DBSCAN(eps=0.5, min_samples=3).fit_predict(scaled)
        df.loc[filas.index, 'IND_DBSCAN'] = (pred == -1).astype(int)

    # ── HBOS ──────────────────────────────────────────────────────────────────
    df['IND_HBOS'] = 0
    for _, grupo in df.groupby(col_r):
        filas = grupo[col_v].dropna()
        if len(filas) < 2:
            continue
        n_bins = min(10, max(2, len(filas) // 3))
        modelo = HBOS(n_bins=n_bins, contamination=0.05)
        modelo.fit(filas.values.reshape(-1, 1))
        df.loc[filas.index, 'IND_HBOS'] = modelo.predict(filas.values.reshape(-1, 1))

    # ── ES_OUTLIER ────────────────────────────────────────────────────────────
    suma = (
        df['IND_IQR'] + df['IND_ZSCORE'] + df['IND_ZSCORE_ROB']
        + df['IND_IFOREST'] + df['IND_LOF'] + df['IND_DBSCAN'] + df['IND_HBOS']
    )
    df['ES_OUTLIER'] = (suma >= 2).astype(int)

    log.info('Pipeline completado — %d outliers / %d registros', df['ES_OUTLIER'].sum(), len(df))
    return df


# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.get('/health', summary='Estado del servidor y conexión a BD')
def health():
    """
    Función: Verifica que el servidor está activo y que la conexión a SQL
    Server funciona correctamente.

    Returns:
        dict: Estado del servidor y timestamp.
    """
    try:
        motor = create_engine(URL_CONEXION, echo=False)
        with motor.connect() as conn:
            fila = conn.execute(text('SELECT DB_NAME() AS bd, GETDATE() AS ts')).fetchone()
        return {
            'estado'   : 'ok',
            'bd'       : fila.bd,
            'servidor' : SERVIDOR,
            'timestamp': str(fila.ts),
        }
    except Exception as exc:
        raise HTTPException(
            status_code = 503,
            detail      = f'Sin conexión a SQL Server: {exc}',
        ) from exc


@app.post('/analizar', response_model=RespuestaAnalisis,
          summary='Ejecuta el pipeline completo de detección de outliers')
def analizar(parametros: ParametrosAnalisis):
    """
    Función: Ejecuta el pipeline completo de detección de outliers para el
    análisis indicado. Carga datos desde el SP, aplica los 7 indicadores
    y retorna los resultados con resumen y listado de outliers.

    Args:
        parametros (ParametrosAnalisis): cod_analisis, fec_ini, fec_fin.

    Returns:
        RespuestaAnalisis: Resumen + lista de registros con ES_OUTLIER = 1.
    """
    log.info('Solicitud /analizar — COD=%s | %s → %s',
             parametros.cod_analisis, parametros.fec_ini, parametros.fec_fin)

    df = obtener_datos_sp(
        parametros.cod_analisis,
        parametros.fec_ini,
        parametros.fec_fin,
    )

    df = ejecutar_pipeline(df)

    indicadores_nombres = [
        'IND_IQR', 'IND_ZSCORE', 'IND_ZSCORE_ROB',
        'IND_IFOREST', 'IND_LOF', 'IND_DBSCAN', 'IND_HBOS',
    ]
    conteo_ind = {k: int(df[k].sum()) for k in indicadores_nombres}

    total      = len(df)
    outliers   = int(df['ES_OUTLIER'].sum())
    pct        = round(outliers / total * 100, 4) if total > 0 else 0.0

    df_outliers = df[df['ES_OUTLIER'] == 1].copy()
    # Convertir Decimal/Int64 a tipos Python nativos para JSON
    registros   = df_outliers.where(df_outliers.notna(), None).to_dict(orient='records')
    registros   = [
        {k: (float(v) if hasattr(v, '__float__') else v)
         for k, v in r.items()}
        for r in registros
    ]

    return RespuestaAnalisis(
        cod_analisis    = parametros.cod_analisis,
        fec_ini         = parametros.fec_ini,
        fec_fin         = parametros.fec_fin,
        total_registros = total,
        total_outliers  = outliers,
        pct_outlier     = pct,
        indicadores     = ResumenIndicadores(**conteo_ind),
        outliers        = registros,
        timestamp       = datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )


@app.get('/resultados/{cod_analisis}',
         summary='Consulta resultados ya guardados en SQL Server')
def resultados(cod_analisis: str, solo_outliers: bool = True):
    """
    Función: Consulta la tabla de resultados previamente generada por el
    pipeline usando las acciones ANALISIS_TODOS o ANALISIS_OUTLIERS del SP.

    Args:
        cod_analisis  (str): Código del análisis (ej. 'ANA1').
        solo_outliers (bool): Si True, retorna solo ES_OUTLIER=1 (default).

    Returns:
        dict: Lista de registros y resumen.
    """
    accion = 'ANALISIS_OUTLIERS' if solo_outliers else 'ANALISIS_TODOS'
    try:
        motor = create_engine(URL_CONEXION, echo=False)
        sentencia = text(
            f"EXEC [{BASE_DATOS}].[{ESQUEMA}].[SP_VALORES_UNITARIOS] "
            f"@ACCION='{accion}', @COD_ANALISIS='{cod_analisis}'"
        )
        with motor.connect() as conn:
            resultado = conn.execute(sentencia)
            cols      = list(resultado.keys())
            filas     = resultado.fetchall()
        df  = pd.DataFrame.from_records(filas, columns=cols)
        return {
            'cod_analisis': cod_analisis,
            'accion'      : accion,
            'total'       : len(df),
            'registros'   : df.where(df.notna(), None).to_dict(orient='records'),
        }
    except Exception as exc:
        raise HTTPException(
            status_code = 500,
            detail      = f'Error al consultar resultados: {exc}',
        ) from exc
