#!/usr/bin/env python3
"""Auditoria por etapas de INbreast con el umbral adaptativo preservado.

El ground truth se utiliza solo para atribuir errores despues de ejecutar la
inferencia de referencia. No modifica T, D>T, candidatos ni clasificacion.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
from collections import Counter
from pathlib import Path
import time

import numpy as np
import pandas as pd

import validar_optimizado as base


ROOT = Path(__file__).resolve().parents[1]
METRIC_NAMES = [
    "deformation_mean", "deformation_std", "adaptive_threshold",
    "deformation_max", "gt_deformation_max", "gt_deformation_mean",
    "gt_fraction_above_threshold", "analysis_mask_pixels", "gt_pixels",
    "suprathreshold_pixels", "components_prearea", "components_too_small",
    "components_too_large", "candidates_valid_area", "candidates_floor_rejected",
    "candidates_score_rejected", "candidates_accepted", "probability",
    "decision_threshold", "base_predicted", "vetoed", "predicted_positive",
    "component_equivalence", "area_min_px", "area_max_px", "threshold_capped",
    "gt_pixels_above_threshold", "gt_components", "gt_accepted_components",
    "reference_raw_candidates", "reference_accepted_candidates",
    "connectivity", "gt_neighborhood_pixels",
    "gt_pixels_original_above_threshold",
]
STAGE_NAMES = {
    0: "area_too_small",
    1: "area_too_large",
    2: "safety_floor",
    3: "v3_score",
    4: "accepted",
}
DOUBLE_COMPONENT_FIELDS = [
    "x", "y", "area_px", "area_mm2", "perimeter_px",
    "deformation_max", "deformation_mean", "center_mean", "ring_mean",
    "ring_std", "compactness", "local_contrast_z", "dog_max", "dog_z",
    "legacy_score", "contrast_rank", "dog_rank", "compactness_rank",
    "evidence",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--dll", type=Path,
        default=ROOT / "bin" / "windows" / "deform_inbreast_v8_audit.dll",
    )
    parser.add_argument(
        "--reference", type=Path,
        default=ROOT / "results" / "v5_fp_safe" / "predicciones_v5_fp_safe.csv",
    )
    parser.add_argument(
        "--ground-truth", type=Path,
        default=ROOT / "results" / "paper_v7" / "ground_truth_inbreast.csv",
    )
    parser.add_argument(
        "--trace-reference", type=Path,
        default=ROOT / "results" / "v4_full" / "inbreast_por_imagen.csv",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "results" / "inbreast_v8_audit" / "development",
    )
    parser.add_argument(
        "--split", choices=("train", "validation", "development", "test", "all"),
        default="development",
    )
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_bool(value: object) -> bool:
    return str(value).strip().lower() == "true"


def load_function(path: Path):
    library = ctypes.CDLL(str(path))
    function = library.audit_inbreast_v8_components
    dptr = ctypes.POINTER(ctypes.c_double)
    fptr = ctypes.POINTER(ctypes.c_float)
    bptr = ctypes.POINTER(ctypes.c_uint8)
    u32ptr = ctypes.POINTER(ctypes.c_uint32)
    i32ptr = ctypes.POINTER(ctypes.c_int)
    u64ptr = ctypes.POINTER(ctypes.c_uint64)
    function.argtypes = [
        fptr, ctypes.c_uint64, bptr, ctypes.c_uint64,
        bptr, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.c_float, ctypes.c_uint64, dptr, ctypes.c_uint64, u64ptr,
        *([dptr] * len(DOUBLE_COMPONENT_FIELDS)),
        u32ptr, i32ptr, i32ptr, i32ptr, i32ptr, dptr,
    ]
    function.restype = ctypes.c_int
    return library, function


def call_audit(function, case: dict) -> tuple[dict, list[dict]]:
    image = np.ascontiguousarray(case["image"], dtype=np.float32)
    mask = np.ascontiguousarray(case["mask"], dtype=np.uint8)
    gt = case["gt"]
    gt_array = (
        np.ascontiguousarray(gt, dtype=np.uint8) if gt is not None else None
    )
    fptr = ctypes.POINTER(ctypes.c_float)
    bptr = ctypes.POINTER(ctypes.c_uint8)
    dptr = ctypes.POINTER(ctypes.c_double)
    u32ptr = ctypes.POINTER(ctypes.c_uint32)
    i32ptr = ctypes.POINTER(ctypes.c_int)

    metrics = np.empty(len(METRIC_NAMES), dtype=np.float64)
    component_count = ctypes.c_uint64()
    quality = ctypes.c_int()
    elapsed = ctypes.c_double()

    common = [
        image.ctypes.data_as(fptr), image.size,
        mask.ctypes.data_as(bptr), mask.size,
        gt_array.ctypes.data_as(bptr) if gt_array is not None else None,
        gt_array.size if gt_array is not None else 0,
        image.shape[0], image.shape[1], float(case["spacing"]),
    ]
    null_doubles = [None] * len(DOUBLE_COMPONENT_FIELDS)
    rc = function(
        *common, 0, metrics.ctypes.data_as(dptr), metrics.size,
        ctypes.byref(component_count), *null_doubles,
        None, None, None, None, ctypes.byref(quality), ctypes.byref(elapsed),
    )
    if rc not in (0, 4):
        raise RuntimeError(f"Primera llamada V8 devolvio {rc}; QC={quality.value}")

    count = int(component_count.value)
    double_arrays = {
        name: np.empty(count, dtype=np.float64)
        for name in DOUBLE_COMPONENT_FIELDS
    }
    cluster_id = np.empty(count, dtype=np.uint32)
    stage = np.empty(count, dtype=np.int32)
    overlaps_gt = np.empty(count, dtype=np.int32)
    valid_area = np.empty(count, dtype=np.int32)
    rc = function(
        *common, count, metrics.ctypes.data_as(dptr), metrics.size,
        ctypes.byref(component_count),
        *[double_arrays[name].ctypes.data_as(dptr) for name in DOUBLE_COMPONENT_FIELDS],
        cluster_id.ctypes.data_as(u32ptr), stage.ctypes.data_as(i32ptr),
        overlaps_gt.ctypes.data_as(i32ptr), valid_area.ctypes.data_as(i32ptr),
        ctypes.byref(quality), ctypes.byref(elapsed),
    )
    if rc != 0:
        raise RuntimeError(f"Auditoria V8 devolvio {rc}; QC={quality.value}")

    image_metrics = {
        name: float(metrics[index]) for index, name in enumerate(METRIC_NAMES)
    }
    image_metrics["quality_code"] = int(quality.value)
    image_metrics["time_ms"] = float(elapsed.value)
    components = []
    for index in range(count):
        row = {
            name: float(double_arrays[name][index])
            for name in DOUBLE_COMPONENT_FIELDS
        }
        row.update({
            "component_index": index,
            "cluster_id": int(cluster_id[index]),
            "stage_code": int(stage[index]),
            "stage": STAGE_NAMES[int(stage[index])],
            "overlaps_gt": bool(overlaps_gt[index]),
            "valid_area": bool(valid_area[index]),
        })
        components.append(row)
    return image_metrics, components


def confusion_label(actual: bool, predicted: bool) -> str:
    if actual:
        return "TP" if predicted else "FN"
    return "FP" if predicted else "TN"


def gt_category(metadata: pd.Series) -> str:
    if int(metadata.get("calcification_roi_count", 0)) > 0:
        return "CALCIFICATION_ROI"
    if int(metadata.get("cluster_roi_count", 0)) > 0:
        return "CLUSTER_ONLY"
    if as_bool(metadata.get("xml_exists", False)):
        return "NEGATIVE_WITH_NONCALC_XML"
    return "NEGATIVE_WITHOUT_XML"


def selected_inbreast_cases(dataset: Path, image_ids: list[str]):
    """Carga solo los IDs solicitados; evita decodificar las 410 imágenes."""
    paths = {
        path.stem.split("_")[0]: path
        for path in (dataset / "AllDICOMs").glob("*.dcm")
    }
    for image_id in image_ids:
        path = paths.get(str(image_id))
        if path is None:
            continue
        image, spacing, laterality, view, _ = (
            base.inbreast_base.load_inbreast_dicom(str(path))
        )
        image = np.ascontiguousarray(image, dtype=np.float32)
        mask = np.ascontiguousarray(
            base.inbreast_base.breast_mask_and_pectoral_removal(image),
            dtype=np.uint8,
        )
        gt = base.inbreast_base.load_gt_mask_inbreast(
            str(dataset / "AllXML" / f"{image_id}.xml"), image.shape
        )
        gt = np.ascontiguousarray(gt, dtype=np.uint8) if gt is not None else None
        individual = gt is not None
        yield {
            "image_id": str(image_id),
            "image": image,
            "mask": mask,
            "gt": gt,
            "spacing": float(spacing),
            "gt_positive": individual or str(image_id) in {"20587054", "20587080"},
            "gt_localizable": individual,
            "laterality": laterality,
            "view": view,
        }


def causal_category(row: dict) -> str:
    if row["presence_result"] != "FN":
        return "not_fn"
    if not row["gt_localizable"]:
        return "gt_not_localizable"
    if row["gt_pixels_above_threshold"] <= 0:
        return "map_or_threshold"
    if row["gt_components"] <= 0:
        return "component_formation_or_area"
    if row["gt_accepted_components"] <= 0:
        return "postfilter"
    if not row["base_predicted"]:
        return "classifier"
    if row["vetoed"]:
        return "veto"
    return "unresolved"


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    reference = pd.read_csv(args.reference)
    reference = reference.loc[reference["dataset"].eq("inbreast")].copy()
    if args.split == "development":
        reference = reference.loc[reference["split"].isin(["train", "validation"])]
    elif args.split != "all":
        reference = reference.loc[reference["split"].eq(args.split)]
    if args.limit:
        reference = reference.head(args.limit)
    reference["image_key"] = reference["image_id"].astype(str)
    reference = reference.set_index("image_key")

    ground_truth = pd.read_csv(args.ground_truth, dtype={"image_id": str}).fillna("")
    ground_truth = ground_truth.set_index("image_id")
    trace_reference = pd.read_csv(args.trace_reference)
    trace_reference = trace_reference.loc[
        trace_reference["algorithm"].eq("v3_locked_reference")
    ].copy()
    trace_reference["image_key"] = trace_reference["image_id"].astype(str)
    trace_reference = trace_reference.set_index("image_key")

    wanted = set(reference.index)
    cases = list(selected_inbreast_cases(args.dataset, list(reference.index)))
    if len(cases) != len(wanted):
        found = {str(case["image_id"]) for case in cases}
        raise RuntimeError(f"Faltan imagenes: {sorted(wanted - found)}")

    library, function = load_function(args.dll)
    image_rows: list[dict] = []
    component_rows: list[dict] = []
    started = time.time()
    for index, case in enumerate(cases, 1):
        image_id = str(case["image_id"])
        metrics, components = call_audit(function, case)
        expected = reference.loc[image_id]
        metadata = ground_truth.loc[image_id]
        trace = trace_reference.loc[image_id]
        predicted = bool(round(metrics["predicted_positive"]))
        actual = bool(case["gt_positive"])
        row = {
            "image_id": image_id,
            "split": str(expected["split"]),
            "gt_positive": actual,
            "gt_localizable": bool(case["gt_localizable"]),
            "gt_category": gt_category(metadata),
            "acr": str(metadata.get("acr", "")),
            "birads": str(metadata.get("birads", "")),
            "view": str(metadata.get("view", case.get("view", ""))),
            "laterality": str(metadata.get("laterality", case.get("laterality", ""))),
            "rows": int(case["image"].shape[0]),
            "cols": int(case["image"].shape[1]),
            "spacing_mm": float(case["spacing"]),
            **metrics,
            "base_predicted": bool(round(metrics["base_predicted"])),
            "vetoed": bool(round(metrics["vetoed"])),
            "predicted_positive": predicted,
            "presence_result": confusion_label(actual, predicted),
            "reference_prediction": as_bool(expected["v5_prediction"]),
            "reference_prediction_match": predicted == as_bool(expected["v5_prediction"]),
            "trace_threshold_match": abs(
                metrics["adaptive_threshold"] - float(trace["adaptive_threshold"])
            ) <= 1e-12,
            "trace_raw_match": int(round(metrics["reference_raw_candidates"]))
            == int(trace["raw_candidates"]),
            "trace_accepted_match": int(round(metrics["reference_accepted_candidates"]))
            == int(trace["accepted_candidates"]),
        }
        row["causal_fn_category"] = causal_category(row)
        image_rows.append(row)
        for component in components:
            component_rows.append({
                "image_id": image_id,
                "split": row["split"],
                "gt_positive": actual,
                "gt_category": row["gt_category"],
                "presence_result": row["presence_result"],
                "adaptive_threshold": metrics["adaptive_threshold"],
                **component,
            })
        if index == 1 or index % 10 == 0 or index == len(cases):
            print(
                f"PROGRESO {index}/{len(cases)} "
                f"({time.time() - started:.1f}s)", flush=True,
            )

    image_path = args.output / "audit_images.csv"
    component_path = args.output / "audit_components.csv"
    pd.DataFrame(image_rows).to_csv(image_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(component_rows).to_csv(
        component_path, index=False, encoding="utf-8-sig"
    )

    frame = pd.DataFrame(image_rows)
    confusion = Counter(frame["presence_result"])
    fn_categories = Counter(frame.loc[
        frame["presence_result"].eq("FN"), "causal_fn_category"
    ])
    stage_counts = Counter(row["stage"] for row in component_rows)
    summary = {
        "plan_id": "INB-PLAN-2026-11-05",
        "scope": "INbreast only",
        "split": args.split,
        "images": len(image_rows),
        "positives": int(frame["gt_positive"].sum()),
        "negatives": int((~frame["gt_positive"]).sum()),
        "confusion": dict(confusion),
        "fn_causal_categories": dict(fn_categories),
        "component_stage_counts": dict(stage_counts),
        "threshold_invariant": "T=min(0.95,mean_M(D)+20*std_M(D)); D>T",
        "all_component_equivalent": bool(
            frame["component_equivalence"].eq(1.0).all()
        ),
        "all_reference_predictions_match": bool(
            frame["reference_prediction_match"].all()
        ),
        "all_trace_thresholds_match": bool(frame["trace_threshold_match"].all()),
        "all_trace_raw_counts_match": bool(frame["trace_raw_match"].all()),
        "all_trace_accepted_counts_match": bool(
            frame["trace_accepted_match"].all()
        ),
        "quality_failures": int(frame["quality_code"].ne(0).sum()),
        "artifacts": {
            "audit_images": str(image_path),
            "audit_components": str(component_path),
        },
        "hashes": {
            "dll": sha256(args.dll),
            "reference": sha256(args.reference),
            "ground_truth": sha256(args.ground_truth),
            "trace_reference": sha256(args.trace_reference),
            "source": sha256(ROOT / "src" / "deform_inbreast_v8_audit.cpp"),
        },
    }
    summary_path = args.output / "audit_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not all([
        summary["all_component_equivalent"],
        summary["all_reference_predictions_match"],
        summary["all_trace_thresholds_match"],
        summary["all_trace_raw_counts_match"],
        summary["all_trace_accepted_counts_match"],
    ]):
        raise SystemExit("La auditoria no reproduce completamente la referencia.")


if __name__ == "__main__":
    main()

