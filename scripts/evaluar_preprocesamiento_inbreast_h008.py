#!/usr/bin/env python3
"""H-INB-008: compara preprocesamiento heredado y normalizacion DICOM cruda.

La mascara, el detector C++, el mapa D, la formula adaptativa, D>T, los
postfiltros y el clasificador permanecen congelados. Ground truth se consulta
solo despues de obtener ambas inferencias.
"""

from __future__ import annotations

import argparse
from collections import Counter
import ctypes
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import platform
import time

import numpy as np
import pandas as pd
import pydicom

import auditar_inbreast_v8 as v8
import validar_optimizado as base


ROOT = Path(__file__).resolve().parents[1]
WORKER_FUNCTION = None
WORKER_LIBRARY = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--dll", type=Path,
        default=ROOT / "bin" / "windows" / "deform_inbreast_v8_audit.dll",
    )
    parser.add_argument(
        "--config", type=Path,
        default=ROOT / "experiments" / "inbreast_v8" / "INB-H008-RAWNORM01" / "config.json",
    )
    parser.add_argument(
        "--audit-reference", type=Path,
        default=ROOT / "results" / "inbreast_v8_audit" / "development" / "audit_images.csv",
    )
    parser.add_argument(
        "--splits", type=Path,
        default=ROOT / "experiments" / "inbreast_v8" / "splits_v1" / "nested_folds.csv",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "results" / "inbreast_v8_rawnorm" / "development",
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


def robust_normalize_raw(raw: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float, float]:
    values = raw[(mask > 0) & np.isfinite(raw)]
    if values.size == 0:
        raise RuntimeError("Mascara mamaria sin valores DICOM finitos")
    low, high = np.percentile(values, [0.5, 99.5])
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        low = float(values.min())
        high = float(values.max())
    if high <= low:
        raise RuntimeError("Rango DICOM degenerado dentro de la mascara")
    normalized = np.zeros(raw.shape, dtype=np.float32)
    inside = mask > 0
    normalized[inside] = np.clip(
        (raw[inside].astype(np.float32) - float(low)) / float(high - low),
        0.0, 1.0,
    )
    return np.ascontiguousarray(normalized), float(low), float(high)


def init_worker(dll: str) -> None:
    global WORKER_LIBRARY, WORKER_FUNCTION
    WORKER_LIBRARY, WORKER_FUNCTION = v8.load_function(Path(dll))


def call_metrics_only(function, case: dict) -> dict:
    image = np.ascontiguousarray(case["image"], dtype=np.float32)
    mask = np.ascontiguousarray(case["mask"], dtype=np.uint8)
    gt = case.get("gt")
    gt_array = np.ascontiguousarray(gt, dtype=np.uint8) if gt is not None else None
    fptr = ctypes.POINTER(ctypes.c_float)
    bptr = ctypes.POINTER(ctypes.c_uint8)
    dptr = ctypes.POINTER(ctypes.c_double)
    metrics = np.empty(len(v8.METRIC_NAMES), dtype=np.float64)
    component_count = ctypes.c_uint64()
    quality = ctypes.c_int()
    elapsed = ctypes.c_double()
    null_doubles = [None] * len(v8.DOUBLE_COMPONENT_FIELDS)
    rc = function(
        image.ctypes.data_as(fptr), image.size,
        mask.ctypes.data_as(bptr), mask.size,
        gt_array.ctypes.data_as(bptr) if gt_array is not None else None,
        gt_array.size if gt_array is not None else 0,
        image.shape[0], image.shape[1], float(case["spacing"]),
        0, metrics.ctypes.data_as(dptr), metrics.size,
        ctypes.byref(component_count), *null_doubles,
        None, None, None, None, ctypes.byref(quality), ctypes.byref(elapsed),
    )
    if rc not in (0, 4):
        raise RuntimeError(f"V8 devolvio {rc}; QC={quality.value}")
    result = {name: float(metrics[i]) for i, name in enumerate(v8.METRIC_NAMES)}
    result["component_count"] = int(component_count.value)
    # rc=4 only reports that the deliberately zero component buffer is too
    # small. Image metrics are already complete and this is not a QC failure.
    result["metrics_only_return_code"] = int(rc)
    result["quality_code"] = 0 if rc == 4 else int(quality.value)
    result["time_ms"] = float(elapsed.value)
    return result


def evaluate_one(payload: dict) -> dict:
    image_id = payload["image_id"]
    path = Path(payload["dicom_path"])
    legacy, spacing, laterality, view, _ = base.inbreast_base.load_inbreast_dicom(str(path))
    legacy = np.ascontiguousarray(legacy, dtype=np.float32)
    mask = np.ascontiguousarray(
        base.inbreast_base.breast_mask_and_pectoral_removal(legacy), dtype=np.uint8
    )
    gt = base.inbreast_base.load_gt_mask_inbreast(
        str(Path(payload["xml_path"])), legacy.shape
    )
    gt = np.ascontiguousarray(gt, dtype=np.uint8) if gt is not None else None
    ds = pydicom.dcmread(path)
    raw = ds.pixel_array.astype(np.float32)
    robust, low, high = robust_normalize_raw(raw, mask)
    common = {"mask": mask, "gt": gt, "spacing": float(spacing)}
    legacy_metrics = call_metrics_only(
        WORKER_FUNCTION, {**common, "image": legacy}
    )
    robust_metrics = call_metrics_only(
        WORKER_FUNCTION, {**common, "image": robust}
    )
    row = {
        **payload,
        "laterality_loaded": laterality,
        "view_loaded": view,
        "rows": int(legacy.shape[0]),
        "cols": int(legacy.shape[1]),
        "spacing_mm": float(spacing),
        "raw_percentile_0_5": low,
        "raw_percentile_99_5": high,
    }
    for arm, metrics in (("legacy", legacy_metrics), ("rawnorm", robust_metrics)):
        for name, value in metrics.items():
            row[f"{arm}_{name}"] = value
        predicted = bool(round(metrics["predicted_positive"]))
        row[f"{arm}_predicted_positive"] = predicted
        row[f"{arm}_presence_result"] = v8.confusion_label(
            bool(payload["gt_positive"]), predicted
        )
    return row


def metric_bundle(frame: pd.DataFrame, prefix: str) -> dict:
    actual = frame["gt_positive"].astype(bool)
    predicted = frame[f"{prefix}_predicted_positive"].astype(bool)
    tp = int((actual & predicted).sum())
    tn = int((~actual & ~predicted).sum())
    fp = int((~actual & predicted).sum())
    fn = int((actual & ~predicted).sum())
    sensitivity = tp / (tp + fn) if tp + fn else float("nan")
    specificity = tn / (tn + fp) if tn + fp else float("nan")
    return {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": (sensitivity + specificity) / 2,
    }


def mechanism_bundle(frame: pd.DataFrame, prefix: str) -> dict:
    positives = frame[frame["gt_positive"].astype(bool)]
    localizable = positives[positives["gt_localizable"].astype(bool)]
    negatives = frame[~frame["gt_positive"].astype(bool)]
    accepted = negatives[f"{prefix}_candidates_accepted"].to_numpy(dtype=float)
    return {
        "localizable_positives": int(len(localizable)),
        "localizable_with_gt_signal": int(
            localizable[f"{prefix}_gt_pixels_above_threshold"].gt(0).sum()
        ),
        "localizable_with_gt_accepted_component": int(
            localizable[f"{prefix}_gt_accepted_components"].gt(0).sum()
        ),
        "negative_images": int(len(negatives)),
        "negative_accepted_candidates_total": int(np.rint(accepted.sum())),
        "negative_accepted_candidates_mean": float(accepted.mean()),
        "negative_accepted_candidates_p95": float(np.percentile(accepted, 95)),
        "negative_accepted_candidates_max": int(np.rint(accepted.max())),
    }


def sampled_metric_difference(sample: pd.DataFrame, name: str) -> float:
    if name in {"sensitivity", "specificity", "balanced_accuracy"}:
        return metric_bundle(sample, "rawnorm")[name] - metric_bundle(sample, "legacy")[name]
    target = sample[sample["target_map_or_threshold"].astype(bool)]
    negatives = sample[~sample["gt_positive"].astype(bool)]
    if name == "target_gt_signal_rate":
        return (
            target["rawnorm_gt_pixels_above_threshold"].gt(0).mean()
            - target["legacy_gt_pixels_above_threshold"].gt(0).mean()
        )
    if name == "target_gt_accepted_rate":
        return (
            target["rawnorm_gt_accepted_components"].gt(0).mean()
            - target["legacy_gt_accepted_components"].gt(0).mean()
        )
    if name == "negative_accepted_candidates_mean":
        return (
            negatives["rawnorm_candidates_accepted"].mean()
            - negatives["legacy_candidates_accepted"].mean()
        )
    raise KeyError(name)


def grouped_bootstrap(frame: pd.DataFrame, replicates: int, seed: int) -> dict:
    groups = {
        key: group.index.to_numpy(dtype=int)
        for key, group in frame.groupby("subject_surrogate", sort=True)
    }
    keys = np.array(sorted(groups))
    rng = np.random.default_rng(seed)
    names = [
        "sensitivity", "specificity", "balanced_accuracy",
        "target_gt_signal_rate", "target_gt_accepted_rate",
        "negative_accepted_candidates_mean",
    ]
    values = {name: [] for name in names}
    for _ in range(replicates):
        sampled_keys = rng.choice(keys, size=len(keys), replace=True)
        indices = np.concatenate([groups[key] for key in sampled_keys])
        sample = frame.loc[indices].reset_index(drop=True)
        for name in names:
            value = sampled_metric_difference(sample, name)
            if np.isfinite(value):
                values[name].append(float(value))
    output = {}
    for name in names:
        observed = sampled_metric_difference(frame, name)
        ci = np.percentile(values[name], [2.5, 97.5]).tolist()
        output[name] = {
            "rawnorm_minus_legacy": float(observed),
            "cluster_bootstrap_ci95": [float(ci[0]), float(ci[1])],
        }
    return output


def fold_metrics(frame: pd.DataFrame) -> list[dict]:
    output = []
    for fold, group in frame.groupby("outer_fold", sort=True):
        legacy = metric_bundle(group, "legacy")
        rawnorm = metric_bundle(group, "rawnorm")
        target = group[group["target_map_or_threshold"].astype(bool)]
        output.append({
            "outer_fold": int(fold),
            "images": int(len(group)),
            "legacy": legacy,
            "rawnorm": rawnorm,
            "target_new_gt_signal": int((
                target["legacy_gt_pixels_above_threshold"].le(0)
                & target["rawnorm_gt_pixels_above_threshold"].gt(0)
            ).sum()),
        })
    return output


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    reference = pd.read_csv(args.audit_reference, dtype={"image_id": str})
    splits = pd.read_csv(args.splits, dtype={"image_id": str})
    identity = (
        splits[splits["role"].eq("external_validation")]
        .drop_duplicates("image_id")
        .set_index("image_id")
    )
    if set(reference["image_id"]) != set(identity.index):
        raise RuntimeError("Los 327 ID de auditoria y split externo no coinciden")
    if args.limit:
        reference = reference.head(args.limit).copy()
    dicom_paths = {
        path.stem.split("_")[0]: path
        for path in (args.dataset / "AllDICOMs").glob("*.dcm")
    }
    tasks = []
    for _, ref in reference.iterrows():
        image_id = str(ref["image_id"])
        identity_row = identity.loc[image_id]
        tasks.append({
            "image_id": image_id,
            "dicom_path": str(dicom_paths[image_id]),
            "xml_path": str(args.dataset / "AllXML" / f"{image_id}.xml"),
            "legacy_split": str(ref["split"]),
            "gt_positive": bool(ref["gt_positive"]),
            "gt_localizable": bool(ref["gt_localizable"]),
            "gt_category": str(ref["gt_category"]),
            "causal_fn_category": str(ref["causal_fn_category"]),
            "target_map_or_threshold": str(ref["causal_fn_category"]) == "map_or_threshold",
            "subject_surrogate": str(identity_row["subject_surrogate"]),
            "outer_fold": int(identity_row["outer_fold"]),
            "acr": str(ref["acr"]),
            "view": str(ref["view"]),
            "laterality": str(ref["laterality"]),
            "reference_prediction": bool(ref["predicted_positive"]),
            "reference_threshold": float(ref["adaptive_threshold"]),
            "reference_raw_candidates": float(ref["reference_raw_candidates"]),
            "reference_accepted_candidates": float(ref["reference_accepted_candidates"]),
        })

    rows = []
    started = time.time()
    workers = max(1, min(args.workers, os.cpu_count() or 1))
    with ProcessPoolExecutor(
        max_workers=workers, initializer=init_worker, initargs=(str(args.dll),)
    ) as pool:
        futures = {pool.submit(evaluate_one, task): task["image_id"] for task in tasks}
        for completed, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if completed == 1 or completed % 10 == 0 or completed == len(futures):
                print(
                    f"PROGRESO H008 {completed}/{len(futures)} "
                    f"({time.time() - started:.1f}s)", flush=True,
                )

    frame = pd.DataFrame(rows).sort_values("image_id").reset_index(drop=True)
    legacy_reproduction = {
        "prediction_match": bool(
            frame["legacy_predicted_positive"].eq(frame["reference_prediction"]).all()
        ),
        "max_threshold_absolute_error": float(
            np.max(np.abs(frame["legacy_adaptive_threshold"] - frame["reference_threshold"]))
        ),
        "raw_candidate_match": bool(np.allclose(
            frame["legacy_reference_raw_candidates"],
            frame["reference_raw_candidates"], rtol=0, atol=0,
        )),
        "accepted_candidate_match": bool(np.allclose(
            frame["legacy_reference_accepted_candidates"],
            frame["reference_accepted_candidates"], rtol=0, atol=0,
        )),
        "quality_failures": int(
            frame["legacy_quality_code"].ne(0).sum()
            + frame["rawnorm_quality_code"].ne(0).sum()
        ),
    }
    if not all([
        legacy_reproduction["prediction_match"],
        legacy_reproduction["max_threshold_absolute_error"] <= 1e-12,
        legacy_reproduction["raw_candidate_match"],
        legacy_reproduction["accepted_candidate_match"],
        legacy_reproduction["quality_failures"] == 0,
    ]):
        raise RuntimeError(f"La rama heredada no reprodujo la referencia: {legacy_reproduction}")

    frame.to_csv(
        args.output / "rawnorm_comparison_by_image.csv",
        index=False, encoding="utf-8-sig",
    )
    legacy_classification = metric_bundle(frame, "legacy")
    rawnorm_classification = metric_bundle(frame, "rawnorm")
    legacy_mechanism = mechanism_bundle(frame, "legacy")
    rawnorm_mechanism = mechanism_bundle(frame, "rawnorm")
    target = frame[frame["target_map_or_threshold"].astype(bool)]
    negatives = frame[~frame["gt_positive"].astype(bool)]
    target_new_signal = int((
        target["legacy_gt_pixels_above_threshold"].le(0)
        & target["rawnorm_gt_pixels_above_threshold"].gt(0)
    ).sum())
    target_new_accepted = int((
        target["legacy_gt_accepted_components"].le(0)
        & target["rawnorm_gt_accepted_components"].gt(0)
    ).sum())
    folds = fold_metrics(frame)
    folds_with_rescue = sum(row["target_new_gt_signal"] > 0 for row in folds)
    negative_ratio = (
        rawnorm_mechanism["negative_accepted_candidates_total"]
        / max(1, legacy_mechanism["negative_accepted_candidates_total"])
    )
    p95_increase = (
        rawnorm_mechanism["negative_accepted_candidates_p95"]
        - legacy_mechanism["negative_accepted_candidates_p95"]
    )
    gates = config["promotion_gates"]
    generation_checks = {
        "target_new_signal": target_new_signal >= gates["generation_gate"]["minimum_target_images_newly_with_gt_signal"],
        "fold_coverage": folds_with_rescue >= gates["generation_gate"]["minimum_outer_folds_with_target_rescue"],
        "negative_candidate_ratio": negative_ratio <= gates["generation_gate"]["maximum_negative_accepted_candidate_ratio"],
        "negative_candidate_p95": p95_increase <= gates["generation_gate"]["maximum_negative_accepted_p95_increase"],
    }
    classification_checks = {
        "true_positives": rawnorm_classification["tp"] >= gates["frozen_classification_gate"]["minimum_true_positives"],
        "false_positives": rawnorm_classification["fp"] <= gates["frozen_classification_gate"]["maximum_false_positives"],
        "sensitivity": (
            rawnorm_classification["sensitivity"] - legacy_classification["sensitivity"]
            >= gates["frozen_classification_gate"]["minimum_sensitivity_difference"]
        ),
        "specificity": (
            rawnorm_classification["specificity"] - legacy_classification["specificity"]
            >= gates["frozen_classification_gate"]["minimum_specificity_difference"]
        ),
    }
    transition = Counter(
        f"{a}->{b}" for a, b in zip(
            frame["legacy_presence_result"], frame["rawnorm_presence_result"]
        )
    )
    summary = {
        "experiment_id": config["experiment_id"],
        "complete": not bool(args.limit),
        "images": int(len(frame)),
        "subject_surrogate_groups": int(frame["subject_surrogate"].nunique()),
        "legacy_reproduction": legacy_reproduction,
        "classification": {
            "legacy": legacy_classification,
            "rawnorm": rawnorm_classification,
            "transitions": dict(transition),
        },
        "mechanism": {
            "legacy": legacy_mechanism,
            "rawnorm": rawnorm_mechanism,
            "target_images": int(len(target)),
            "target_new_gt_signal": target_new_signal,
            "target_new_gt_accepted_component": target_new_accepted,
            "outer_folds_with_target_signal_rescue": int(folds_with_rescue),
            "negative_accepted_candidate_ratio": float(negative_ratio),
            "negative_accepted_p95_increase": float(p95_increase),
        },
        "outer_folds": folds,
        "paired_uncertainty": grouped_bootstrap(
            frame,
            int(config["validation"]["bootstrap_replicates"]),
            int(config["validation"]["bootstrap_seed"]),
        ),
        "promotion_gates": {
            "generation_checks": generation_checks,
            "generation_passed": all(generation_checks.values()),
            "frozen_classification_checks": classification_checks,
            "frozen_classification_passed": all(classification_checks.values()),
            "final_algorithm_promoted": False,
        },
        "invariants": {
            "formula": config["threshold_formula_invariant"],
            "formula_unchanged": True,
            "strict_comparison_unchanged": True,
            "detector_dll_unchanged": True,
            "classifier_unchanged": True,
            "test_v7_used": False,
            "mias_used": False,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "workers": workers,
        },
        "hashes": {
            "script": sha256(ROOT / "scripts" / "evaluar_preprocesamiento_inbreast_h008.py"),
            "config": sha256(args.config),
            "dll": sha256(args.dll),
            "audit_reference": sha256(args.audit_reference),
            "split": sha256(args.splits),
        },
    }
    (args.output / "rawnorm_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
