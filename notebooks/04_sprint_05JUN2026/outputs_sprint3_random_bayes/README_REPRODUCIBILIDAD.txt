
ENTREGABLE SPRINT 3 - RANDOM SEARCH, BAYES SEARCH, PRUNING Y EARLY STOPPING

Fecha de ejecucion: 2026-06-05 19:32:50
Periodo: 2024-01-01 a 2024-12-31
Fuente de datos: SQL_SERVER
Seed: 42
Hash snapshot SHA256: 64e301537f11093ea2b54fd90fd4cb7c57825c226f3718c0eb70a65b9ceb6774

Objetivo:
Comparar configuraciones de deteccion de valores unitarios anomalos mediante Random Search y Bayes Search.

Regla metodologica:
Cada subpartida se evalua como universo independiente.
Los parametros se ajustan solo con train.
El test holdout se usa como verificacion final.

Presupuesto:
Random Search maximo: 30 trials
Bayes Search maximo: 30 trials
Top-K reportado: 10
Folds CV por subpartida: 3

Pruning:
Se corta una configuracion si, despues de 5 folds, su F1 parcial queda por debajo del baseline menos margen.
Margen pruning: 0.005

Early stopping:
Se detiene una busqueda si no mejora al menos 0.0005 durante 8 trials.

Configuracion ganadora:
{
  "metodo": "IQR",
  "feature": "LOG_VU",
  "k_iqr": 2.1085354970683277,
  "z_umbral": 2.681716165354331,
  "usar_winsor": false,
  "p_inf": 0.04670442449818708,
  "p_sup": 0.9789739304036299
}

Metricas holdout ganadora:
{
  "precision": 0.9542642509942554,
  "recall": 0.6825221238938053,
  "f1": 0.7958356366316566,
  "pr_auc": 0.6668053755662212,
  "detectados": 4526,
  "tasa_detectada": 0.03491691225254972,
  "latencia_ms": 259.1190999999071,
  "registros_test": 129622
}

Archivos principales:
- outputs_sprint3_random_bayes\logs\trials_random_bayes.csv
- outputs_sprint3_random_bayes\logs\top_k_configuraciones.csv
- outputs_sprint3_random_bayes\logs\resumen_experimentos.csv
- outputs_sprint3_random_bayes\modelos_config\config_ganadora.json
- outputs_sprint3_random_bayes\figuras\grafico_evolucion_f1_cv.png
- outputs_sprint3_random_bayes\figuras\matriz_confusion_ganadora.png
