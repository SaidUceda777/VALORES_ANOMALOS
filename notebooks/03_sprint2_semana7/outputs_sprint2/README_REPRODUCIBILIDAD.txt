ENTREGA SPRINT 2 - REPRODUCIBILIDAD

Comando sugerido:
    jupyter notebook sprint2_validacion_completa_valores_unitarios.ipynb

Parametros:
    seed=42
    periodo=2024-01-01 a 2024-12-31
    split=Split 70/30 dentro de cada NUM_SPN_R
    test_size=0.3
    umbral_z_robusto=3.5
    metrica_principal=F1-score
    metricas_secundarias=precision, recall, PR-AUC, detectados, tasa_detectada, latencia_ms

Protocolo:
    1. Carga unica de datos desde SQL Server.
    2. Snapshot con hash SHA256 antes de evaluar variantes.
    3. Split dentro de cada subpartida.
    4. Ajustes calculados solo con train.
    5. Evaluacion en test fijo para todas las variantes.
    6. Cross-validation por subpartida para estabilidad.
    7. Modelo auxiliar solo para importancia y calibracion.

Archivos generados:
    snapshot=outputs_sprint2\datos\snapshot_sprint2.csv
    metricas_ablation=outputs_sprint2\logs\metrics_ablation_sprint2.csv
    metricas_cv=outputs_sprint2\logs\metrics_cv_sprint2.csv
    metricas_cv_subpartida=outputs_sprint2\logs\metrics_cv_subpartida_sprint2.csv
    learning_curve=outputs_sprint2\logs\learning_curve_sprint2.csv
    importancia_features=outputs_sprint2\logs\feature_importance_sprint2.csv
    figura_ablation=outputs_sprint2\figuras\sprint2_pr_curve_ranking.png
    figura_learning=outputs_sprint2\figuras\sprint2_learning_curve_estabilidad.png
    figura_calibracion=outputs_sprint2\figuras\sprint2_calibracion_modelo_auxiliar.png

Hash snapshot SHA256:
    64e301537f11093ea2b54fd90fd4cb7c57825c226f3718c0eb70a65b9ceb6774

Decision tecnica:
    adoptar=B_LOG
    f1_cv_promedio=0.4830
    f1_cv_std=0.4303
    mejora_vs_baseline_cv=0.0604

Conclusion:
    Se adopta B_LOG porque presenta el mejor desempeno promedio en cross-validation por subpartida, mantiene el protocolo sin leakage, usa el mismo dataset que el baseline y conserva interpretabilidad tecnica.

Riesgos y siguientes pasos:
    1. La etiqueta y_true es proxy estadistica; requiere validacion experta.
    2. Monitorear drift por subpartida y aduana antes de produccion.
    3. Revisar falsos positivos por familia de producto y composicion declarada.