# Reproducción de H010

## 1. Alcance

Este procedimiento reproduce la comparación interna por imagen entre DART-MC y los controles clásicos sobre INbreast. La etiqueta real no se entrega al extractor C++. La clasificación se evalúa con predicciones fuera de muestra generadas por validación anidada agrupada.

## 2. Datos

Obtenga INbreast por la vía autorizada por sus responsables y conserve los DICOM en `AllDICOMs`. No copie los DICOM al repositorio. El registro incluido usa solo los nombres de archivo necesarios para localizar cada imagen con `--dataset-root`.

No se dispuso de PatientID verificado. `subject_surrogate` mantiene juntas adquisiciones con el mismo token de nombre, pero no demuestra independencia entre pacientes.

## 3. Entorno

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\scripts\build_h010_threshold_features.ps1
python .\scripts\verify_release.py
python .\scripts\verify_manifest.py
```

## 4. Extracción de características

```powershell
python .\scripts\extraer_caracteristicas_h010_comparadores.py `
  --dataset-root "C:\ruta\INbreast Release 1.0" `
  --workers 2
```

La salida esperada es `results/inbreast_v8_h010/features/h010_threshold_features_long.csv`, con 9 483 filas (327 imágenes × 29 modos), cero fallos de calidad y reproducción exacta de la rama DART-MC de H009 dentro de la tolerancia declarada.

## 5. Evaluación anidada

```powershell
python .\scripts\entrenar_h010_comparadores_anidados.py
```

La semilla, las familias de variables, la cuadrícula de regularización, la métrica primaria y las comparaciones se encuentran congeladas en `experiments/inbreast_v8/INB-H010-THRESHOLD-COMP01/config.json`.

Resultados principales esperados:

- DART-MC: TP=179, TN=57, FP=12, FN=79; sensibilidad=69.38 %, especificidad=82.61 %, exactitud balanceada=75.99 %.
- Kapur: TP=219, TN=54, FP=15, FN=39; sensibilidad=84.88 %, especificidad=78.26 %, exactitud balanceada=81.57 %.
- Diferencia DART-MC−Kapur en exactitud balanceada: −5.58 puntos porcentuales.
- IC95 % bootstrap agrupado por `subject_surrogate`: −9.79 a −1.28 puntos.
- McNemar exacto bilateral: p=1.21×10⁻⁷.

Los hashes y parámetros completos están en los archivos JSON de auditoría y resumen.

## 6. Figuras y manuscrito candidato EMBC 2027

```powershell
python .\scripts\crear_figuras_embc2027_h010.py
python .\scripts\crear_articulo_embc2027_h010.py
```

Las figuras se guardan en `docs/figures/embc2027/`. La salida editable es `docs/DART_MC_EMBC_2027_SUBMISSION_CANDIDATE_H010.docx`. El PDF incluido fue exportado con Microsoft Word y revisado visualmente en sus cinco páginas. El documento debe migrarse a la plantilla oficial descargada desde el portal EMBC 2027 y volver a exportarse antes del envío.

La construcción del manuscrito toma las cifras desde los CSV y JSON archivados; no vuelve a entrenar ni altera H010. El informe contiene una auditoría descriptiva del umbral: T mínimo 0.023, mediana 0.325, máximo 0.95 y activación del tope en 13 imágenes. Estos datos son post hoc y no se presentan como ajuste del algoritmo.

## 7. Modelo congelado

`results/inbreast_v8_h010/nested_evaluation/h010_frozen_dart_model.json` conserva la familia `simplified_9`, regularización L2=0.01 y umbral de decisión 0.4269318644 para una validación externa futura. Su ajuste sobre las 327 imágenes no debe confundirse con una evaluación sobre datos independientes; el rendimiento reportable es el de las predicciones anidadas.

