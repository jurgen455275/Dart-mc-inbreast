#!/usr/bin/env python3
"""Extrae 23 variables comparables para DART-MC y umbrales de control."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import ctypes
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pydicom

import evaluar_preprocesamiento_inbreast_h008 as h008
import validar_optimizado as base


ROOT = Path(__file__).resolve().parents[1]
MODE_NAMES = {
    0: "dart_mc",
    1: "fixed_d_005", 2: "fixed_d_010", 3: "fixed_d_015",
    4: "fixed_d_020", 5: "fixed_d_025", 6: "fixed_d_030",
    7: "fixed_d_040", 8: "fixed_d_050", 9: "fixed_d_060",
    10: "otsu_masked",
    11: "quantile_q9900", 12: "quantile_q9950",
    13: "quantile_q9990", 14: "quantile_q9995",
    15: "quantile_q9999",
    16: "mean_k8_cap095", 17: "mean_k12_cap095",
    18: "mean_k16_cap095", 19: "mean_k24_cap095",
    20: "k20_adaptive_cap_q9999", 21: "empirical_tail_area",
    22: "empirical_q999_cap095", 23: "k20_without_cap",
    24: "niblack_local_k10", 25: "sauvola_local_k05",
    26: "kapur_entropy", 27: "kittler_illingworth",
    28: "ridler_calvard",
}
FEATURE_NAMES = [
    "adaptive_threshold", "raw_density_log", "accepted_density_log",
    "score_max", "score_mean", "dog_max", "dog_mean",
    "contrast_max", "contrast_mean", "compactness_max",
    "compactness_mean", "cluster_support", "cluster_count_log",
    "accept_fraction", "score_gap", "x_mean", "y_mean", "x_std",
    "y_std", "border_mean", "evidence_max", "area_max_log",
    "area_mean_log",
]
WORKER_LIBRARY = None
WORKER_FUNCTION = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dll", type=Path,
        default=ROOT / "bin" / "windows"
        / "deform_inbreast_h010_threshold_features.dll",
    )
    parser.add_argument(
        "--reference", type=Path,
        default=ROOT / "results" / "inbreast_v8_rawnorm" / "development"
        / "rawnorm_comparison_by_image.csv",
    )
    parser.add_argument(
        "--h009-features", type=Path,
        default=ROOT / "results" / "inbreast_v8_h009" / "features"
        / "rawnorm_features_23.csv",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "results" / "inbreast_v8_h010" / "features",
    )
    parser.add_argument(
        "--dataset-root", type=Path,
        help=(
            "Raiz local de INbreast. Puede ser la carpeta 'INbreast Release 1.0' "
            "o directamente su subcarpeta 'AllDICOMs'. Reemplaza las rutas "
            "absolutas conservadas en el registro de referencia."
        ),
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def init_worker(dll_path: str) -> None:
    global WORKER_LIBRARY, WORKER_FUNCTION
    WORKER_LIBRARY = ctypes.CDLL(dll_path)
    WORKER_FUNCTION = WORKER_LIBRARY.extract_inbreast_h010_threshold_features
    WORKER_FUNCTION.argtypes = [
        ctypes.POINTER(ctypes.c_float), ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint64,
        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_float,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_double), ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_double),
    ]
    WORKER_FUNCTION.restype = ctypes.c_int


def call_h010(image: np.ndarray, mask: np.ndarray, spacing: float):
    image = np.ascontiguousarray(image, dtype=np.float32)
    mask = np.ascontiguousarray(mask, dtype=np.uint8)
    mode_count = len(MODE_NAMES)
    thresholds = np.empty(mode_count, dtype=np.float64)
    raw_counts = np.empty(mode_count, dtype=np.uint64)
    accepted_counts = np.empty(mode_count, dtype=np.uint64)
    features = np.empty((mode_count, len(FEATURE_NAMES)), dtype=np.float64)
    quality = ctypes.c_int()
    elapsed = ctypes.c_double()
    rc = WORKER_FUNCTION(
        image.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), image.size,
        mask.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), mask.size,
        image.shape[0], image.shape[1], float(spacing),
        thresholds.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        raw_counts.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
        accepted_counts.ctypes.data_as(ctypes.POINTER(ctypes.c_uint64)),
        features.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), features.size,
        ctypes.byref(quality), ctypes.byref(elapsed),
    )
    if rc != 0:
        raise RuntimeError(f"H010 devolvio {rc}; QC={quality.value}")
    return thresholds, raw_counts, accepted_counts, features, int(quality.value), float(elapsed.value)


def as_bool(value) -> bool:
    return str(value).strip().lower() == "true"


def evaluate_one(payload: dict) -> list[dict]:
    path = Path(payload["dicom_path"])
    legacy, spacing, _, _, _ = base.inbreast_base.load_inbreast_dicom(str(path))
    legacy = np.ascontiguousarray(legacy, dtype=np.float32)
    mask = np.ascontiguousarray(
        base.inbreast_base.breast_mask_and_pectoral_removal(legacy),
        dtype=np.uint8,
    )
    raw = pydicom.dcmread(path).pixel_array.astype(np.float32)
    normalized, low, high = h008.robust_normalize_raw(raw, mask)
    thresholds, raw_counts, accepted_counts, features, quality, elapsed = call_h010(
        normalized, mask, float(spacing)
    )
    common = {
        "image_id": str(payload["image_id"]),
        "subject_surrogate": str(payload["subject_surrogate"]),
        "outer_fold": int(payload["outer_fold"]),
        "gt_positive": as_bool(payload["gt_positive"]),
        "acr": str(payload["acr"]),
        "view": str(payload["view"]),
        "laterality": str(payload["laterality"]),
        "rows": int(legacy.shape[0]),
        "cols": int(legacy.shape[1]),
        "spacing_mm": float(spacing),
        "raw_percentile_0_5": float(low),
        "raw_percentile_99_5": float(high),
        "quality_code": quality,
        "time_ms_all_methods": elapsed,
    }
    rows = []
    for mode, method in MODE_NAMES.items():
        feature_values = {
            name: float(features[mode, index])
            for index, name in enumerate(FEATURE_NAMES)
        }
        rows.append({
            **common,
            "mode": mode,
            "method": method,
            "raw_candidates": int(raw_counts[mode]),
            "accepted_candidates": int(accepted_counts[mode]),
            **feature_values,
        })
        if abs(feature_values["adaptive_threshold"] - thresholds[mode]) > 1e-12:
            raise RuntimeError(f"Umbral inconsistente en {payload['image_id']} modo {mode}")
    return rows


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    reference = pd.read_csv(
        args.reference, dtype={"image_id": str, "subject_surrogate": str}
    )
    if args.dataset_root:
        dicom_dir = args.dataset_root.resolve()
        if dicom_dir.name.lower() != "alldicoms":
            dicom_dir = dicom_dir / "AllDICOMs"
        reference["dicom_path"] = reference["dicom_path"].map(
            lambda value: str(dicom_dir / Path(str(value)).name)
        )
    elif not reference.empty and not Path(str(reference.iloc[0]["dicom_path"])).is_absolute():
        raise RuntimeError(
            "El registro usa rutas relativas. Indique --dataset-root con la ruta local "
            "de INbreast."
        )
    if args.limit:
        reference = reference.head(args.limit).copy()
    tasks = reference.to_dict("records")
    workers = max(1, min(args.workers, os.cpu_count() or 1))
    output_rows = []
    started = time.time()
    with ProcessPoolExecutor(
        max_workers=workers, initializer=init_worker, initargs=(str(args.dll),)
    ) as pool:
        futures = {pool.submit(evaluate_one, row): row["image_id"] for row in tasks}
        for completed, future in enumerate(as_completed(futures), 1):
            output_rows.extend(future.result())
            if completed == 1 or completed % 10 == 0 or completed == len(futures):
                print(
                    f"PROGRESO H010 {completed}/{len(futures)} "
                    f"({time.time() - started:.1f}s)", flush=True,
                )
    frame = pd.DataFrame(output_rows).sort_values(["image_id", "mode"])
    expected_rows = len(reference) * len(MODE_NAMES)
    if len(frame) != expected_rows or frame.duplicated(["image_id", "mode"]).any():
        raise RuntimeError("Salida H010 incompleta o duplicada")
    if frame["quality_code"].ne(0).any():
        raise RuntimeError("H010 produjo fallos de calidad")

    dart = frame[frame["mode"].eq(0)].copy()
    h009_features = pd.read_csv(args.h009_features, dtype={"image_id": str})
    joined = dart.merge(
        h009_features[["image_id", "raw_candidates", "accepted_candidates", *FEATURE_NAMES]],
        on="image_id", how="left", validate="one_to_one", suffixes=("_h010", "_h009"),
    )
    differences = {}
    for name in FEATURE_NAMES:
        differences[name] = float(np.max(np.abs(
            joined[f"{name}_h010"] - joined[f"{name}_h009"]
        )))
    reproduction_tolerance = 1e-7
    audit = {
        "experiment_id": "INB-H010-THRESHOLD-COMP01",
        "images": int(len(reference)),
        "methods": len(MODE_NAMES),
        "rows": int(len(frame)),
        "quality_failures": int(frame["quality_code"].ne(0).sum()),
        "ground_truth_passed_to_detector": False,
        "dart_threshold_formula": "T=min(0.95,mean_M(D)+20*std_M(D)); D>T",
        "dart_raw_candidate_mismatches_vs_h009": int((
            joined["raw_candidates_h010"] != joined["raw_candidates_h009"]
        ).sum()),
        "dart_accepted_candidate_mismatches_vs_h009": int((
            joined["accepted_candidates_h010"] != joined["accepted_candidates_h009"]
        ).sum()),
        "dart_feature_max_abs_difference_vs_h009": differences,
        "dart_reproduction_tolerance": reproduction_tolerance,
        "elapsed_wall_seconds": time.time() - started,
    }
    if audit["dart_raw_candidate_mismatches_vs_h009"] \
            or audit["dart_accepted_candidate_mismatches_vs_h009"] \
            or max(differences.values()) > reproduction_tolerance:
        raise RuntimeError(f"El control DART no reproduce H009: {audit}")

    feature_path = args.output / "h010_threshold_features_long.csv"
    audit_path = args.output / "h010_feature_audit.json"
    frame.to_csv(feature_path, index=False)
    audit.update({
        "features_sha256": sha256(feature_path),
        "reference_sha256": sha256(args.reference),
        "h009_features_sha256": sha256(args.h009_features),
        "dll_sha256": sha256(args.dll),
    })
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
