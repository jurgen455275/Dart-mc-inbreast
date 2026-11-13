"""Validacion reproducible de los detectores C++ sobre el dataset MIAS.

Evalua presencia de microcalcificaciones en las 322 imagenes y localizacion
en las imagenes CALC que incluyen coordenadas. No reajusta parametros con MIAS.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import pathlib
import time
from collections import defaultdict

import cv2
import numpy as np
import pandas as pd


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODES = (
    "cpp_original_k20",
    "cpp_actual_k70",
    "mejorado_balanced",
    "mejorado_sensitive",
    "mejorado_adaptive_original",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida los C++ sobre MIAS")
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument(
        "--dll-original",
        type=pathlib.Path,
        default=REPO_ROOT / "bin" / "windows" / "deform_inbreast.dll",
    )
    parser.add_argument(
        "--dll-mejorado",
        type=pathlib.Path,
        default=REPO_ROOT / "bin" / "windows" / "deform_inbreast_mejorado.dll",
    )
    parser.add_argument("--output", type=pathlib.Path, default=REPO_ROOT / "results")
    parser.add_argument("--spacing-mm", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=0, help="0 procesa todo el dataset")
    return parser.parse_args()


def load_original(path: pathlib.Path):
    lib = ctypes.CDLL(str(path))
    fn = lib.analyze_inbreast_cpp
    fn.argtypes = [
        ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_float, ctypes.c_double, ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_double),
    ]
    fn.restype = ctypes.c_int
    return lib, fn


def load_improved(path: pathlib.Path):
    lib = ctypes.CDLL(str(path))
    fn = lib.analyze_inbreast_mejorado_v2
    fn.argtypes = [
        ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_float, ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_double),
    ]
    fn.restype = ctypes.c_int
    return lib, fn


def read_image(path: pathlib.Path) -> np.ndarray:
    raw = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if raw is None:
        raise FileNotFoundError(path)
    return np.ascontiguousarray(raw.astype(np.float32) / 255.0)


def breast_mask(image: np.ndarray) -> np.ndarray:
    image_u8 = np.clip(image * 255.0, 0, 255).astype(np.uint8)
    _, threshold = cv2.threshold(
        image_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    count, labels, stats, _ = cv2.connectedComponentsWithStats(threshold, 8)
    if count <= 1:
        return np.ascontiguousarray(np.ones_like(image_u8, dtype=np.uint8))
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = (labels == largest).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    return np.ascontiguousarray(mask)


def build_metadata(info_path: pathlib.Path):
    frame = pd.read_csv(info_path)
    grouped = {}
    for refnum, group in frame.groupby("REFNUM", sort=True):
        calc = group[group["CLASS"].eq("CALC")]
        grouped[str(refnum)] = {
            "bg": str(group.iloc[0]["BG"]),
            "classes": sorted(set(str(value) for value in group["CLASS"])),
            "gt_positive": not calc.empty,
            "calc_rows": calc.to_dict("records"),
            "severity": "/".join(sorted(set(str(value) for value in calc["SEVERITY"].dropna()))),
        }
    return frame, grouped


def make_gt_mask(shape: tuple[int, int], calc_rows: list[dict]) -> tuple[np.ndarray | None, int]:
    rows, cols = shape
    mask = np.zeros(shape, dtype=np.uint8)
    annotated = 0
    for lesion in calc_rows:
        values = (lesion.get("X"), lesion.get("Y"), lesion.get("RADIUS"))
        if any(pd.isna(value) for value in values):
            continue
        x = int(round(float(values[0])))
        # MIAS expresa Y desde el borde inferior; las matrices se indexan desde arriba.
        y = rows - 1 - int(round(float(values[1])))
        radius = max(1, int(round(float(values[2]))))
        if 0 <= x < cols and 0 <= y < rows:
            cv2.circle(mask, (x, y), radius, 1, thickness=-1)
            annotated += 1
    if not np.any(mask):
        return None, annotated
    return np.ascontiguousarray(mask), annotated


def call_original(fn, image, mask, gt_mask, spacing, k):
    mean = ctypes.c_double()
    stddev = ctypes.c_double()
    threshold = ctypes.c_double()
    candidates = ctypes.c_uint64()
    tp = ctypes.c_uint64()
    fp = ctypes.c_uint64()
    detected = ctypes.c_int()
    elapsed = ctypes.c_double()
    gt_ptr = (
        gt_mask.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
        if gt_mask is not None else None
    )
    rc = fn(
        image.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
        mask.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), gt_ptr,
        image.shape[0], image.shape[1], spacing, k,
        ctypes.byref(mean), ctypes.byref(stddev), ctypes.byref(threshold),
        ctypes.byref(candidates), ctypes.byref(tp), ctypes.byref(fp),
        ctypes.byref(detected), ctypes.byref(elapsed),
    )
    if rc != 0:
        raise RuntimeError(f"El C++ original devolvio {rc}")
    return {
        "threshold": threshold.value, "mean": mean.value, "std": stddev.value,
        "candidates": int(candidates.value), "candidate_tp": int(tp.value),
        "candidate_fp": int(fp.value), "localized_hit": bool(detected.value),
        "time_ms": elapsed.value,
    }


def call_improved(fn, image, mask, gt_mask, spacing):
    thresholds = (ctypes.c_double * 3)()
    candidates = (ctypes.c_uint64 * 3)()
    tp = (ctypes.c_uint64 * 3)()
    fp = (ctypes.c_uint64 * 3)()
    detected = (ctypes.c_int * 3)()
    elapsed = ctypes.c_double()
    gt_ptr = (
        gt_mask.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
        if gt_mask is not None else None
    )
    rc = fn(
        image.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
        mask.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)), gt_ptr,
        image.shape[0], image.shape[1], spacing, thresholds, candidates,
        tp, fp, detected, ctypes.byref(elapsed),
    )
    if rc != 0:
        raise RuntimeError(f"El C++ mejorado devolvio {rc}")
    result = {}
    for index, mode in enumerate((
        "mejorado_balanced", "mejorado_sensitive", "mejorado_adaptive_original"
    )):
        result[mode] = {
            "threshold": thresholds[index], "mean": "", "std": "",
            "candidates": int(candidates[index]), "candidate_tp": int(tp[index]),
            "candidate_fp": int(fp[index]), "localized_hit": bool(detected[index]),
            "time_ms": elapsed.value,
        }
    return result


def classification(gt_positive: bool, predicted: bool) -> str:
    if gt_positive:
        return "TP" if predicted else "FN"
    return "FP" if predicted else "TN"


def safe_div(num, den):
    return num / den if den else 0.0


def summarize(rows: list[dict], metadata_frame: pd.DataFrame, image_count: int, spacing: float):
    summary = {
        "dataset": {
            "annotation_rows": int(len(metadata_frame)),
            "unique_images_in_csv": int(metadata_frame["REFNUM"].nunique()),
            "analyzed_images": image_count,
            "calc_annotation_rows": int(metadata_frame["CLASS"].eq("CALC").sum()),
            "calc_positive_images": int(metadata_frame.loc[metadata_frame["CLASS"].eq("CALC"), "REFNUM"].nunique()),
            "calc_images_with_coordinates": int(sum(
                1 for ref in metadata_frame.loc[metadata_frame["CLASS"].eq("CALC"), "REFNUM"].unique()
                if metadata_frame[(metadata_frame["REFNUM"].eq(ref)) & metadata_frame["CLASS"].eq("CALC")][["X", "Y", "RADIUS"]].notna().all(axis=1).any()
            )),
            "spacing_mm_assumed": spacing,
        },
        "algorithms": {},
    }
    for mode in MODES:
        group = [row for row in rows if row["algorithm"] == mode]
        counts = {label: sum(row["presence_result"] == label for row in group) for label in ("TP", "TN", "FP", "FN")}
        annotated_positive = [row for row in group if row["gt_positive"] and row["gt_localizable"]]
        localized = sum(bool(row["localized_hit"]) for row in annotated_positive)
        candidate_tp = sum(int(row["candidate_tp"]) for row in group)
        candidate_fp = sum(int(row["candidate_fp"]) for row in group)
        summary["algorithms"][mode] = {
            **{key.lower(): int(value) for key, value in counts.items()},
            "sensitivity": safe_div(counts["TP"], counts["TP"] + counts["FN"]),
            "specificity": safe_div(counts["TN"], counts["TN"] + counts["FP"]),
            "precision_presence": safe_div(counts["TP"], counts["TP"] + counts["FP"]),
            "f1_presence": safe_div(2 * counts["TP"], 2 * counts["TP"] + counts["FP"] + counts["FN"]),
            "accuracy": safe_div(counts["TP"] + counts["TN"], len(group)),
            "balanced_accuracy": 0.5 * (
                safe_div(counts["TP"], counts["TP"] + counts["FN"])
                + safe_div(counts["TN"], counts["TN"] + counts["FP"])
            ),
            "localized_images": localized,
            "localizable_positive_images": len(annotated_positive),
            "localization_rate": safe_div(localized, len(annotated_positive)),
            "total_candidates": sum(int(row["candidates"]) for row in group),
            "candidate_tp": candidate_tp,
            "candidate_fp": candidate_fp,
            "candidate_precision": safe_div(candidate_tp, candidate_tp + candidate_fp),
            "false_candidates_per_image": safe_div(candidate_fp, len(group)),
            "mean_time_ms": safe_div(sum(float(row["time_ms"]) for row in group), len(group)),
        }
    return summary


def summarize_by_tissue(rows: list[dict]) -> list[dict]:
    output = []
    for mode in MODES:
        mode_rows = [row for row in rows if row["algorithm"] == mode]
        for tissue in ("F", "G", "D"):
            group = [row for row in mode_rows if row["background_tissue"] == tissue]
            counts = {
                label: sum(row["presence_result"] == label for row in group)
                for label in ("TP", "TN", "FP", "FN")
            }
            output.append({
                "algorithm": mode,
                "background_tissue": tissue,
                "images": len(group),
                "positive_images": counts["TP"] + counts["FN"],
                "tp": counts["TP"], "tn": counts["TN"],
                "fp": counts["FP"], "fn": counts["FN"],
                "sensitivity": safe_div(counts["TP"], counts["TP"] + counts["FN"]),
                "specificity": safe_div(counts["TN"], counts["TN"] + counts["FP"]),
                "balanced_accuracy": 0.5 * (
                    safe_div(counts["TP"], counts["TP"] + counts["FN"])
                    + safe_div(counts["TN"], counts["TN"] + counts["FP"])
                ),
            })
    return output


def explore_candidate_cutoffs(rows: list[dict]) -> list[dict]:
    """Barrido diagnostico; no se usa para reemplazar las reglas primarias."""
    output = []
    for mode in MODES:
        group = [row for row in rows if row["algorithm"] == mode]
        max_candidates = max(int(row["candidates"]) for row in group)
        for cutoff in range(1, max_candidates + 2):
            tp = tn = fp = fn = 0
            for row in group:
                predicted = int(row["candidates"]) >= cutoff
                result = classification(bool(row["gt_positive"]), predicted)
                if result == "TP": tp += 1
                elif result == "TN": tn += 1
                elif result == "FP": fp += 1
                else: fn += 1
            sensitivity = safe_div(tp, tp + fn)
            specificity = safe_div(tn, tn + fp)
            output.append({
                "algorithm": mode, "min_candidates": cutoff,
                "tp": tp, "tn": tn, "fp": fp, "fn": fn,
                "sensitivity": sensitivity, "specificity": specificity,
                "balanced_accuracy": 0.5 * (sensitivity + specificity),
                "f1_presence": safe_div(2 * tp, 2 * tp + fp + fn),
            })
    return output


def write_csv(path: pathlib.Path, rows: list[dict], fieldnames=None):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        columns = list(fieldnames or (rows[0].keys() if rows else []))
        if not columns:
            return
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    image_dir = args.dataset / "MIAS"
    info_path = args.dataset / "mias_info.csv"
    metadata_frame, metadata = build_metadata(info_path)
    images = sorted(image_dir.glob("mdb*.png"))
    if args.limit:
        images = images[: args.limit]
    _, original_fn = load_original(args.dll_original)
    _, improved_fn = load_improved(args.dll_mejorado)
    rows = []
    started = time.time()
    for index, image_path in enumerate(images, 1):
        image_id = image_path.stem
        meta = metadata[image_id]
        image = read_image(image_path)
        mask = breast_mask(image)
        gt_mask, annotated_lesions = make_gt_mask(image.shape, meta["calc_rows"])
        results = {
            "cpp_original_k20": call_original(original_fn, image, mask, gt_mask, args.spacing_mm, 20.0),
            "cpp_actual_k70": call_original(original_fn, image, mask, gt_mask, args.spacing_mm, 70.0),
            **call_improved(improved_fn, image, mask, gt_mask, args.spacing_mm),
        }
        for mode, result in results.items():
            min_candidates = 3 if mode == "mejorado_balanced" else 1
            predicted = result["candidates"] >= min_candidates
            rows.append({
                "image_id": image_id,
                "background_tissue": meta["bg"],
                "classes": "/".join(meta["classes"]),
                "severity_calc": meta["severity"],
                "gt_positive": meta["gt_positive"],
                "gt_localizable": gt_mask is not None,
                "gt_annotated_lesions": annotated_lesions,
                "algorithm": mode,
                "min_candidates_for_positive": min_candidates,
                **result,
                "predicted_positive": predicted,
                "presence_result": classification(meta["gt_positive"], predicted),
                "presence_correct": predicted == meta["gt_positive"],
            })
        if index == 1 or index % 20 == 0 or index == len(images):
            print(f"PROGRESO {index}/{len(images)} ({time.time() - started:.1f}s)", flush=True)

    per_image_path = args.output / "mias_validacion_por_imagen.csv"
    summary_path = args.output / "mias_resumen.json"
    summary_csv_path = args.output / "mias_resumen_algoritmos.csv"
    positive_path = args.output / "mias_resultados_calc_positivas.csv"
    tissue_path = args.output / "mias_resumen_por_tejido.csv"
    cutoff_path = args.output / "mias_exploracion_min_candidatos.csv"
    write_csv(per_image_path, rows)
    write_csv(
        positive_path,
        [row for row in rows if row["gt_positive"]],
        fieldnames=rows[0].keys(),
    )
    summary = summarize(rows, metadata_frame, len(images), args.spacing_mm)
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    summary_rows = []
    for mode, values in summary["algorithms"].items():
        summary_rows.append({"algorithm": mode, **values})
    write_csv(summary_csv_path, summary_rows)
    write_csv(tissue_path, summarize_by_tissue(rows))
    write_csv(cutoff_path, explore_candidate_cutoffs(rows))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
