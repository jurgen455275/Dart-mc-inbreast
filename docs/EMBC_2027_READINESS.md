# Estado de preparación para EMBC 2027

Fecha de corte: 14 de noviembre de 2026.

## Dictamen actual

El paquete está **listo para revisión final de autores y migración a la plantilla oficial**, pero todavía no está listo para presionar Submit. El manuscrito ya tiene estructura 4+1, trazabilidad de cifras, controles clásicos, límites metodológicos explícitos y declaración de asistencia con IA. El algoritmo H010 y sus resultados no fueron modificados durante esta preparación.

## Evidencia directa archivada

- 327 predicciones fuera de muestra de validación anidada agrupada.
- Matriz DART-MC: TP=179, TN=57, FP=12, FN=79.
- Sensibilidad 69.38%, especificidad 82.61%, exactitud balanceada 75.99%.
- Control Kapur: exactitud balanceada 81.57%.
- Diferencia DART-MC menos Kapur: -5.58 puntos; IC95% bootstrap por grupo sustituto -9.79 a -1.28; McNemar bilateral p=1.21e-7.
- Auditoría descriptiva de T: mínimo 0.023, mediana 0.325, máximo 0.95; tope activo en 13 imágenes.
- Código fuente, configuración, particiones, características, predicciones, modelos y resúmenes disponibles en el repositorio.

## Fortalezas para revisión

- Pregunta estrecha y falsable centrada en el umbral adaptativo.
- Comparación bajo una tubería compartida contra ocho reglas clásicas.
- Evaluación fuera de muestra anidada y parámetros documentados.
- Resultado negativo frente a Kapur comunicado sin ocultarlo.
- Fórmula H010 preservada y especificación ejecutable en el artículo.
- Separación explícita entre evidencia directa, análisis post hoc y trabajo propuesto.

## Riesgos de rechazo que permanecen

1. Solo hay evidencia interna en INbreast y no existe cohorte externa independiente.
2. La sensibilidad de 69.38% no respalda uso autónomo de cribado.
3. No se dispone de PatientID verificado; `subject_surrogate` no demuestra independencia por paciente.
4. DART-MC no supera a Kapur en exactitud balanceada.
5. Falta adjudicación radiológica de errores y validación por adquisición/institución.
6. Falta una determinación institucional de ética/exención documentada.
7. La plantilla oficial del portal aún debe sustituir el formato generado.
8. Debe resolverse el revisor recíproco y la capacidad real de presentación presencial.

## Pendientes mínimos bajo control de los autores

- Aprobación línea por línea de ambos autores.
- Confirmación formal de conflictos de interés.
- Determinación ética/exención y autorización institucional de divulgación/IP.
- Elección institucional de licencia para el repositorio.
- Migración a la plantilla oficial y verificación del PDF.
- Registro del revisor recíproco o exención válida.
- Plan de financiación y presentación presencial.
- Creación de una versión etiquetada y, si procede, DOI de Zenodo después de resolver la licencia.

## Qué no debe cambiarse sin un nuevo experimento

- La regla H010, incluidos 20 y 0.95.
- Las predicciones anidadas y la matriz de confusión reportada.
- La selección de Kapur como control más fuerte observado.
- El carácter interno, exploratorio y no clínico de la evidencia.
- La ausencia de PatientID verificado.

Modificar cualquiera de esos elementos requiere un protocolo separado, estimación solo con datos de entrenamiento y nueva evaluación en datos no usados para elegir el cambio.
