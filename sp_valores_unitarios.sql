-- ============================================================
-- PROCEDIMIENTO CENTRALIZADO DE ANÁLISIS DE VALORES UNITARIOS
-- Base    : [DB_GEE_DW_ADUANAS]
-- Esquema : [SC_ADUANA]
-- Nombre  : [SP_VALORES_UNITARIOS]
--
-- ACCIONES:
--   'INGESTA'  → crea tabla raw y carga el TXT via BULK INSERT
--   'OBTENER'  → retorna columnas _C, _R, _V para análisis Python
--   'ANALISIS' → consulta la tabla de resultados guardada por Python
-- ============================================================

USE [DB_GEE_DW_ADUANAS];
GO

CREATE OR ALTER PROCEDURE [SC_ADUANA].[SP_VALORES_UNITARIOS]
    @ACCION         VARCHAR(50),
    @COD_ANALISIS   VARCHAR(50)  = NULL,
    @FEC_INI        VARCHAR(10)  = NULL,
    @FEC_FIN        VARCHAR(10)  = NULL,
    @RUTA_ARCHIVO   NVARCHAR(500) = N'C:\Users\hp\Downloads\ROBOTICA\PROYECTO_TESIS\EXPORTACIONES_LIMPIO_UTF8_SIN_ERRORES.txt'
AS
BEGIN
    SET NOCOUNT ON;

    -- ── Extraer año desde @FEC_INI / @FEC_FIN (formato YYYY-MM-DD) ────────────
    -- TRY_CAST devuelve NULL si la cadena no es fecha válida → YEAR(NULL) = NULL
    DECLARE @ANN_INI INT = YEAR(TRY_CAST(@FEC_INI AS DATE));
    DECLARE @ANN_FIN INT = YEAR(TRY_CAST(@FEC_FIN AS DATE));

    -- ══════════════════════════════════════════════════════════
    -- ACCIÓN: INGESTA
    -- Crea la tabla raw y carga el archivo plano via BULK INSERT
    -- ══════════════════════════════════════════════════════════
    IF @ACCION = 'INGESTA'
    BEGIN

        IF OBJECT_ID('[SC_ADUANA].[exportaciones_raw]', 'U') IS NOT NULL
            DROP TABLE [SC_ADUANA].[exportaciones_raw];

        CREATE TABLE [SC_ADUANA].[exportaciones_raw]
        (
            num_declaracion      VARCHAR(50)    NULL,
            anio                 VARCHAR(10)    NULL,
            cod_canal            VARCHAR(10)    NULL,
            canal                VARCHAR(100)   NULL,
            cod_aduamanifiesto   VARCHAR(10)    NULL,
            ann_manifiesto       VARCHAR(10)    NULL,
            num_manifiesto       VARCHAR(50)    NULL,
            num_partida          VARCHAR(50)    NULL,
            partida              VARCHAR(100)   NULL,
            num_secserie         VARCHAR(50)    NULL,
            cod_aduana           VARCHAR(10)    NULL,
            aduana               VARCHAR(200)   NULL,
            fob_dolar            VARCHAR(50)    NULL,
            peso_neto            VARCHAR(50)    NULL,
            peso_bruto           VARCHAR(50)    NULL,
            sector               VARCHAR(200)   NULL,
            tipo_producto        VARCHAR(200)   NULL,
            sector_name1         VARCHAR(200)   NULL,
            sector_name2         VARCHAR(200)   NULL,
            descripcion_comercial NVARCHAR(MAX) NULL
        );

        -- BULK INSERT dinámico para aceptar @RUTA_ARCHIVO como variable
        DECLARE @sql_bulk NVARCHAR(MAX) = N'
        BULK INSERT [SC_ADUANA].[exportaciones_raw]
        FROM ''' + @RUTA_ARCHIVO + N'''
        WITH
        (
            FIRSTROW        = 2,
            FIELDTERMINATOR = ''|'',
            ROWTERMINATOR   = ''0x0d0a'',
            CODEPAGE        = ''65001'',
            TABLOCK,
            KEEPNULLS,
            MAXERRORS       = 1000
        );';

        EXEC sp_executesql @sql_bulk;

        SELECT 'INGESTA OK' AS ESTADO,
               COUNT(*)     AS TOTAL_FILAS
        FROM [SC_ADUANA].[exportaciones_raw];

    END

    -- ══════════════════════════════════════════════════════════
    -- ACCIÓN: OBTENER
    -- Retorna columnas _C (temporal), _R (categoría), _V (valor)
    -- para que Python ejecute los modelos de detección
    -- ══════════════════════════════════════════════════════════
    ELSE IF @ACCION = 'OBTENER'
    BEGIN

        -- ── Cuadro ANA1: Valor unitario = FOB / Peso Neto ─────
        IF @COD_ANALISIS = 'ANA1'
        BEGIN
            SELECT
                CAST(anio AS INT)                                                  AS ANIO_C,
                CONCAT(NUM_PARTIDA, '-', PARTIDA)                                  AS NUM_SPN_R,
                fob_dolar / NULLIF(CAST(peso_neto AS DECIMAL(18, 3)), 0)           AS MTO_VALOR_UNTARIO_V
            FROM [DB_GEE_DW_ADUANAS].[SC_ADUANA].[EXPORTACIONES_RAW]
            WHERE peso_neto IS NOT NULL
              AND ISNUMERIC(peso_neto) = 1
              AND CAST(peso_neto AS DECIMAL(18, 3)) <> 0
              AND fob_dolar IS NOT NULL
              AND ISNUMERIC(fob_dolar) = 1
              AND (
                    @ANN_INI IS NULL
                    OR @ANN_FIN IS NULL
                    OR CAST(anio AS INT) BETWEEN @ANN_INI AND @ANN_FIN
                  );
        END

        -- ── Aquí se agregan futuros cuadros (ANA2, ANA3, ...) ─
        -- ELSE IF @COD_ANALISIS = 'ANA2' BEGIN ... END

    END

    -- ══════════════════════════════════════════════════════════
    -- ACCIÓN: EDA_BASE
    -- Base completa para EDA: campos relevantes + MTO_VALOR_UNTARIO_V calculado en SQL.
    -- No trae todos los campos, solo los necesarios para el análisis exploratorio.
    -- EXEC SP_VALORES_UNITARIOS @ACCION='EDA_BASE', @FEC_INI='2024-01-01', @FEC_FIN='2024-12-31'
    -- ══════════════════════════════════════════════════════════
    ELSE IF @ACCION = 'EDA_BASE'
    BEGIN

        SELECT
            CAST(anio AS INT)                                                  AS ANIO_C,
            CONCAT(num_partida, '-', partida)                                  AS NUM_SPN_R,
            CAST(
                TRY_CAST(fob_dolar AS DECIMAL(18,6))
                / NULLIF(TRY_CAST(peso_neto AS DECIMAL(18,6)), 0)
            AS DECIMAL(18,6))                                                  AS MTO_VALOR_UNTARIO_V,
            CAST(TRY_CAST(fob_dolar  AS DECIMAL(18,3)) AS DECIMAL(18,3))       AS FOB_DOLAR,
            CAST(TRY_CAST(peso_neto  AS DECIMAL(18,3)) AS DECIMAL(18,3))       AS PESO_NETO,
            sector                                                             AS SECTOR,
            tipo_producto                                                      AS TIPO_PRODUCTO
        FROM [SC_ADUANA].[exportaciones_raw]
        WHERE ISNUMERIC(fob_dolar)  = 1
          AND ISNUMERIC(peso_neto)  = 1
          AND TRY_CAST(peso_neto AS DECIMAL(18,3)) > 0
          AND fob_dolar IS NOT NULL
          AND peso_neto IS NOT NULL
          AND (
                @ANN_INI IS NULL
                OR @ANN_FIN IS NULL
                OR CAST(anio AS INT) BETWEEN @ANN_INI AND @ANN_FIN
              );

    END

    -- ══════════════════════════════════════════════════════════
    -- ACCIÓN: ANALISIS_TODOS
    -- Todos los registros analizados de la tabla resultado
    -- EXEC SP_VALORES_UNITARIOS @ACCION='ANALISIS_TODOS', @COD_ANALISIS='ANA1'
    -- ══════════════════════════════════════════════════════════
    ELSE IF @ACCION = 'ANALISIS_TODOS'
    BEGIN

        DECLARE @tabla_todos NVARCHAR(200) = N'[SC_ADUANA].[T' + @COD_ANALISIS + N']';
        DECLARE @sql_todos   NVARCHAR(MAX);

        SET @sql_todos = N'
        SELECT *
        FROM '  + @tabla_todos + N'
        ORDER BY NUM_SPN_R, ANIO_C;';

        EXEC sp_executesql @sql_todos;

    END

    -- ══════════════════════════════════════════════════════════
    -- ACCIÓN: ANALISIS_OUTLIERS
    -- Solo registros donde ES_OUTLIER = 1
    -- EXEC SP_VALORES_UNITARIOS @ACCION='ANALISIS_OUTLIERS', @COD_ANALISIS='ANA1'
    -- ══════════════════════════════════════════════════════════
    ELSE IF @ACCION = 'ANALISIS_OUTLIERS'
    BEGIN

        DECLARE @tabla_out NVARCHAR(200) = N'[SC_ADUANA].[T' + @COD_ANALISIS + N']';
        DECLARE @sql_out   NVARCHAR(MAX);

        SET @sql_out = N'
        SELECT *
        FROM '  + @tabla_out + N'
        WHERE ES_OUTLIER = 1
        ORDER BY NUM_SPN_R, ANIO_C;';

        EXEC sp_executesql @sql_out;

    END

    -- ══════════════════════════════════════════════════════════
    -- ACCIÓN: ANALISIS_RESUMEN
    -- Agregado por partida: total registros, outliers y conteo
    -- por cada indicador
    -- EXEC SP_VALORES_UNITARIOS @ACCION='ANALISIS_RESUMEN', @COD_ANALISIS='ANA1'
    -- ══════════════════════════════════════════════════════════
    ELSE IF @ACCION = 'ANALISIS_RESUMEN'
    BEGIN

        DECLARE @tabla_res NVARCHAR(200) = N'[SC_ADUANA].[T' + @COD_ANALISIS + N']';
        DECLARE @sql_res   NVARCHAR(MAX);

        SET @sql_res = N'
        SELECT
            NUM_SPN_R,
            COUNT(*)                             AS TOTAL_REGISTROS,
            SUM(CAST(ES_OUTLIER     AS INT))     AS TOTAL_OUTLIERS,
            CAST(
                ROUND(
                    100.0 * SUM(CAST(ES_OUTLIER AS FLOAT)) / NULLIF(COUNT(*), 0)
                , 2) AS DECIMAL(6,2))            AS PCT_OUTLIER,
            SUM(CAST(IND_IQR        AS INT))     AS CNT_IQR,
            SUM(CAST(IND_ZSCORE     AS INT))     AS CNT_ZSCORE,
            SUM(CAST(IND_ZSCORE_ROB AS INT))     AS CNT_ZSCORE_ROB,
            SUM(CAST(IND_IFOREST    AS INT))     AS CNT_IFOREST,
            SUM(CAST(IND_LOF        AS INT))     AS CNT_LOF,
            SUM(CAST(IND_DBSCAN     AS INT))     AS CNT_DBSCAN,
            SUM(CAST(IND_HBOS       AS INT))     AS CNT_HBOS
        FROM ' + @tabla_res + N'
        GROUP BY NUM_SPN_R
        ORDER BY TOTAL_OUTLIERS DESC;';

        EXEC sp_executesql @sql_res;

    END

    -- ══════════════════════════════════════════════════════════
    -- ► QUERIES EDA — ENTREGABLE 3
    -- ══════════════════════════════════════════════════════════

    -- ──────────────────────────────────────────────────────────
    -- ACCIÓN: EDA_NULOS
    -- Calidad de datos en exportaciones_raw:
    --   nulos, no numéricos y ceros en fob_dolar y peso_neto
    -- EXEC SP_VALORES_UNITARIOS @ACCION='EDA_NULOS'
    -- ──────────────────────────────────────────────────────────
    ELSE IF @ACCION = 'EDA_NULOS'
    BEGIN

        SELECT
            -- Total de registros en la tabla raw
            COUNT(*)                                              AS TOTAL_REGISTROS,

            -- ── fob_dolar ──────────────────────────────────────────
            SUM(CASE WHEN fob_dolar IS NULL
                       OR LTRIM(RTRIM(fob_dolar)) = ''
                     THEN 1 ELSE 0 END)                          AS FOB_NULOS,

            SUM(CASE WHEN fob_dolar IS NOT NULL
                       AND LTRIM(RTRIM(fob_dolar)) <> ''
                       AND ISNUMERIC(fob_dolar) = 0
                     THEN 1 ELSE 0 END)                          AS FOB_NO_NUMERICO,

            SUM(CASE WHEN ISNUMERIC(fob_dolar) = 1
                       AND TRY_CAST(fob_dolar AS DECIMAL(18,3)) <= 0
                     THEN 1 ELSE 0 END)                          AS FOB_CERO_O_NEG,

            -- ── peso_neto ──────────────────────────────────────────
            SUM(CASE WHEN peso_neto IS NULL
                       OR LTRIM(RTRIM(peso_neto)) = ''
                     THEN 1 ELSE 0 END)                          AS PESO_NULOS,

            SUM(CASE WHEN peso_neto IS NOT NULL
                       AND LTRIM(RTRIM(peso_neto)) <> ''
                       AND ISNUMERIC(peso_neto) = 0
                     THEN 1 ELSE 0 END)                          AS PESO_NO_NUMERICO,

            SUM(CASE WHEN ISNUMERIC(peso_neto) = 1
                       AND TRY_CAST(peso_neto AS DECIMAL(18,3)) <= 0
                     THEN 1 ELSE 0 END)                          AS PESO_CERO_O_NEG,

            -- ── num_partida / partida ──────────────────────────────
            SUM(CASE WHEN num_partida IS NULL
                       OR LTRIM(RTRIM(num_partida)) = ''
                     THEN 1 ELSE 0 END)                          AS PARTIDA_NULOS,

            -- ── anio ───────────────────────────────────────────────
            SUM(CASE WHEN anio IS NULL
                       OR ISNUMERIC(anio) = 0
                     THEN 1 ELSE 0 END)                          AS ANIO_INVALIDO,

            -- ── Registros válidos para calcular valor unitario ─────
            SUM(CASE
                    WHEN fob_dolar  IS NOT NULL AND ISNUMERIC(fob_dolar)  = 1
                     AND peso_neto  IS NOT NULL AND ISNUMERIC(peso_neto)  = 1
                     AND TRY_CAST(peso_neto AS DECIMAL(18,3)) > 0
                    THEN 1 ELSE 0
                END)                                             AS REGISTROS_VALIDOS_VU,

            -- ── Duplicados exactos (num_declaracion + num_secserie) ─
            COUNT(*) - COUNT(DISTINCT CONCAT(num_declaracion, '|', num_secserie)) AS DUPLICADOS_APROX

        FROM [SC_ADUANA].[exportaciones_raw];

    END

    -- ──────────────────────────────────────────────────────────
    -- ACCIÓN: EDA_DISTRIBUCION
    -- Percentiles del valor unitario (FOB/peso_neto) a nivel global
    -- y estadísticos de dispersión para detectar asimetría.
    -- EXEC SP_VALORES_UNITARIOS @ACCION='EDA_DISTRIBUCION'
    -- ──────────────────────────────────────────────────────────
    ELSE IF @ACCION = 'EDA_DISTRIBUCION'
    BEGIN

        -- Patrón CTE separada: PERCENTILE_CONT OVER() no se puede mezclar con COUNT/AVG/etc.
        -- en el mismo SELECT. Solución: una CTE para agregados, otra para percentiles,
        -- luego CROSS JOIN (ambas devuelven 1 fila global).
        WITH base AS (
            SELECT
                TRY_CAST(fob_dolar AS DECIMAL(18, 6))
                    / NULLIF(TRY_CAST(peso_neto AS DECIMAL(18, 6)), 0)         AS VU
            FROM [SC_ADUANA].[exportaciones_raw]
            WHERE ISNUMERIC(fob_dolar)  = 1
              AND ISNUMERIC(peso_neto)  = 1
              AND TRY_CAST(peso_neto AS DECIMAL(18, 3)) > 0
              AND (
                    @ANN_INI IS NULL
                    OR @ANN_FIN IS NULL
                    OR TRY_CAST(anio AS INT) BETWEEN @ANN_INI AND @ANN_FIN
                  )
        ),
        agg AS (
            SELECT
                COUNT(VU)                       AS N,
                CAST(AVG(VU)   AS DECIMAL(18,4)) AS MEDIA,
                CAST(STDEV(VU) AS DECIMAL(18,4)) AS DESV_STD,
                CAST(MIN(VU)   AS DECIMAL(18,4)) AS MINIMO,
                CAST(MAX(VU)   AS DECIMAL(18,4)) AS MAXIMO
            FROM base
        ),
        pct AS (
            SELECT DISTINCT
                CAST(PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY VU) OVER () AS DECIMAL(18,4)) AS P01,
                CAST(PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY VU) OVER () AS DECIMAL(18,4)) AS P05,
                CAST(PERCENTILE_CONT(0.10) WITHIN GROUP (ORDER BY VU) OVER () AS DECIMAL(18,4)) AS P10,
                CAST(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY VU) OVER () AS DECIMAL(18,4)) AS Q1,
                CAST(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY VU) OVER () AS DECIMAL(18,4)) AS MEDIANA,
                CAST(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY VU) OVER () AS DECIMAL(18,4)) AS Q3,
                CAST(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY VU) OVER () AS DECIMAL(18,4)) AS P90,
                CAST(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY VU) OVER () AS DECIMAL(18,4)) AS P95,
                CAST(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY VU) OVER () AS DECIMAL(18,4)) AS P99
            FROM base
        )
        SELECT
            a.N, a.MEDIA, a.DESV_STD, a.MINIMO,
            p.P01, p.P05, p.P10, p.Q1, p.MEDIANA, p.Q3, p.P90, p.P95, p.P99,
            a.MAXIMO,
            CAST(p.P99 / NULLIF(p.MEDIANA, 0) AS DECIMAL(18,2))                AS RATIO_P99_P50
        FROM agg a
        CROSS JOIN pct p;

    END

    -- ──────────────────────────────────────────────────────────
    -- ACCIÓN: EDA_PARTIDAS
    -- Top 30 partidas arancelarias por volumen de registros,
    -- con estadísticos del valor unitario por partida.
    -- EXEC SP_VALORES_UNITARIOS @ACCION='EDA_PARTIDAS'
    -- ──────────────────────────────────────────────────────────
    ELSE IF @ACCION = 'EDA_PARTIDAS'
    BEGIN

        -- Patrón CTE separada: VU se pre-calcula a nivel de fila.
        -- agg: COUNT/AVG/MIN/MAX agrupados por partida.
        -- pct: PERCENTILE_CONT OVER(PARTITION BY partida) + SELECT DISTINCT → 1 fila/partida.
        -- JOIN final entrega el TOP 30 por volumen.
        WITH datos_p AS (
            SELECT
                CONCAT(num_partida, '-', partida)                          AS NUM_SPN_R,
                CASE WHEN ISNUMERIC(fob_dolar) = 1 AND ISNUMERIC(peso_neto) = 1
                          AND TRY_CAST(peso_neto AS DECIMAL(18,3)) > 0
                     THEN TRY_CAST(fob_dolar AS DECIMAL(18,6))
                              / NULLIF(TRY_CAST(peso_neto AS DECIMAL(18,6)), 0)
                     ELSE NULL END                                         AS VU
            FROM [SC_ADUANA].[exportaciones_raw]
            WHERE (
                    @ANN_INI IS NULL
                    OR @ANN_FIN IS NULL
                    OR TRY_CAST(anio AS INT) BETWEEN @ANN_INI AND @ANN_FIN
                  )
        ),
        agg_p AS (
            SELECT
                NUM_SPN_R,
                COUNT(*)                        AS N_REGISTROS,
                COUNT(VU)                       AS N_VALIDOS,
                CAST(AVG(VU) AS DECIMAL(18,4))  AS VU_MEDIA,
                CAST(MIN(VU) AS DECIMAL(18,4))  AS VU_MIN,
                CAST(MAX(VU) AS DECIMAL(18,4))  AS VU_MAX
            FROM datos_p
            GROUP BY NUM_SPN_R
        ),
        pct_p AS (
            SELECT DISTINCT
                NUM_SPN_R,
                CAST(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY VU)
                     OVER (PARTITION BY NUM_SPN_R) AS DECIMAL(18,4))      AS VU_MEDIANA
            FROM datos_p
        )
        SELECT TOP 30
            a.NUM_SPN_R,
            a.N_REGISTROS,
            a.N_VALIDOS,
            a.VU_MEDIA,
            p.VU_MEDIANA,
            a.VU_MIN,
            a.VU_MAX
        FROM agg_p  a
        JOIN pct_p  p ON a.NUM_SPN_R = p.NUM_SPN_R
        ORDER BY a.N_REGISTROS DESC;

    END

    -- ──────────────────────────────────────────────────────────
    -- ACCIÓN: EDA_TEMPORAL
    -- Evolución anual del valor unitario (detección de drift):
    --   mediana, IQR, P95, N registros por año.
    -- EXEC SP_VALORES_UNITARIOS @ACCION='EDA_TEMPORAL'
    -- ──────────────────────────────────────────────────────────
    ELSE IF @ACCION = 'EDA_TEMPORAL'
    BEGIN

        -- Patrón CTE separada: VU pre-calculado a nivel de fila.
        -- agg_t: COUNT/AVG agrupados por año.
        -- pct_t: PERCENTILE_CONT OVER(PARTITION BY ANIO) + SELECT DISTINCT → 1 fila/año.
        -- IQR = Q3 - Q1 en la consulta externa sobre valores ya consolidados.
        WITH datos_t AS (
            SELECT
                TRY_CAST(anio AS INT)                                          AS ANIO,
                CASE WHEN ISNUMERIC(fob_dolar) = 1 AND ISNUMERIC(peso_neto) = 1
                          AND TRY_CAST(peso_neto AS DECIMAL(18,3)) > 0
                     THEN TRY_CAST(fob_dolar AS DECIMAL(18,6))
                              / NULLIF(TRY_CAST(peso_neto AS DECIMAL(18,6)), 0)
                     ELSE NULL END                                             AS VU
            FROM [SC_ADUANA].[exportaciones_raw]
            WHERE TRY_CAST(anio AS INT) IS NOT NULL
        ),
        agg_t AS (
            SELECT
                ANIO,
                COUNT(*)                        AS N_REGISTROS,
                COUNT(VU)                       AS N_VALIDOS,
                CAST(AVG(VU) AS DECIMAL(18,4))  AS VU_MEDIA
            FROM datos_t
            GROUP BY ANIO
        ),
        pct_t AS (
            SELECT DISTINCT
                ANIO,
                CAST(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY VU)
                     OVER (PARTITION BY ANIO) AS DECIMAL(18,4))                AS VU_Q1,
                CAST(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY VU)
                     OVER (PARTITION BY ANIO) AS DECIMAL(18,4))                AS VU_MEDIANA,
                CAST(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY VU)
                     OVER (PARTITION BY ANIO) AS DECIMAL(18,4))                AS VU_Q3,
                CAST(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY VU)
                     OVER (PARTITION BY ANIO) AS DECIMAL(18,4))                AS VU_P95
            FROM datos_t
        )
        SELECT
            a.ANIO,
            a.N_REGISTROS,
            a.N_VALIDOS,
            a.VU_MEDIA,
            p.VU_Q1,
            p.VU_MEDIANA,
            p.VU_Q3,
            p.VU_P95,
            CAST(p.VU_Q3 - p.VU_Q1 AS DECIMAL(18,4))                          AS VU_IQR
        FROM agg_t a
        JOIN pct_t p ON a.ANIO = p.ANIO
        ORDER BY a.ANIO;

    END

    -- ──────────────────────────────────────────────────────────
    -- ACCIÓN: EDA_BALANCE
    -- Resumen del balance de outliers en una tabla de resultados.
    -- Muestra % de outliers por indicador y total.
    -- EXEC SP_VALORES_UNITARIOS @ACCION='EDA_BALANCE', @COD_ANALISIS='ANA1'
    -- ──────────────────────────────────────────────────────────
    ELSE IF @ACCION = 'EDA_BALANCE'
    BEGIN

        DECLARE @tabla_bal NVARCHAR(200) = N'[SC_ADUANA].[T' + @COD_ANALISIS + N']';
        DECLARE @sql_bal   NVARCHAR(MAX);

        SET @sql_bal = N'
        SELECT
            COUNT(*)                                                     AS N_TOTAL,
            SUM(CAST(ES_OUTLIER     AS INT))                             AS N_OUTLIER,
            SUM(1 - CAST(ES_OUTLIER AS INT))                             AS N_NORMAL,
            CAST(ROUND(100.0 * SUM(CAST(ES_OUTLIER AS FLOAT))
                / NULLIF(COUNT(*), 0), 2) AS DECIMAL(6,2))              AS PCT_OUTLIER,
            SUM(CAST(IND_IQR        AS INT))                             AS CNT_IQR,
            CAST(ROUND(100.0 * SUM(CAST(IND_IQR AS FLOAT))
                / NULLIF(COUNT(*), 0), 2) AS DECIMAL(6,2))              AS PCT_IQR,
            SUM(CAST(IND_ZSCORE     AS INT))                             AS CNT_ZSCORE,
            CAST(ROUND(100.0 * SUM(CAST(IND_ZSCORE AS FLOAT))
                / NULLIF(COUNT(*), 0), 2) AS DECIMAL(6,2))              AS PCT_ZSCORE,
            SUM(CAST(IND_ZSCORE_ROB AS INT))                             AS CNT_ZSCORE_ROB,
            CAST(ROUND(100.0 * SUM(CAST(IND_ZSCORE_ROB AS FLOAT))
                / NULLIF(COUNT(*), 0), 2) AS DECIMAL(6,2))              AS PCT_ZSCORE_ROB,
            SUM(CAST(IND_IFOREST    AS INT))                             AS CNT_IFOREST,
            CAST(ROUND(100.0 * SUM(CAST(IND_IFOREST AS FLOAT))
                / NULLIF(COUNT(*), 0), 2) AS DECIMAL(6,2))              AS PCT_IFOREST,
            SUM(CAST(IND_LOF        AS INT))                             AS CNT_LOF,
            CAST(ROUND(100.0 * SUM(CAST(IND_LOF AS FLOAT))
                / NULLIF(COUNT(*), 0), 2) AS DECIMAL(6,2))              AS PCT_LOF,
            SUM(CAST(IND_DBSCAN     AS INT))                             AS CNT_DBSCAN,
            CAST(ROUND(100.0 * SUM(CAST(IND_DBSCAN AS FLOAT))
                / NULLIF(COUNT(*), 0), 2) AS DECIMAL(6,2))              AS PCT_DBSCAN,
            SUM(CAST(IND_HBOS       AS INT))                             AS CNT_HBOS,
            CAST(ROUND(100.0 * SUM(CAST(IND_HBOS AS FLOAT))
                / NULLIF(COUNT(*), 0), 2) AS DECIMAL(6,2))              AS PCT_HBOS
        FROM ' + @tabla_bal + N';';

        EXEC sp_executesql @sql_bal;

    END

END
GO
