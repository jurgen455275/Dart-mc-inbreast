# Datos no incluidos

Las mamografías DICOM y anotaciones originales de INbreast no se incluyen ni deben confirmarse en Git. Obtenga el dataset por la vía autorizada por sus responsables y conserve localmente una estructura similar a:

```text
INbreast Release 1.0/
└── AllDICOMs/
    ├── <imagen>.dcm
    └── ...
```

Después indique esa carpeta mediante `--dataset-root`. El registro de referencia del repositorio contiene nombres de archivo y variables derivadas necesarias para la trazabilidad, no los píxeles originales.

