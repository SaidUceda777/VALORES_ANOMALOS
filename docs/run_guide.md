# Guía de ejecución

**Proyecto:** Detección de variaciones en el valor unitario — SUNAT

---

## Requisitos

```bash
pip install fastapi uvicorn sqlalchemy pyodbc numpy pandas scikit-learn pyod matplotlib seaborn
```

SQL Server Express corriendo con TCP habilitado.

---

## Paso 1 — Cargar datos

```sql
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS]
    @ACCION       = 'INGESTA',
    @RUTA_ARCHIVO = 'C:\Users\hp\Downloads\ROBOTICA\PROYECTO_TESIS\EXPORTACIONES_LIMPIO_UTF8_SIN_ERRORES.txt'
```

---

## Paso 2 — Verificar conexión

```bash
cd c:\Users\hp\Downloads\ROBOTICA\TESIS_2
python pruebas_mvp.py --prueba1
```

---

## Paso 3 — Ejecutar pipeline (consola)

```bash
python mvp_valores_unitarios.py
```

Genera en la carpeta raíz:
- `TANA1.txt` — outliers por registro
- `TANA1_CATALOGO.txt` — límites MIN/MAX por partida

---

## Paso 4 — EDA + Baseline (notebook)

Abrir en Jupyter:

```
notebooks/01_eda/eda_valores_unitarios.ipynb
```

```bash
jupyter notebook notebooks/01_eda/eda_valores_unitarios.ipynb
```

---

## Paso 5 — API + Frontend

**Backend:**
```bash
cd apps/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:** abrir directamente en el navegador:
```
apps/frontend/index.html
```

Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Consultas de resultado en SQL

```sql
-- Resumen por partida
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS] @ACCION='ANALISIS_RESUMEN',  @COD_ANALISIS='ANA1'

-- Solo outliers
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS] @ACCION='ANALISIS_OUTLIERS', @COD_ANALISIS='ANA1'

-- Calidad de datos
EXEC [SC_ADUANA].[SP_VALORES_UNITARIOS] @ACCION='EDA_NULOS'
```

---

## Pruebas rápidas (sin BD)

```bash
python pruebas_mvp.py --prueba4
```
