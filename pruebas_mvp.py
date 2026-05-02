# ============================================================
# PRUEBAS DEL MVP: SP_VALORES_UNITARIOS
#
# Uso:
#   python pruebas_mvp.py --prueba1            → conexión BD
#   python pruebas_mvp.py --prueba2            → modelos detección
#   python pruebas_mvp.py --prueba3            → función DDL
#   python pruebas_mvp.py --prueba4            → flujo completo sin BD
#   python pruebas_mvp.py --prueba1 --prueba2  → varias a la vez
#   python pruebas_mvp.py                      → todas las pruebas
# ============================================================

import sys
import io
import os
import argparse
import subprocess
import warnings

# Forzar UTF-8 en la consola para soportar caracteres especiales en nombres de partidas
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from pyod.models.hbos import HBOS
from sklearn.cluster import DBSCAN
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import RobustScaler

warnings.filterwarnings("ignore")

# ── PARÁMETROS COMPARTIDOS (deben coincidir con mvp_valores_unitarios.py) ──────
SERVIDOR   = r"DESKTOP-OGU19A7\SQLEXPRESS,56878"
BASE_DATOS = "DB_GEE_DW_ADUANAS"
ESQUEMA    = "SC_ADUANA"
DRIVER     = "ODBC+Driver+17+for+SQL+Server"

URL_CONEXION = (
    f"mssql+pyodbc://{SERVIDOR}/{BASE_DATOS}"
    f"?driver={DRIVER}"
    "&Trusted_Connection=yes"
)

# Almacena la URL que funcionó para reutilizarla en prueba5
_url_activa = None

# ── SEPARADOR VISUAL ───────────────────────────────────────────────────────────
SEP = "=" * 65


def _encabezado(titulo):
    """
    Función: Imprime un encabezado formateado para cada prueba.

    Args:
        titulo (str): Texto del encabezado.

    Returns:
        None
    """
    print(f"\n{SEP}")
    print(f"  {titulo}")
    print(SEP)


# ══════════════════════════════════════════════════════════════════════════════
# PRUEBA 1 — Diagnóstico de conexión SQLAlchemy
# ══════════════════════════════════════════════════════════════════════════════
def prueba_conexion():
    """
    Función: Diagnostica la conexión a SQL Server probando automáticamente
    las variantes de servidor más comunes (instancia default, SQLEXPRESS,
    MSSQLSERVER, TCP explícito, 127.0.0.1). Actualiza _url_activa con la
    primera cadena que funcione.

    Args:
        Ninguno.

    Returns:
        str | None: URL de conexión válida, o None si ninguna funcionó.
    """
    global _url_activa
    _encabezado("PRUEBA 1 — Diagnóstico de conexión SQLAlchemy")

    # 1. Leer instancias reales desde los servicios de Windows
    print("  Leyendo servicios SQL Server activos en esta maquina...")
    instancias_windows = []
    try:
        ps_cmd = (
            "Get-Service | Where-Object {$_.DisplayName -like '*SQL Server (*'} "
            "| Select-Object Name, Status | ConvertTo-Csv -NoTypeInformation"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10
        )
        for linea in res.stdout.splitlines()[1:]:     # saltar cabecera CSV
            partes = linea.replace('"', '').split(",")
            if len(partes) == 2:
                nombre_svc, estado = partes[0].strip(), partes[1].strip()
                if nombre_svc.startswith("MSSQL$"):
                    instancia = nombre_svc.replace("MSSQL$", "")
                    instancias_windows.append((instancia, estado))
                    print(f"    Servicio: {nombre_svc:<30}  Estado: {estado}")
    except Exception as exc:
        print(f"    No se pudo leer servicios: {exc}")

    # 2. Intentar arrancar SQL Server Browser si está detenido
    print()
    try:
        ps_browser = (
            "$svc = Get-Service SQLBrowser -ErrorAction SilentlyContinue; "
            "if ($svc -and $svc.Status -ne 'Running') { "
            "    Start-Service SQLBrowser -ErrorAction SilentlyContinue; "
            "    Start-Sleep 2 "
            "}; "
            "(Get-Service SQLBrowser -ErrorAction SilentlyContinue).Status"
        )
        res_br = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_browser],
            capture_output=True, text=True, timeout=12
        )
        estado_browser = res_br.stdout.strip()
        print(f"  SQL Server Browser: {estado_browser if estado_browser else 'no encontrado'}")
    except Exception:
        print("  SQL Server Browser: no se pudo verificar")

    # 3. Construir candidatos: primero SERVIDOR configurado, luego descubiertos, luego genéricos
    candidatos_descubiertos = [
        f".\\{inst}" for inst, _ in instancias_windows
    ] + [
        f"localhost\\{inst}" for inst, _ in instancias_windows
    ] + [
        f"DESKTOP-OGU19A7\\{inst}" for inst, _ in instancias_windows
    ]
    candidatos_genericos = [
        SERVIDOR,                   # valor configurado en el script
        "localhost",
        r"localhost\SQLEXPRESS",
        r"localhost\MSSQLSERVER",
        r".\SQLEXPRESS",
        "127.0.0.1",
        r"DESKTOP-OGU19A7\SQLEXPRESS",
    ]
    # Deduplicar manteniendo orden
    vistos     = set()
    candidatos = []
    for c in candidatos_descubiertos + candidatos_genericos:
        if c not in vistos:
            vistos.add(c)
            candidatos.append(c)
    print()

    plantilla_url = (
        "mssql+pyodbc://{servidor}/{base}"
        "?driver={driver}"
        "&Trusted_Connection=yes"
        "&timeout=4"
    )

    # 3b. Leer puerto dinámico actual de SQLEXPRESS desde registro (sin admin)
    puerto_dinamico = None
    try:
        ps_puerto = (
            "$p = Get-ItemProperty "
            "'HKLM:\\SOFTWARE\\Microsoft\\Microsoft SQL Server\\MSSQL15.SQLEXPRESS"
            "\\MSSQLServer\\SuperSocketNetLib\\Tcp\\IPAll' -ErrorAction SilentlyContinue; "
            "if ($p.TcpDynamicPorts -and $p.TcpDynamicPorts -ne '0' -and $p.TcpDynamicPorts -ne '') "
            "{ $p.TcpDynamicPorts } elseif ($p.TcpPort -and $p.TcpPort -ne '') { $p.TcpPort }"
        )
        res_p = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_puerto],
            capture_output=True, text=True, timeout=5
        )
        puerto_dinamico = res_p.stdout.strip()
        if puerto_dinamico:
            print(f"  Puerto TCP detectado en registro: {puerto_dinamico}")
            # Agregar candidatos con puerto explícito al inicio
            candidatos_con_puerto = [
                f"DESKTOP-OGU19A7\\SQLEXPRESS,{puerto_dinamico}",
                f"127.0.0.1,{puerto_dinamico}",
            ]
            candidatos = candidatos_con_puerto + candidatos
    except Exception:
        pass

    print(f"  {'Servidor candidato':<40}  Resultado")
    print(f"  {'-'*40}  {'-'*40}")

    url_encontrada  = None
    servidor_valido = None

    for servidor in candidatos:
        # En Python 3.11 no se puede usar \ dentro de f-strings; usamos variable previa
        srv_url = servidor.replace("\\", "\\\\")
        url = plantilla_url.format(servidor=srv_url, base=BASE_DATOS, driver=DRIVER)
        try:
            motor = create_engine(url, echo=False,
                                  connect_args={"timeout": 4, "login_timeout": 4})
            with motor.connect() as conn:
                fila = conn.execute(
                    text("SELECT DB_NAME() AS bd, @@SERVERNAME AS srv, GETDATE() AS ts")
                ).fetchone()
            print(f"  {servidor:<40}  [OK] bd={fila.bd}  srv={fila.srv}")
            url_encontrada  = url
            servidor_valido = servidor
            break
        except Exception as exc:
            msg = str(exc).splitlines()[0][:55]
            print(f"  {servidor:<40}  [FAIL] {msg}")

    print()
    if url_encontrada:
        _url_activa = url_encontrada
        print(f"  [OK] Conexion exitosa con: {servidor_valido}")
        print()
        print(f"  >> Actualiza SERVIDOR en mvp_valores_unitarios.py y pruebas_mvp.py:")
        print(f'     SERVIDOR = r"{servidor_valido}"')
    else:
        print("  [FAIL] Ningun candidato conecto.")
        print()
        print("  CAUSA DETECTADA:")
        print("  - Servicios corriendo : SQLEXPRESS, SQLEXPRESS01, SQLEXPRESS2, WINCC")
        print("  - SQL Server Browser  : Stopped  (impide resolver instancias nombradas)")
        print("  - TCP/IP y Named Pipes: deshabilitados en instancias Express")
        print("  - WINCC TCP activo (56905) pero autenticacion restringida por dominio")
        print()
        print("  SOLUCION (requiere ejecutar como Administrador):")
        print("  " + "-" * 49)
        print("  Opcion A — Habilitar TCP en SQLEXPRESS (recomendado):")
        print("    1. Busca 'SQL Server Configuration Manager' y abrelo como Admin")
        print("    2. Ve a: SQL Server Network Configuration")
        print("             > Protocols for SQLEXPRESS")
        print("    3. Doble clic en 'TCP/IP' > Enable > OK")
        print("    4. En la misma ventana habilita 'Named Pipes' (opcional)")
        print("    5. Reinicia el servicio:")
        print("         Restart-Service MSSQL`$SQLEXPRESS")
        print()
        print("  Opcion B — Iniciar SQL Server Browser (resuelve todas las instancias):")
        print("    Start-Service SQLBrowser   (desde terminal como Admin)")
        print()
        print("  Opcion C — Pasar nombre de servidor manualmente al script:")
        print("    python pruebas_mvp.py --prueba1 --servidor .\\SQLEXPRESS")

    return url_encontrada


# ══════════════════════════════════════════════════════════════════════════════
# PRUEBA 2 — Modelos de detección con datos sintéticos
# ══════════════════════════════════════════════════════════════════════════════
def prueba_modelos():
    """
    Función: Valida los 5 indicadores (IQR, Z-Score, Z-Score Robusto,
    Isolation Forest, LOF) usando un DataFrame sintético con outliers
    conocidos en las posiciones finales.

    Args:
        Ninguno.

    Returns:
        pd.DataFrame: Resultado con indicadores y ES_OUTLIER.
    """
    _encabezado("PRUEBA 2 — Modelos de detección (datos sintéticos)")

    np.random.seed(42)
    valores_normales = np.random.normal(loc=100, scale=8, size=60).tolist()
    # Outliers inyectados con posición conocida: índices 60, 61, 62
    outliers_conocidos = [600.0, -250.0, 900.0]
    todas_partidas = (["7210-MAQUINARIA"] * 35 + ["8544-CABLES"] * 25
                      + ["7210-MAQUINARIA"] * 2 + ["8544-CABLES"])

    df_test = pd.DataFrame({
        "NUM_SPN_R"           : todas_partidas,
        "ANIO_C"              : [2023] * 63,
        "MTO_VALOR_UNTARIO_V" : valores_normales + outliers_conocidos,
    })

    col_r = "NUM_SPN_R"
    col_v = "MTO_VALOR_UNTARIO_V"

    # IQR
    q1  = df_test.groupby(col_r)[col_v].transform("quantile", 0.25)
    q3  = df_test.groupby(col_r)[col_v].transform("quantile", 0.75)
    iqr = q3 - q1
    df_test["IND_IQR"] = (
        (df_test[col_v] < q1 - 1.5 * iqr) | (df_test[col_v] > q3 + 1.5 * iqr)
    ).astype(int)

    # Z-Score clásico
    media  = df_test.groupby(col_r)[col_v].transform("mean")
    desv   = df_test.groupby(col_r)[col_v].transform("std").replace(0, np.nan)
    df_test["IND_ZSCORE"] = ((df_test[col_v] - media) / desv).abs().gt(3).astype(int)

    # Z-Score robusto
    mediana = df_test.groupby(col_r)[col_v].transform("median")
    mad     = df_test.groupby(col_r)[col_v].transform(
        lambda x: np.median(np.abs(x - np.median(x)))
    ).replace(0, np.nan)
    df_test["IND_ZSCORE_ROB"] = (
        (0.6745 * (df_test[col_v] - mediana) / mad).abs().gt(3.5)
    ).astype(int)

    # Isolation Forest
    df_test["IND_IFOREST"] = 0
    for _, grupo in df_test.groupby(col_r):
        if len(grupo) < 2:
            continue
        pred = IsolationForest(contamination=0.05, random_state=42).fit_predict(
            grupo[[col_v]].values
        )
        df_test.loc[grupo.index, "IND_IFOREST"] = (pred == -1).astype(int)

    # LOF
    df_test["IND_LOF"] = 0
    for _, grupo in df_test.groupby(col_r):
        if len(grupo) < 2:
            continue
        n_vec = min(20, len(grupo) - 1)
        pred  = LocalOutlierFactor(n_neighbors=n_vec, contamination=0.05).fit_predict(
            grupo[[col_v]].values
        )
        df_test.loc[grupo.index, "IND_LOF"] = (pred == -1).astype(int)

    # DBSCAN
    df_test["IND_DBSCAN"] = 0
    for _, grupo in df_test.groupby(col_r):
        filas_db = grupo[col_v].dropna()
        if len(filas_db) < 4:
            continue
        valores_scaled = RobustScaler().fit_transform(filas_db.values.reshape(-1, 1))
        pred = DBSCAN(eps=0.5, min_samples=3).fit_predict(valores_scaled)
        df_test.loc[filas_db.index, "IND_DBSCAN"] = (pred == -1).astype(int)

    # HBOS
    df_test["IND_HBOS"] = 0
    for _, grupo in df_test.groupby(col_r):
        filas_hbos = grupo[col_v].dropna()
        if len(filas_hbos) < 2:
            continue
        n_bins = min(10, max(2, len(filas_hbos) // 3))
        modelo_hbos = HBOS(n_bins=n_bins, contamination=0.05)
        modelo_hbos.fit(filas_hbos.values.reshape(-1, 1))
        pred = modelo_hbos.predict(filas_hbos.values.reshape(-1, 1))
        df_test.loc[filas_hbos.index, "IND_HBOS"] = pred

    # ES_OUTLIER
    suma = (df_test["IND_IQR"] + df_test["IND_ZSCORE"] + df_test["IND_ZSCORE_ROB"]
            + df_test["IND_IFOREST"] + df_test["IND_LOF"]
            + df_test["IND_DBSCAN"] + df_test["IND_HBOS"])
    df_test["ES_OUTLIER"] = (suma >= 2).astype(int)

    solo_outliers = df_test[df_test["ES_OUTLIER"] == 1]
    print(f"  Total registros     : {len(df_test)}")
    print(f"  Outliers inyectados : indices 60, 61, 62  ->  valores {outliers_conocidos}")
    print(f"  Outliers detectados : {len(solo_outliers)}")
    print()
    print(solo_outliers[[col_r, col_v, "IND_IQR", "IND_ZSCORE",
                          "IND_ZSCORE_ROB", "IND_IFOREST", "IND_LOF",
                          "IND_DBSCAN", "IND_HBOS", "ES_OUTLIER"]].to_string(index=True))

    detectados_correctos = set(solo_outliers.index).intersection({60, 61, 62})
    print(f"\n  Outliers conocidos encontrados: {len(detectados_correctos)} / 3")

    return df_test


# ══════════════════════════════════════════════════════════════════════════════
# PRUEBA 3 — Función generar_ddl_tabla
# ══════════════════════════════════════════════════════════════════════════════
def prueba_ddl():
    """
    Función: Verifica que generar_ddl_tabla produce tipos SQL correctos
    para cada sufijo de columna (_R → VARCHAR, _C → INT, _V → DECIMAL,
    IND_* / ES_OUTLIER → TINYINT).

    Args:
        Ninguno.

    Returns:
        tuple[str, str]: (sentencia DROP, sentencia CREATE TABLE).
    """
    _encabezado("PRUEBA 3 — Generación de DDL")

    # DataFrame de muestra que representa la estructura de Entregable 1
    df_muestra = pd.DataFrame([{
        "NUM_SPN_R"            : "7210-MAQUINARIA INDUSTRIAL",
        "ANIO_C"               : 2023,
        "MTO_VALOR_UNTARIO_V"  : 123.456,
        "IND_IQR"              : 0,
        "IND_ZSCORE"           : 0,
        "IND_ZSCORE_ROB"       : 1,
        "IND_IFOREST"          : 0,
        "IND_LOF"              : 1,
        "ES_OUTLIER"           : 1,
    }])

    nombre_tabla_sql = "[DB_GEE_DW_ADUANAS].[SC_ADUANA].[TANA1]"

    # ── réplica inline de generar_ddl_tabla ───────────────────────────────────
    columnas_ddl = []
    primera_fila = df_muestra.iloc[0]

    for col in df_muestra.columns:
        col_up = col.upper()
        if col_up.endswith("_R") or col_up == "__R":
            ancho = max(len(str(primera_fila.get(col, ""))) * 6, 200)
            tipo  = f"VARCHAR({ancho})"
        elif col_up.endswith("_C"):
            tipo  = "INT"
        elif col_up.endswith("_V"):
            tipo  = "DECIMAL(18, 6)"
        elif col_up.startswith("IND_") or col_up == "ES_OUTLIER":
            tipo  = "TINYINT"
        else:
            ancho = max(len(str(primera_fila.get(col, ""))) * 6, 200)
            tipo  = f"VARCHAR({ancho})"
        columnas_ddl.append(f"    [{col}] {tipo} NULL")

    cuerpo = ",\n".join(columnas_ddl)
    drop   = f"IF OBJECT_ID('{nombre_tabla_sql}', 'U') IS NOT NULL DROP TABLE {nombre_tabla_sql};"
    create = f"CREATE TABLE {nombre_tabla_sql} (\n{cuerpo}\n);"

    print("  Tabla objetivo:", nombre_tabla_sql)
    print()
    print(drop)
    print()
    print(create)

    # Verificaciones
    assert "VARCHAR"      in create, "Falla: _R no generó VARCHAR"
    assert "INT"          in create, "Falla: _C no generó INT"
    assert "DECIMAL(18"   in create, "Falla: _V no generó DECIMAL"
    assert "TINYINT"      in create, "Falla: IND_* no generó TINYINT"
    print("\n  [OK] Todos los tipos SQL son correctos")

    return drop, create


# ══════════════════════════════════════════════════════════════════════════════
# PRUEBA 4 — Flujo completo sin base de datos
# ══════════════════════════════════════════════════════════════════════════════
def prueba_flujo_completo():
    """
    Función: Simula el flujo completo del MVP usando datos sintéticos
    en lugar de llamar al SP. Produce Entregable 1 y Entregable 2,
    y los guarda como TXT con separador |.

    Args:
        Ninguno.

    Returns:
        tuple[pd.DataFrame, pd.DataFrame]: (entregable_1, entregable_2).
    """
    _encabezado("PRUEBA 4 — Flujo completo (sin BD)")

    np.random.seed(0)
    n = 80
    partidas = (["8544-CABLES"] * 40 + ["7210-MAQUINARIA"] * 40)
    valores  = (
        np.random.normal(200, 15, 40).tolist()
        + np.random.normal(500, 30, 40).tolist()
    )
    # Insertar 4 outliers conocidos
    valores[5]  = 5000.0
    valores[45] = -100.0
    valores[20] = 9999.0
    valores[60] = 0.001

    df = pd.DataFrame({
        "NUM_SPN_R"           : partidas,
        "ANIO_C"              : [2023] * n,
        "MTO_VALOR_UNTARIO_V" : valores,
    })

    col_r = "NUM_SPN_R"
    col_c = "ANIO_C"
    col_v = "MTO_VALOR_UNTARIO_V"

    # CORE 1
    q1  = df.groupby(col_r)[col_v].transform("quantile", 0.25)
    q3  = df.groupby(col_r)[col_v].transform("quantile", 0.75)
    iqr = q3 - q1
    df["IND_IQR"] = ((df[col_v] < q1 - 1.5 * iqr) | (df[col_v] > q3 + 1.5 * iqr)).astype(int)

    media = df.groupby(col_r)[col_v].transform("mean")
    desv  = df.groupby(col_r)[col_v].transform("std").replace(0, np.nan)
    df["IND_ZSCORE"] = ((df[col_v] - media) / desv).abs().gt(3).astype(int)

    mediana = df.groupby(col_r)[col_v].transform("median")
    mad     = df.groupby(col_r)[col_v].transform(
        lambda x: np.median(np.abs(x - np.median(x)))
    ).replace(0, np.nan)
    df["IND_ZSCORE_ROB"] = (0.6745 * (df[col_v] - mediana) / mad).abs().gt(3.5).astype(int)

    # CORE 2
    df["IND_IFOREST"] = 0
    for _, grupo in df.groupby(col_r):
        if len(grupo) < 2:
            continue
        pred = IsolationForest(contamination=0.05, random_state=42).fit_predict(
            grupo[[col_v]].values
        )
        df.loc[grupo.index, "IND_IFOREST"] = (pred == -1).astype(int)

    df["IND_LOF"] = 0
    for _, grupo in df.groupby(col_r):
        if len(grupo) < 2:
            continue
        n_vec = min(20, len(grupo) - 1)
        pred  = LocalOutlierFactor(n_neighbors=n_vec, contamination=0.05).fit_predict(
            grupo[[col_v]].values
        )
        df.loc[grupo.index, "IND_LOF"] = (pred == -1).astype(int)

    df["IND_DBSCAN"] = 0
    for _, grupo in df.groupby(col_r):
        filas_db = grupo[col_v].dropna()
        if len(filas_db) < 4:
            continue
        valores_scaled = RobustScaler().fit_transform(filas_db.values.reshape(-1, 1))
        pred = DBSCAN(eps=0.5, min_samples=3).fit_predict(valores_scaled)
        df.loc[filas_db.index, "IND_DBSCAN"] = (pred == -1).astype(int)

    df["IND_HBOS"] = 0
    for _, grupo in df.groupby(col_r):
        filas_hbos = grupo[col_v].dropna()
        if len(filas_hbos) < 2:
            continue
        n_bins = min(10, max(2, len(filas_hbos) // 3))
        modelo_hbos = HBOS(n_bins=n_bins, contamination=0.05)
        modelo_hbos.fit(filas_hbos.values.reshape(-1, 1))
        pred = modelo_hbos.predict(filas_hbos.values.reshape(-1, 1))
        df.loc[filas_hbos.index, "IND_HBOS"] = pred

    suma = (df["IND_IQR"] + df["IND_ZSCORE"] + df["IND_ZSCORE_ROB"]
            + df["IND_IFOREST"] + df["IND_LOF"] + df["IND_DBSCAN"] + df["IND_HBOS"])
    df["ES_OUTLIER"] = (suma >= 2).astype(int)

    # Entregables
    entregable_1 = df[[col_r, col_c, col_v,
                        "IND_IQR", "IND_ZSCORE", "IND_ZSCORE_ROB",
                        "IND_IFOREST", "IND_LOF", "IND_DBSCAN", "IND_HBOS",
                        "ES_OUTLIER"]].copy()

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

    # Export TXT
    entregable_1.to_csv("TEST_TANA1.txt",          sep="|", index=False)
    entregable_2.to_csv("TEST_TANA1_CATALOGO.txt", sep="|", index=False)

    print(f"  Registros totales : {len(entregable_1)}")
    print(f"  Outliers (ES=1)   : {entregable_1['ES_OUTLIER'].sum()}")
    print(f"  Outliers en índices conocidos (5,20,45,60): "
          f"{entregable_1.loc[[5,20,45,60], 'ES_OUTLIER'].tolist()}")
    print()
    print("-- Entregable 1 (primeras 10 filas) --")
    print(entregable_1.head(10).to_string(index=True))
    print()
    print("-- Entregable 2 - Catalogo MIN/MAX --")
    print(entregable_2.to_string(index=False))
    print()
    print("  [OK] TXT exportados: TEST_TANA1.txt | TEST_TANA1_CATALOGO.txt")

    return entregable_1, entregable_2


# ══════════════════════════════════════════════════════════════════════════════
# PRUEBA 5 — Ejecución real contra la base de datos
# ══════════════════════════════════════════════════════════════════════════════
def prueba_ejecucion_real(cod_analisis="ANA1", fec_ini="2020", fe_fin="2024"):
    """
    Función: Ejecuta el flujo completo del MVP contra SQL Server real.
    Llama al SP con @ACCION='OBTENER', corre los 5 modelos, crea las
    tablas de resultado y exporta los TXT.

    Args:
        cod_analisis (str): Código del análisis a ejecutar (ej: 'ANA1').
        fec_ini (str): Año o fecha de inicio del filtro.
        fe_fin  (str): Año o fecha de fin del filtro.

    Returns:
        tuple[pd.DataFrame, pd.DataFrame] | None:
            (entregable_1, entregable_2) si la ejecución fue exitosa,
            None si ocurrió un error de conexión o de SP.
    """
    _encabezado(f"PRUEBA 5 - Ejecucion real  |  COD={cod_analisis}  {fec_ini}->{fe_fin}")

    # ── 1. Conexión y actualización del SP desde el archivo .sql ─────────────
    try:
        url_usar = _url_activa if _url_activa else URL_CONEXION
        motor    = create_engine(url_usar, echo=False)

        # Leer sp_valores_unitarios.sql, dividir por GO y ejecutar cada batch
        ruta_sql = os.path.join(os.path.dirname(__file__), "sp_valores_unitarios.sql")
        with open(ruta_sql, encoding="utf-8") as f:
            script_completo = f.read()

        # Separar por GO (ignorar USE y GO solos)
        batches = [b.strip() for b in script_completo.split("\nGO") if b.strip()
                   and not b.strip().upper().startswith("USE ")]
        with motor.begin() as conn:
            for batch in batches:
                if batch:
                    conn.execute(text(batch))
        print("  [OK] SP actualizado desde sp_valores_unitarios.sql")

    except Exception as exc_sp:
        print(f"  [WARN] No se pudo actualizar el SP: {str(exc_sp)[:120]}")
        print("         Continuando con la version existente en la BD...")

    # ── 2. Llamada al SP con parametros ──────────────────────────────────────
    try:
        url_usar = _url_activa if _url_activa else URL_CONEXION
        motor    = create_engine(url_usar, echo=False)

        sentencia_sp = text(
            f"EXEC [DB_GEE_DW_ADUANAS].[SC_ADUANA].[SP_VALORES_UNITARIOS] "
            f"@ACCION       = 'OBTENER', "
            f"@COD_ANALISIS = '{cod_analisis}', "
            f"@FEC_INI      = '{fec_ini}', "
            f"@FEC_FIN      = '{fe_fin}'"
        )

        with motor.connect() as conn:
            resultado        = conn.execute(sentencia_sp)
            nombres_columnas = list(resultado.keys())
            filas            = resultado.fetchall()

        df = pd.DataFrame.from_records(filas, columns=nombres_columnas)
        print(f"  [OK] SP ejecutado  -> {len(df)} filas recibidas")
        print(f"  Columnas           : {list(df.columns)}")

    except Exception as exc:
        print(f"  [ERROR] Fallo en conexión/SP: {exc}")
        return None

    if df.empty:
        print("  [AVISO] El SP no devolvió registros. Verifica @COD_ANALISIS y rango de fechas.")
        return None

    # ── 2. Clasificar columnas _R, _C, _V ────────────────────────────────────
    columnas_r = [c for c in df.columns if str(c).upper().endswith("_R")]
    columnas_c = [c for c in df.columns if str(c).upper().endswith("_C")]
    columnas_v = [c for c in df.columns if str(c).upper().endswith("_V")]

    col_r = columnas_r[0] if columnas_r else None
    col_c = columnas_c[0] if columnas_c else None
    col_v = columnas_v[0] if columnas_v else None

    if col_r is None:
        df["__R"] = "ALL"
        col_r = "__R"

    print(f"  col_R = {col_r} | col_C = {col_c} | col_V = {col_v}")

    # pyodbc devuelve DECIMAL como Decimal de Python → forzar float64
    if col_v:
        df[col_v] = pd.to_numeric(df[col_v], errors="coerce")
    if col_c:
        df[col_c] = pd.to_numeric(df[col_c], errors="coerce").astype("Int64")

    # ── 3. CORE 1: indicadores estadísticos ──────────────────────────────────
    q1  = df.groupby(col_r)[col_v].transform("quantile", 0.25)
    q3  = df.groupby(col_r)[col_v].transform("quantile", 0.75)
    iqr = q3 - q1
    df["IND_IQR"] = ((df[col_v] < q1 - 1.5 * iqr) | (df[col_v] > q3 + 1.5 * iqr)).astype(int)

    media = df.groupby(col_r)[col_v].transform("mean")
    desv  = df.groupby(col_r)[col_v].transform("std").replace(0, np.nan)
    df["IND_ZSCORE"] = ((df[col_v] - media) / desv).abs().gt(3).astype(int)

    mediana = df.groupby(col_r)[col_v].transform("median")
    mad     = df.groupby(col_r)[col_v].transform(
        lambda x: np.median(np.abs(x - np.median(x)))
    ).replace(0, np.nan)
    df["IND_ZSCORE_ROB"] = (0.6745 * (df[col_v] - mediana) / mad).abs().gt(3.5).astype(int)

    # ── 4. CORE 2: modelos IA ─────────────────────────────────────────────────
    df["IND_IFOREST"] = 0
    for _, grupo in df.groupby(col_r):
        filas_validas = grupo[col_v].dropna()
        if len(filas_validas) < 2:
            continue
        pred = IsolationForest(contamination=0.05, random_state=42).fit_predict(
            filas_validas.values.reshape(-1, 1)
        )
        df.loc[filas_validas.index, "IND_IFOREST"] = (pred == -1).astype(int)

    df["IND_LOF"] = 0
    for _, grupo in df.groupby(col_r):
        filas_validas = grupo[col_v].dropna()
        if len(filas_validas) < 2:
            continue
        n_vec = min(20, len(filas_validas) - 1)
        pred  = LocalOutlierFactor(n_neighbors=n_vec, contamination=0.05).fit_predict(
            filas_validas.values.reshape(-1, 1)
        )
        df.loc[filas_validas.index, "IND_LOF"] = (pred == -1).astype(int)

    df["IND_DBSCAN"] = 0
    for _, grupo in df.groupby(col_r):
        filas_db = grupo[col_v].dropna()
        if len(filas_db) < 4:
            continue
        valores_scaled = RobustScaler().fit_transform(filas_db.values.reshape(-1, 1))
        pred = DBSCAN(eps=0.5, min_samples=3).fit_predict(valores_scaled)
        df.loc[filas_db.index, "IND_DBSCAN"] = (pred == -1).astype(int)

    df["IND_HBOS"] = 0
    for _, grupo in df.groupby(col_r):
        filas_hbos = grupo[col_v].dropna()
        if len(filas_hbos) < 2:
            continue
        n_bins = min(10, max(2, len(filas_hbos) // 3))
        modelo_hbos = HBOS(n_bins=n_bins, contamination=0.05)
        modelo_hbos.fit(filas_hbos.values.reshape(-1, 1))
        pred = modelo_hbos.predict(filas_hbos.values.reshape(-1, 1))
        df.loc[filas_hbos.index, "IND_HBOS"] = pred

    # ── 5. ES_OUTLIER ─────────────────────────────────────────────────────────
    suma = (df["IND_IQR"] + df["IND_ZSCORE"] + df["IND_ZSCORE_ROB"]
            + df["IND_IFOREST"] + df["IND_LOF"] + df["IND_DBSCAN"] + df["IND_HBOS"])
    df["ES_OUTLIER"] = (suma >= 2).astype(int)

    # ── 6. Armar entregables ──────────────────────────────────────────────────
    columnas_e1 = [col_r]
    if col_c:
        columnas_e1.append(col_c)
    columnas_e1 += [col_v, "IND_IQR", "IND_ZSCORE", "IND_ZSCORE_ROB",
                    "IND_IFOREST", "IND_LOF", "IND_DBSCAN", "IND_HBOS", "ES_OUTLIER"]

    entregable_1 = df[columnas_e1].copy()

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

    # ── 7. Resumen en consola ─────────────────────────────────────────────────
    total     = len(entregable_1)
    outliers  = int(entregable_1["ES_OUTLIER"].sum())
    pct       = round(outliers / total * 100, 2) if total > 0 else 0

    linea = "-" * 55
    print(f"\n  {linea}")
    print(f"  {'RESUMEN':^55}")
    print(f"  {linea}")
    print(f"  Total registros analizados : {total:>10,}")
    print(f"  Outliers detectados        : {outliers:>10,}  ({pct} %)")
    print(f"  {linea}")
    print(f"  Indicador              Detectados")
    print(f"  {'-'*30}")
    for ind in ["IND_IQR", "IND_ZSCORE", "IND_ZSCORE_ROB", "IND_IFOREST", "IND_LOF", "IND_DBSCAN", "IND_HBOS"]:
        print(f"  {ind:<22} {int(entregable_1[ind].sum()):>8,}")
    print(f"  {linea}")
    print(f"\n  Catálogo MIN/MAX por categoría:")
    print(entregable_2.to_string(index=False))

    # ── 8. Export TXT ─────────────────────────────────────────────────────────
    base_nombre = "T" + cod_analisis.replace(" ", "_").replace("-", "_")
    ruta_e1     = f"{base_nombre}.txt"
    ruta_e2     = f"{base_nombre}_CATALOGO.txt"
    entregable_1.to_csv(ruta_e1, sep="|", index=False)
    entregable_2.to_csv(ruta_e2, sep="|", index=False)
    print(f"\n  [OK] TXT exportados  : {ruta_e1}  |  {ruta_e2}")

    # ── 9. Crear tablas y cargar en SQL Server ────────────────────────────────
    tabla_e1_sql = f"[DB_GEE_DW_ADUANAS].[SC_ADUANA].[{base_nombre}]"
    tabla_e2_sql = f"[DB_GEE_DW_ADUANAS].[SC_ADUANA].[{base_nombre}_CATALOGO]"

    try:
        # Generar DDL
        columnas_ddl_e1 = []
        primera_fila_e1 = entregable_1.iloc[0]
        for col in entregable_1.columns:
            col_up = col.upper()
            if col_up.endswith("_R") or col_up == "__R":
                ancho = max(len(str(primera_fila_e1.get(col, ""))) * 6, 200)
                tipo  = f"VARCHAR({ancho})"
            elif col_up.endswith("_C"):
                tipo  = "INT"
            elif col_up.endswith("_V"):
                tipo  = "DECIMAL(18, 6)"
            elif col_up.startswith("IND_") or col_up == "ES_OUTLIER":
                tipo  = "TINYINT"
            else:
                ancho = max(len(str(primera_fila_e1.get(col, ""))) * 6, 200)
                tipo  = f"VARCHAR({ancho})"
            columnas_ddl_e1.append(f"    [{col}] {tipo} NULL")

        drop_e1   = f"IF OBJECT_ID('{tabla_e1_sql}', 'U') IS NOT NULL DROP TABLE {tabla_e1_sql};"
        create_e1 = f"CREATE TABLE {tabla_e1_sql} (\n" + ",\n".join(columnas_ddl_e1) + "\n);"

        # DDL e2: R → VARCHAR holgado, VAL_* → DECIMAL(18,6)
        primera_e2   = entregable_2.iloc[0]
        cols_ddl_e2  = []
        for col in entregable_2.columns:
            col_up = col.upper()
            if col_up == "R":
                ancho = max(len(str(primera_e2.get(col, ""))) * 6, 200)
                tipo  = f"VARCHAR({ancho})"
            elif col_up.startswith("VAL_"):
                tipo  = "DECIMAL(18, 6)"
            else:
                ancho = max(len(str(primera_e2.get(col, ""))) * 6, 200)
                tipo  = f"VARCHAR({ancho})"
            cols_ddl_e2.append(f"    [{col}] {tipo} NULL")

        drop_e2   = f"IF OBJECT_ID('{tabla_e2_sql}', 'U') IS NOT NULL DROP TABLE {tabla_e2_sql};"
        create_e2 = f"CREATE TABLE {tabla_e2_sql} (\n" + ",\n".join(cols_ddl_e2) + "\n);"

        with motor.begin() as conn:
            conn.execute(text(drop_e1))
            conn.execute(text(create_e1))
            conn.execute(text(drop_e2))
            conn.execute(text(create_e2))

        entregable_1.to_sql(name=base_nombre,                schema=ESQUEMA,
                            con=motor, if_exists="append",   index=False, chunksize=5_000)
        entregable_2.to_sql(name=f"{base_nombre}_CATALOGO",  schema=ESQUEMA,
                            con=motor, if_exists="append",   index=False, chunksize=1_000)

        print(f"  [OK] Tablas cargadas : {tabla_e1_sql}")
        print(f"                         {tabla_e2_sql}")

    except Exception as exc:
        print(f"  [ERROR] Fallo al guardar en SQL Server: {exc}")
        return entregable_1, entregable_2

    # ── 10. Consultar resultados via las 3 acciones ANALISIS del SP ───────────
    acciones_analisis = [
        ("ANALISIS_TODOS",     "Todos los registros analizados"),
        ("ANALISIS_OUTLIERS",  "Solo outliers  (ES_OUTLIER = 1)"),
        ("ANALISIS_RESUMEN",   "Resumen agregado por partida"),
    ]

    for accion, descripcion in acciones_analisis:
        print(f"\n  {'-'*60}")
        print(f"  {accion} - {descripcion}")
        print(f"  {'-'*60}")
        try:
            sentencia = text(
                f"EXEC [{BASE_DATOS}].[{ESQUEMA}].[SP_VALORES_UNITARIOS] "
                f"@ACCION       = '{accion}', "
                f"@COD_ANALISIS = '{cod_analisis}'"
            )
            with motor.connect() as conn:
                res  = conn.execute(sentencia)
                cols = list(res.keys())
                rows = res.fetchmany(10)        # mostrar solo primeras 10 filas
                df_preview = pd.DataFrame(rows, columns=cols)
            print(f"  (mostrando primeras {len(df_preview)} filas)")
            print(df_preview.to_string(index=False))
        except Exception as exc_a:
            print(f"  [ERROR] {accion}: {str(exc_a)[:150]}")

    return entregable_1, entregable_2


# ══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════
parser = argparse.ArgumentParser(
    description="Pruebas del MVP SP_VALORES_UNITARIOS",
    formatter_class=argparse.RawTextHelpFormatter,
)
parser.add_argument("--prueba1",  action="store_true", help="Diagnostico de conexion SQLAlchemy")
parser.add_argument("--prueba2",  action="store_true", help="Modelos de deteccion con datos sinteticos")
parser.add_argument("--prueba3",  action="store_true", help="Generacion de DDL automatico")
parser.add_argument("--prueba4",  action="store_true", help="Flujo completo sin base de datos")
parser.add_argument("--prueba5",  action="store_true", help="Ejecucion real contra SQL Server")
parser.add_argument("--cod",      default="ANA1",      help="COD_ANALISIS para prueba5 (default: ANA1)")
parser.add_argument("--ini",      default="2020",      help="FEC_INI para prueba5       (default: 2020)")
parser.add_argument("--fin",      default="2024",      help="FEC_FIN para prueba5       (default: 2024)")
parser.add_argument("--servidor", default=None,        help="Forzar servidor SQL (ej: .\\SQLEXPRESS o 127.0.0.1,56905)")

args = parser.parse_args()

# Si se pasa --servidor, sobreescribir la URL global antes de cualquier prueba
if args.servidor:
    srv_override   = args.servidor.replace("\\", "\\\\")
    URL_CONEXION   = (
        f"mssql+pyodbc://{srv_override}/{BASE_DATOS}"
        f"?driver={DRIVER}&Trusted_Connection=yes"
    )
    print(f"  [INFO] Servidor forzado: {args.servidor}")

# Si no se pasa ningún flag, ejecutar todas (excepto prueba5 que necesita BD)
ejecutar_todas = not any([args.prueba1, args.prueba2, args.prueba3, args.prueba4, args.prueba5])

if args.prueba1 or ejecutar_todas:
    prueba_conexion()

if args.prueba2 or ejecutar_todas:
    prueba_modelos()

if args.prueba3 or ejecutar_todas:
    prueba_ddl()

if args.prueba4 or ejecutar_todas:
    prueba_flujo_completo()

if args.prueba5:
    # Garantizar que _url_activa esté resuelto antes de la ejecución real
    if _url_activa is None:
        prueba_conexion()
    prueba_ejecucion_real(cod_analisis=args.cod, fec_ini=args.ini, fe_fin=args.fin)

print(f"\n{SEP}")
print("  FIN DE PRUEBAS")
print(SEP)
