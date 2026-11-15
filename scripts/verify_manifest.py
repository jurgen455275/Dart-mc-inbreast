#!/usr/bin/env python3
"""Verifica las huellas SHA-256 del paquete publicable."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST_SHA256.txt"
LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    failures: list[str] = []
    entries = 0
    for line_number, raw in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        match = LINE.fullmatch(raw)
        if not match:
            failures.append(f"Linea {line_number} invalida en el manifiesto.")
            continue
        expected, relative = match.groups()
        path = ROOT / Path(relative)
        entries += 1
        if not path.is_file():
            failures.append(f"Falta el archivo: {relative}")
            continue
        actual = sha256(path)
        if actual != expected:
            failures.append(f"Hash distinto: {relative}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"OK: {entries} hashes SHA-256 verificados.")


if __name__ == "__main__":
    main()
