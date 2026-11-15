# Guía de envío a IEEE EMBC 2027

Actualizada el 14 de noviembre de 2026. Verifique nuevamente el portal oficial antes de enviar.

## 1. Modalidad recomendada

Enviar como **Full Contributed Paper** en el tema **Biomedical Imaging and Image Processing**. El trabajo debe presentarse como propuesta metodológica reproducible de umbralización adaptativa para clasificación de presencia de microcalcificaciones, con evaluación interna en INbreast. No debe describirse como dispositivo clínico, detector validado externamente ni método superior.

## 2. Requisitos oficiales vigentes

Según las páginas oficiales de EMBC 2027:

- Fecha límite del artículo completo: **24 de enero de 2027, 11:59 p. m. AoE**.
- Notificación: **16 de abril de 2027**.
- Versión final: **30 de abril de 2027**.
- Formato estricto **4+1**: páginas 1–4 para contenido técnico; página 5 solo para agradecimientos y referencias.
- Máximo de **20 referencias**; el candidato contiene 15.
- Idioma inglés, trabajo original y no sometido simultáneamente en otra sede.
- Debe utilizarse la plantilla oficial sin modificar márgenes, fuentes ni tamaños.
- Un autor debe ser designado como autor de correspondencia: Johnny Villalobos Murillo.
- Debe registrarse al menos un coautor elegible como revisor recíproco o declarar una exención veraz.
- El uso de inteligencia artificial generativa debe declararse en Acknowledgment indicando herramienta y alcance.
- Si es aceptado, debe presentarse presencialmente; la sede será Singapur, del 11 al 15 de julio de 2027.

Fuentes oficiales:

- https://embc.embs.org/2027/author-guidelines/
- https://embc.embs.org/2027/papers/
- https://embc.embs.org/2027/important-dates/
- https://embc.embs.org/2027/about/faqs/

## 3. Archivos ya preparados

- `DART_MC_EMBC_2027_SUBMISSION_CANDIDATE_H010.docx`: fuente editable.
- `DART_MC_EMBC_2027_SUBMISSION_CANDIDATE_H010.pdf`: candidato de cinco páginas revisado visualmente.
- `figures/embc2027/`: diagrama del método, comparación de métricas y auditoría del umbral.
- `EMBC_2027_READINESS.md`: estado, evidencia y pendientes.

El PDF actual es un candidato estructural. No debe enviarse hasta pasar el contenido a la plantilla oficial que proporcione el portal.

## 4. Pasos de los autores antes de abrir el envío

1. Johnny y Jurgen deben leer el artículo completo y aprobar cada afirmación, autoría y declaración.
2. Confirmar por escrito que no existen conflictos financieros, personales, de patentes o licencias. Si existe alguno, declararlo.
3. Solicitar a la Universidad Nacional la determinación institucional sobre ética/exención para este análisis secundario y la autorización aplicable de propiedad intelectual y divulgación.
4. Definir quién cumple los requisitos para revisión recíproca. Si nadie cumple, documentar y declarar la exención real en el portal.
5. Solicitar presupuesto para inscripción, viaje, alojamiento, seguro y eventual visa de Singapur.
6. Resolver la licencia del código. No publicar una licencia sin autorización institucional.
7. Cuando abra el portal, descargar la plantilla oficial 4+1 y migrar el contenido sin cambiar resultados.

## 5. Controles justo antes de enviar

1. Ejecutar `python scripts/verify_release.py` y exigir `OK`.
2. Comprobar que el PDF tiene exactamente cinco páginas y que la página 5 solo contiene Acknowledgment y References.
3. Verificar que las 15 referencias existen, sus DOI son correctos y se citan en orden.
4. Confirmar que las cifras del resumen, Tabla I, discusión y conclusión coinciden con los JSON/CSV archivados.
5. Confirmar que el texto conserva: 327 imágenes; 258 positivas; 69 negativas; TP=179; TN=57; FP=12; FN=79; BA=75.99%; especificidad=82.61%; y que Kapur obtiene BA=81.57%.
6. Mantener explícitos los límites: un solo dataset, sin PatientID verificado, agrupación sustituta, evaluación interna y sin validación clínica.
7. Ejecutar el comprobador de formato/PDF que ofrezca el portal y corregir únicamente maquetación.
8. Completar todos los autores y correos exactamente como aparecen en el manuscrito.
9. Designar a Johnny como autor de correspondencia y presentador previsto.
10. Guardar el PDF enviado, confirmación del portal, identificador de envío y fecha en un registro inmutable del proyecto.

## 6. Respuesta recomendada si preguntan por la contribución

DART-MC propone calcular el umbral sobre una respuesta estructural normalizada de cada mamografía, preservando la regla `T=min(0.95, mean_M(D)+20*std_M(D))`. La contribución demostrada es reproducibilidad e interpretabilidad del umbral por imagen bajo una evaluación interna controlada. La evidencia no demuestra superioridad ni utilidad clínica; esas son hipótesis para validación externa.
