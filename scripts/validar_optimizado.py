"""Evalua adaptive-optimized y classical-dog-fixed en INBreast o MIAS."""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
from pathlib import Path
import time

import cv2
import numpy as np
import pandas as pd

import validacion_inbreast as inbreast_base
import validar_mias as mias_base


ROOT = Path(__file__).resolve().parents[1]
MODES = ("adaptive_optimized", "classical_dog_fixed")


def parse_args():
    parser = argparse.ArgumentParser(description="Valida la variante optimizada y el comparador clasico")
    parser.add_argument("--dataset-type", choices=("inbreast", "mias"), required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--dll", type=Path,
        default=ROOT / "bin" / "windows" / "deform_inbreast_optimizado.dll",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "optimizado")
    parser.add_argument("--spacing-mm", type=float, default=0.05,
                        help="Solo MIAS; spacing asumido")
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def load_detector(path: Path):
    lib = ctypes.CDLL(str(path))
    fn = lib.analyze_inbreast_optimizado
    fn.argtypes = [
        ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_float, ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_double),
    ]
    fn.restype = ctypes.c_int
    return lib, fn


def call_detector(fn, image, mask, gt_mask, spacing):
    thresholds = (ctypes.c_double * 2)()
    raw = (ctypes.c_uint64 * 2)()
    accepted = (ctypes.c_uint64 * 2)()
    clusters = (ctypes.c_uint64 * 2)()
    max_cluster = (ctypes.c_uint64 * 2)()
    candidate_tp = (ctypes.c_uint64 * 2)()
    candidate_fp = (ctypes.c_uint64 * 2)()
    localized = (ctypes.c_int * 2)()
    predicted = (ctypes.c_int * 2)()
    elapsed = ctypes.c_double()
    gt_ptr = (
        gt_mask.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
        if gt_mask is not None else None
    )
    rc = fn(
        image.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
        mask.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), gt_ptr,
        image.shape[0], image.shape[1], spacing,
        thresholds, raw, accepted, clusters, max_cluster,
        candidate_tp, candidate_fp, localized, predicted,
        ctypes.byref(elapsed),
    )
    if rc != 0:
        raise RuntimeError(f"El C++ optimizado devolvio {rc}")
    return {
        mode: {
            "threshold": float(thresholds[index]),
            "raw_candidates": int(raw[index]),
            "candidates": int(accepted[index]),
            "clusters": int(clusters[index]),
            "max_cluster": int(max_cluster[index]),
            "candidate_tp": int(candidate_tp[index]),
            "candidate_fp": int(candidate_fp[index]),
            "localized_hit": bool(localized[index]),
            "predicted_positive": bool(predicted[index]),
            "time_ms_dual": elapsed.value,
        }
        for index, mode in enumerate(MODES)
    }


def classification(gt_positive, predicted):
    if gt_positive:
        return "TP" if predicted else "FN"
    return "FP" if predicted else "TN"


def safe_div(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def inbreast_cases(dataset: Path, limit: int):
    files = sorted((dataset / "AllDICOMs").glob("*.dcm"))
    if limit:
        files = files[:limit]
    for path in files:
        image_id = path.stem.split("_")[0]
        image, spacing, laterality, view, _ = inbreast_base.load_inbreast_dicom(str(path))
        image = np.ascontiguousarray(image, dtype=np.float32)
        mask = np.ascontiguousarray(
            inbreast_base.breast_mask_and_pectoral_removal(image), dtype=np.uint8)
        gt = inbreast_base.load_gt_mask_inbreast(
            str(dataset / "AllXML" / f"{image_id}.xml"), image.shape)
        gt = np.ascontiguousarray(gt, dtype=np.uint8) if gt is not None else None
        individual = gt is not None
        positive = individual or image_id in {"20587054", "20587080"}
        yield {
            "image_id": image_id, "image": image, "mask": mask, "gt": gt,
            "spacing": float(spacing), "gt_positive": positive,
            "gt_localizable": individual, "laterality": laterality, "view": view,
            "background_tissue": "", "classes": "",
        }


def mias_cases(dataset: Path, spacing: float, limit: int):
    _, metadata = mias_base.build_metadata(dataset / "mias_info.csv")
    files = sorted((dataset / "MIAS").glob("mdb*.png"))
    if limit:
        files = files[:limit]
    for path in files:
        meta = metadata[path.stem]
        image = mias_base.read_image(path)
        mask = mias_base.breast_mask(image)
        gt, _ = mias_base.make_gt_mask(image.shape, meta["calc_rows"])
        yield {
            "image_id": path.stem, "image": image, "mask": mask, "gt": gt,
            "spacing": float(spacing), "gt_positive": bool(meta["gt_positive"]),
            "gt_localizable": gt is not None, "laterality": "", "view": "",
            "background_tissue": meta["bg"], "classes": "/".join(meta["classes"]),
        }


def summarize(rows):
    summary = {}
    for mode in MODES:
        group = [row for row in rows if row["algorithm"] == mode]
        counts = {
            label: sum(row["presence_result"] == label for row in group)
            for label in ("TP", "TN", "FP", "FN")
        }
        localizable = [row for row in group if row["gt_positive"] and row["gt_localizable"]]
        candidate_tp = sum(row["candidate_tp"] for row in group)
        candidate_fp = sum(row["candidate_fp"] for row in group)
        sensitivity = safe_div(counts["TP"], counts["TP"] + counts["FN"])
        specificity = safe_div(counts["TN"], counts["TN"] + counts["FP"])
        summary[mode] = {
            "tp": counts["TP"], "tn": counts["TN"],
            "fp": counts["FP"], "fn": counts["FN"],
            "sensitivity": sensitivity, "specificity": specificity,
            "precision_presence": safe_div(counts["TP"], counts["TP"] + counts["FP"]),
            "f1_presence": safe_div(2 * counts["TP"], 2 * counts["TP"] + counts["FP"] + counts["FN"]),
            "accuracy": safe_div(counts["TP"] + counts["TN"], len(group)),
            "balanced_accuracy": 0.5 * (sensitivity + specificity),
            "localized_images": sum(row["localized_hit"] for row in localizable),
            "localizable_positive_images": len(localizable),
            "localization_rate": safe_div(sum(row["localized_hit"] for row in localizable), len(localizable)),
            "raw_candidates": sum(row["raw_candidates"] for row in group),
            "total_candidates": candidate_tp + candidate_fp,
            "candidate_tp": candidate_tp, "candidate_fp": candidate_fp,
            "candidate_precision": safe_div(candidate_tp, candidate_tp + candidate_fp),
            "false_candidates_per_image": safe_div(candidate_fp, len(group)),
            "mean_time_ms_dual": safe_div(sum(row["time_ms_dual"] for row in group), len(group)),
        }
    return summary


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    _, detector = load_detector(args.dll)
    cases = (
        inbreast_cases(args.dataset, args.limit)
        if args.dataset_type == "inbreast"
        else mias_cases(args.dataset, args.spacing_mm, args.limit)
    )
    rows = []
    started = time.time()
    for index, case in enumerate(cases, 1):
        results = call_detector(
            detector, case["image"], case["mask"], case["gt"], case["spacing"])
        for mode, result in results.items():
            presence = classification(case["gt_positive"], result["predicted_positive"])
            rows.append({
                "image_id": case["image_id"], "dataset": args.dataset_type,
                "laterality": case["laterality"], "view": case["view"],
                "background_tissue": case["background_tissue"], "classes": case["classes"],
                "gt_positive": case["gt_positive"], "gt_localizable": case["gt_localizable"],
                "algorithm": mode, **result, "presence_result": presence,
                "presence_correct": presence in {"TP", "TN"},
            })
        if index == 1 or index % 20 == 0:
            print(f"PROGRESO {args.dataset_type} {index} ({time.time() - started:.1f}s)", flush=True)
    if not rows:
        raise RuntimeError("No se encontraron imagenes")
    prefix = args.dataset_type
    write_csv(args.output / f"{prefix}_por_imagen.csv", rows)
    summary = summarize(rows)
    with (args.output / f"{prefix}_resumen.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
