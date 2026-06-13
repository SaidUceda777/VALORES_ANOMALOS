DEMO 10-12 MIN - STORYTELLING TECNICO

Fecha de ejecucion: 2026-06-12 19:23:00
Seed: 42
Fuente de datos SQL Server: SQL_SERVER
Periodo configurado: 2024-01-01 a 2024-12-31

Regla metodologica:
1. La base se divide primero por NUM_PARTNANDI.
2. Los folds se crean dentro de cada subpartida.
3. Los parametros se ajustan con train.
4. El test se usa para evaluar.
5. Los outliers sinteticos se insertan solo para validar recuperacion conocida.
6. Las alertas reales no se interpretan como fraude, sino como priorizacion para revision.

Subpartidas usadas en demo:
[
  "1008509000-QUINUA, EXCEPTO PARA LA SIEMBRA",
  "1211909099-RAICES DE REGALIZ",
  "1005909000-LOS DEMAS MAICES",
  "1211903000-OREGANO (ORIGANUM VULGARE)",
  "1209919000-DEMAS SEMILLAS DE HORTALIZAS, PARA SIEMBRA"
]

Modelos:
[
  {
    "nombre": "IQR_SUBPARTIDA",
    "parametros": {
      "k": 1.5
    }
  },
  {
    "nombre": "ROBUST_Z_SUBPARTIDA",
    "parametros": {
      "z_umbral": 3.5
    }
  },
  {
    "nombre": "LOF_NOVELTY",
    "parametros": {
      "n_neighbors": 20,
      "contamination": 0.08
    }
  },
  {
    "nombre": "ISOLATION_FOREST",
    "parametros": {
      "contamination": 0.08,
      "n_estimators": 200
    }
  }
]

Artefactos:
- artifacts_demo_storytelling_sql_server\resultados_modelos_por_subpartida.csv
- artifacts_demo_storytelling_sql_server\ablaciones_global_vs_subpartida.csv
- artifacts_demo_storytelling_sql_server\alertas_reales_priorizadas.csv
- artifacts_demo_storytelling_sql_server\figura_clave_outliers_por_subpartida.png

Comando sugerido:
jupyter notebook demo_storytelling_subpartida_outliers.ipynb

MLflow:
Opcional. Si se usa, registrar parametros, metricas promedio por modelo y artefactos generados.