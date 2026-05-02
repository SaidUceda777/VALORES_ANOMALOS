# Guía de Despliegue

**Proyecto:** Detección de variaciones en el valor unitario — SUNAT  
**Stack:** Python (FastAPI) + HTML / CSS / JS  
**Servidor actual:** Python — Uvicorn  
**Migración futura:** Java — Spring Boot (ver sección al final)

---

## Arquitectura general

```
┌─────────────────────────────────────────────┐
│  FRONTEND  (apps/frontend/)                 │
│  index.html · styles.css · app.js          │
│  Navegador — sin framework, vanilla JS      │
└─────────────────────┬───────────────────────┘
                      │ HTTP (fetch API)
                      │ POST /analizar
                      │ GET  /health
┌─────────────────────▼───────────────────────┐
│  BACKEND   (apps/backend/main.py)           │
│  FastAPI — Uvicorn                          │
│  Puerto: 8000                               │
└─────────────────────┬───────────────────────┘
                      │ SQLAlchemy + pyodbc
┌─────────────────────▼───────────────────────┐
│  BASE DE DATOS                              │
│  SQL Server Express — DB_GEE_DW_ADUANAS     │
│  [SC_ADUANA].[SP_VALORES_UNITARIOS]         │
└─────────────────────────────────────────────┘
```

---

## Estructura de archivos

```
TESIS_2/
├── apps/
│   ├── frontend/
│   │   ├── index.html      ← UI principal
│   │   ├── styles.css      ← estilos
│   │   └── app.js          ← lógica y llamadas a la API
│   └── backend/
│       └── main.py         ← FastAPI (servidor Python)
└── docs/
    ├── dataset.md          ← este archivo
    └── deployment.md       ← esta guía
```

---

## 1. Requisitos previos

```bash
pip install fastapi uvicorn sqlalchemy pyodbc numpy pandas scikit-learn pyod
```

Verificar SQL Server Express corriendo:
```powershell
Get-Service MSSQL$SQLEXPRESS
```

---

## 2. Levantar el servidor Python

```bash
cd c:\Users\hp\Downloads\ROBOTICA\TESIS_2\apps\backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

La API queda disponible en:
- Documentación Swagger: http://localhost:8000/docs
- Health check: http://localhost:8000/health

---

## 3. Abrir el frontend

Simplemente abrir el archivo en el navegador:

```
apps/frontend/index.html
```

O servir con Python para evitar restricciones CORS en desarrollo:

```bash
cd c:\Users\hp\Downloads\ROBOTICA\TESIS_2\apps\frontend
python -m http.server 3000
# Abrir: http://localhost:3000
```

---

## 4. Endpoints de la API

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Estado del servidor y conexión a BD |
| `POST` | `/analizar` | Ejecuta el pipeline de detección completo |
| `GET` | `/resultados/{cod_analisis}` | Consulta resultados ya guardados |

### POST /analizar — body

```json
{
  "cod_analisis": "ANA1",
  "fec_ini": "2023-01-01",
  "fec_fin": "2023-12-31"
}
```

### POST /analizar — respuesta

```json
{
  "cod_analisis": "ANA1",
  "total_registros": 15420,
  "total_outliers": 312,
  "pct_outlier": 2.02,
  "indicadores": {
    "IND_IQR": 280,
    "IND_ZSCORE": 195,
    "IND_ZSCORE_ROB": 260,
    "IND_IFOREST": 310,
    "IND_LOF": 298,
    "IND_DBSCAN": 180,
    "IND_HBOS": 305
  },
  "outliers": [
    {
      "NUM_SPN_R": "7108120000-ORO EN LAS DEMAS FORMAS EN BRUTO",
      "ANIO_C": 2023,
      "MTO_VALOR_UNTARIO_V": 0.001,
      "ES_OUTLIER": 1
    }
  ]
}
```

---

## Opción de migración a Java (Spring Boot)

El servidor Python (Uvicorn + FastAPI) puede reemplazarse por Spring Boot manteniendo exactamente los mismos endpoints. El procesamiento ML permanece en Python.

**Arquitectura híbrida:**

```
Frontend (HTML/CSS/JS)
      │
      ▼
Spring Boot (Java) — puerto 8080
  ├── /health     → responde directamente
  ├── /analizar   → llama a Python microservicio
  └── /resultados → consulta SQL Server
      │
      ▼
Python ML Service — puerto 8001
  └── POST /run_pipeline → ejecuta detección de outliers
      │
      ▼
SQL Server
```

**Archivos Java necesarios (cuando se migre):**
```
apps/backend-java/
├── pom.xml
└── src/main/java/com/sunat/outliers/
    ├── OutliersApplication.java
    ├── controller/AnalisisController.java
    └── service/PipelineService.java
```

Los archivos Python y Java pueden coexistir. Actualmente se usa solo el servidor Python.
