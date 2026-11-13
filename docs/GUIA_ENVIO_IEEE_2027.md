# Guía de envío para DART-MC

Fecha de revisión: 12 de noviembre de 2026.

## Recomendación principal

La primera opción recomendada es **IEEE EMBC 2027**, en la línea de *Biomedical Imaging and Image Processing*. El evento está anunciado para el 11–15 de julio de 2027 en Singapur. La convocatoria oficial indica apertura del portal en diciembre de 2026, fecha límite de artículo completo el 24 de enero de 2027 y formato de cinco páginas: cuatro páginas técnicas más una quinta para referencias, agradecimientos y declaraciones. El idioma es inglés y se exige la plantilla IEEE.

- Convocatoria: https://embc.embs.org/2027/papers/
- Preguntas frecuentes: https://embc.embs.org/2027/about/faqs/

El manuscrito actual usa diseño IEEE genérico a dos columnas y deberá ajustarse a la plantilla exacta de EMBC después de confirmar esa sede. La contribución debe presentarse como propuesta metodológica con validación interna, no como herramienta clínica.

## Alternativas

### IEEE Latin America Transactions

Es una alternativa de revista regional compatible con procesamiento de imágenes y aplicaciones biomédicas. Recibe manuscritos de forma continua y solicita artículos de investigación de 6–9 páginas a dos columnas. Requiere, además del manuscrito, carta, resumen gráfico y resumen en video; las referencias deben incluir DOI cuando exista. La revista solicita una declaración ética cuando se utilizan bases de datos de sujetos humanos.

- Instrucciones: https://latamt.ieeer9.org/index.php/transactions/about/submissions
- Preguntas frecuentes: https://latamt.ieeer9.org/index.php/transactions/FrequentlyAskedQuestions

Para esta opción conviene ampliar la discusión, añadir validación externa y cerrar primero el dictamen ético institucional.

### CONESCAPAN 2027

Es una opción temática y regional razonable, pero al 12 de noviembre de 2026 no se localizó una convocatoria oficial verificable para 2027. No se debe adaptar el artículo con requisitos de 2026 como si fueran vigentes. Se recomienda esperar la convocatoria oficial de IEEE Sección Costa Rica o Región 9.

### IEEE ISBI 2027

Es una sede muy alineada con imágenes biomédicas, pero la fecha límite oficial de artículos completos fue el 2 de noviembre de 2026 y ya pasó. Los resúmenes de una página no se incorporan a las actas; por tanto, no son equivalentes a publicar el artículo completo.

- Sitio: https://biomedicalimaging.org/2027/
- Envíos: https://biomedicalimaging.org/2027/papers/

## Lista mínima antes del envío

1. **Dictamen ético o exención.** Solicitar al comité institucional que determine si el análisis secundario de INbreast requiere aprobación o exención. No inventar un número de aprobación.
2. **Identidad de pacientes.** Mantener `subject_surrogate` como agrupador técnico y declarar que no es PatientID verificado. No afirmar desempeño ni independencia a nivel de paciente.
3. **Autor de correspondencia.** Definir cuál de los dos coautores responderá por el envío. Ambos correos institucionales ya aparecen en el manuscrito: `johnny.villalobos.murillo@una.ac.cr` y `jurgen.herrera.alfaro@est.una.ac.cr`.
4. **Declaraciones.** El manuscrito ya declara apoyo de la Universidad Nacional de Costa Rica por medio del LAPID, coautoría conjunta y ausencia de conflictos conocidos. Antes de enviarlo, ambos autores deben confirmar que la declaración de conflicto es verdadera y completar una contribución CRediT más específica si la sede la solicita.
5. **Repositorio persistente.** Publicar el paquete reproducible en un repositorio con versión congelada; preferiblemente obtener DOI mediante Zenodo.
6. **Plantilla final.** Migrar el contenido a la plantilla oficial de la sede elegida y comprobar páginas, anonimización y política de uso de inteligencia artificial.
7. **Revisión científica.** Hacer una lectura final con el coordinador del proyecto y, si es posible, con una persona con experiencia clínica o radiológica.

## Lo que ya queda resuelto

- Comparación preregistrada de DART-MC contra controles clásicos con la misma representación y validación.
- Evaluación anidada agrupada y predicciones por imagen trazables.
- Configuración DART-MC congelada para una futura validación externa.
- Manuscrito IEEE genérico con límites de evidencia explícitos.
- Ausencia de afirmaciones clínicas o a nivel de paciente.
- Financiación institucional, coautoría y correos institucionales incorporados.
- Declaración estándar de ausencia de conflictos de interés incorporada, sujeta a confirmación personal de ambos autores.

## Lo que no debe afirmarse

- Que DART-MC está validado clínicamente.
- Que el agrupador sustituto identifica pacientes.
- Que INbreast constituye validación externa independiente.
- Que DART-MC es universalmente superior a los métodos clásicos.
- Que los valores 20 y 0.95 son óptimos o completamente adaptativos.
