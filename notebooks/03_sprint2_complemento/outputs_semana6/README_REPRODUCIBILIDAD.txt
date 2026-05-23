ENTREGA SPRINT SEMANA 6 - REPRODUCIBILIDAD

Comando sugerido:
    jupyter notebook sprint_semana6_resumido_autonomo.ipynb

Parametros:
    seed=42
    periodo=2024-01-01 a 2024-12-31
    split=Split 70/30 dentro de cada NUM_SPN_R
    metrica_principal=F1-score
    metricas_secundarias=precision, recall, PR-AUC, detectados, tasa_detectada, latencia_ms

Archivos generados:
    metricas=outputs_semana6\logs\metrics_experimentos_semana6.csv
    snapshot=outputs_semana6\datos\snapshot_semana6.csv
    figura=outputs_semana6\figuras\semana6_pr_curve_ranking.png

Hash snapshot SHA256:
    bd70c05d1c0f5e10f3628e56fa6f31bf6042f3b7f774966ed8814b776517c97f

Decision tecnica:
    adoptar=B_LOG - IQR sobre log1p(VU)
    f1=0.7327
    precision=0.7121
    recall=0.7545
    pr_auc=0.5500
    latencia_ms=137.5275

Riesgos y siguientes pasos:
    1. La etiqueta y_true es proxy estadistica; requiere validacion experta para reducir falsos positivos.
    2. Monitorear drift por subpartida y aduana antes de pasar a un flujo productivo.
    3. Siguiente sprint: calibrar umbrales por familia de producto y revisar errores por variable.