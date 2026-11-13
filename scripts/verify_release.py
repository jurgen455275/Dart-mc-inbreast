#!/usr/bin/env python3
"""Comprueba que el paquete Git no contenga datos o rutas personales obvias."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {".dcm", ".dicom"}
TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".ps1", ".cpp", ".h", ".json", ".csv",
    ".yml", ".yaml", ".cff",
}
PERSONAL_PATHS = [
    re.compile(r"C:[\\/]Users[\\/]", re.IGNORECASE),
    re.compile(r"OneDrive[\\/]Documentos", re.IGNORECASE),
]


def main() -> None:
    failures: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            failures.append(f"Dato DICOM no permitido: {relative}")
        if path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size < 20_000_000:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                failures.append(f"No se pudo leer {relative}: {exc}")
                continue
            for pattern in PERSONAL_PATHS:
                if pattern.search(content):
                    failures.append(f"Ruta personal detectada en {relative}")
    if failures:
        raise SystemExit("\n".join(failures))
    print("OK: no se detectaron DICOM ni rutas personales en archivos de texto.")


if __name__ == "__main__":
    main()

