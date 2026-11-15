# DART-MC: paquete reproducible H010

Este repositorio acompaña la propuesta de investigación **DART-MC (Distribution-Adaptive Response Thresholding for Microcalcifications)** para clasificar, a nivel de imagen, la presencia de microcalcificaciones mamográficas. El umbral que se evalúa permanece invariable:

```text
T = min(0.95, mean_M(D) + 20 * std_M(D));  D > T
```

`D` es la respuesta normalizada de isotropía–energía y `M` es la máscara intramamaria válida. Los valores 20 y 0.95 se preservaron del algoritmo investigado; no se presentan como óptimos.

## Evidencia disponible

La comparación H010 utilizó 327 imágenes de INbreast, 258 positivas y 69 negativas, con validación anidada agrupada 5×4. No se dispuso de un PatientID verificado; `subject_surrogate` es únicamente un agrupador técnico derivado del nombre de archivo. Los resultados son internos, por imagen y no constituyen validación clínica.

| Método | TP | TN | FP | FN | Sensibilidad | Especificidad | Exactitud balanceada | Precisión positiva |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DART-MC | 179 | 57 | 12 | 79 | 69.38 % | 82.61 % | 75.99 % | 93.72 % |
| Kapur | 219 | 54 | 15 | 39 | 84.88 % | 78.26 % | 81.57 % | 93.59 % |

DART-MC mostró la mayor especificidad entre los métodos principales, pero Kapur obtuvo una exactitud balanceada 5.58 puntos porcentuales mayor. Por ello, DART-MC se presenta como una propuesta adaptativa de alta especificidad y no como el método ganador.

## Contenido

- `src/`: extractor C++ y dependencias fuente.
- `scripts/`: compilación, extracción, validación y generación del manuscrito.
- `experiments/`: configuración preespecificada y particiones congeladas.
- `results/`: características, predicciones fuera de muestra, métricas y modelos congelados.
- `docs/`: manuscrito candidato para IEEE EMBC 2027, versión editable, PDF verificado, figuras y guías de envío.
- `data/`: instrucciones para obtener INbreast; las mamografías no se redistribuyen.
- `REPRODUCIBILITY.md`: reproducción paso a paso y resultados esperados.
- `DECLARATIONS.md`: financiación, autoría, conflictos, ética y disponibilidad.
- `CITATION.cff`: metadatos de citación.
- `MANIFEST_SHA256.txt`: huellas de integridad de los archivos publicables.
- `UPLOAD_CHECKLIST.md`: comprobación final antes de publicar el repositorio.

## Instalación rápida en Windows

Requisitos: Python 3.11 o posterior, PowerShell y un compilador C++17 compatible (Visual Studio Build Tools o `g++`).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\scripts\build_h010_threshold_features.ps1
```

Para repetir la extracción se necesita una copia autorizada de INbreast:

```powershell
python .\scripts\extraer_caracteristicas_h010_comparadores.py `
  --dataset-root "C:\ruta\INbreast Release 1.0" --workers 2
python .\scripts\entrenar_h010_comparadores_anidados.py
python .\scripts\crear_figuras_embc2027_h010.py
python .\scripts\crear_articulo_embc2027_h010.py
```

La evaluación estadística y el manuscrito pueden regenerarse directamente desde los resultados incluidos, sin redistribuir las imágenes.

## Manuscrito candidato EMBC 2027

La entrega incluye `docs/DART_MC_EMBC_2027_SUBMISSION_CANDIDATE_H010.docx` y su PDF de cinco páginas revisado visualmente. Sigue la estructura 4+1 anunciada por EMBC 2027: cuatro páginas de contenido técnico y una quinta página de agradecimientos y referencias. Presenta H010 como propuesta reproducible con evidencia interna, no como sistema clínicamente validado ni como método superior.

La guía operativa está en `docs/GUIA_ENVIO_EMBC_2027.md` y el estado de preparación en `docs/EMBC_2027_READINESS.md`. Antes de enviar debe sustituirse el estilo generado por la plantilla oficial disponible en el portal y volver a comprobar página por página.

## Autores y afiliación

- Johnny Villalobos Murillo — `johnny.villalobos.murillo@una.ac.cr`
- Jurgen Herrera Alfaro — `jurgen.herrera.alfaro@est.una.ac.cr`

Laboratorio de Procesamiento de Imágenes Digitales (LAPID), Universidad Nacional de Costa Rica.

Johnny Villalobos Murillo es el autor de correspondencia.

## Financiación y conflictos

El trabajo recibió apoyo de la Universidad Nacional de Costa Rica por medio del LAPID. Los autores declaran no conocer conflictos financieros o personales relacionados con el trabajo; ambos deben confirmar esta declaración antes del envío científico.

## Licencia

Todavía no se ha elegido una licencia. Consulte `LICENSE_PENDING.md` antes de hacer público el repositorio. Hasta que se agregue un archivo `LICENSE`, no se concede permiso de reutilización del código.

