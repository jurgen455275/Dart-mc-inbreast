# INB-H010-THRESHOLD-COMP01

## Estado previo

El experimento se preespecificó el 12 de noviembre de 2026 antes de ejecutar la extracción completa o conocer los resultados comparativos. El test histórico V7 permanece excluido.

## Pregunta

¿El umbral preservado DART-MC es una alternativa viable frente a controles clásicos cuando todos reciben RawNorm, la misma representación D, los mismos postfiltros, las mismas 23 variables y la misma validación anidada?

## Restricción principal

La fórmula DART-MC no puede cambiar:

`T=min(0.95,mean_M(D)+20*std_M(D)); D>T`

## Identidad y agrupación

INbreast no aporta PatientID utilizable en la copia disponible. `subject_surrogate` es un token del nombre de archivo que mantiene adquisiciones relacionadas dentro del mismo fold, pero no se declara como identidad de paciente verificada. Por tanto, H010 no permite una afirmación de validación a nivel de paciente.

## Decisión posterior

La ejecución reproducible terminó el 12 de noviembre de 2026 sobre las 327 imágenes previstas, con 9 483 filas de características (29 modos), cero fallos de calidad y sin entregar la etiqueta real al extractor. La rama DART-MC reprodujo H009: cero diferencias en conteos de candidatos y cero diferencias en las 327 predicciones anidadas.

DART-MC obtuvo TP=179, TN=57, FP=12 y FN=79: sensibilidad 69.38 %, especificidad 82.61 %, exactitud balanceada 75.99 %, F1 79.73 % y MCC 0.430. La precisión positiva fue 93.72 %.

El mejor control por la métrica primaria fue Kapur sobre el mismo mapa D: TP=219, TN=54, FP=15 y FN=39; sensibilidad 84.88 %, especificidad 78.26 % y exactitud balanceada 81.57 %. La diferencia DART-MC menos Kapur en exactitud balanceada fue −5.58 puntos porcentuales, con IC95 % bootstrap agrupado por `subject_surrogate` de −9.79 a −1.28 puntos. McNemar exacto produjo p=1.21×10⁻⁷ (7 imágenes correctas solo con DART-MC y 44 solo con Kapur).

Por tanto, H010 **no respalda superioridad de DART-MC** y favorece internamente a Kapur para exactitud balanceada. DART-MC conserva la mayor especificidad entre los métodos principales y se mantiene como propuesta adaptativa de alta especificidad, no como método ganador. Esta interpretación es interna, por imagen y específica de INbreast.

Para futura validación externa se congela DART-MC con la familia `simplified_9`, regularización L2=0.01 y umbral de decisión 0.4269318644. Su ajuste sobre todas las imágenes no se evalúa sobre entrenamiento; el rendimiento reportable continúa siendo el de las predicciones anidadas.
