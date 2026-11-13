#!/usr/bin/env python3
"""Comparacion H010 de umbrales con validacion anidada agrupada identica."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from entrenar_h009_rawnorm_anidado import (
    as_bool, choose_threshold, fit_logistic, fit_predict, fit_standardizer,
    metrics, paired_exact, select_inside_outer,
)


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--features", type=Path,
        default=ROOT / "results" / "inbreast_v8_h010" / "features"
        / "h010_threshold_features_long.csv",
    )
    parser.add_argument(
        "--splits", type=Path,
        default=ROOT / "experiments" / "inbreast_v8" / "splits_v1"
        / "nested_folds.csv",
    )
    parser.add_argument(
        "--config", type=Path,
        default=ROOT / "experiments" / "inbreast_v8"
        / "INB-H010-THRESHOLD-COMP01" / "config.json",
    )
    parser.add_argument(
        "--h009", type=Path,
        default=ROOT / "results" / "inbreast_v8_h009" / "nested_evaluation"
        / "h009_outer_predictions.csv",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "results" / "inbreast_v8_h010" / "nested_evaluation",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bootstrap_difference(
    frame: pd.DataFrame, a: str, b: str, repetitions: int, seed: int,
) -> dict:
    groups = {
        str(group): rows.index.to_numpy(dtype=int)
        for group, rows in frame.groupby("subject_surrogate", sort=True)
    }
    keys = np.array(sorted(groups))
    rng = np.random.default_rng(seed)
    names = ["sensitivity", "specificity", "balanced_accuracy", "f1", "mcc"]
    values = {name: [] for name in names}
    observed_a = metrics(frame["gt_positive"], frame[a])
    observed_b = metrics(frame["gt_positive"], frame[b])
    for _ in range(repetitions):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        indices = np.concatenate([groups[key] for key in sampled])
        bag = frame.loc[indices]
        result_a = metrics(bag["gt_positive"], bag[a])
        result_b = metrics(bag["gt_positive"], bag[b])
        for name in names:
            value = result_a[name] - result_b[name]
            if np.isfinite(value):
                values[name].append(float(value))
    return {
        name: {
            "observed_difference": float(observed_a[name] - observed_b[name]),
            "subject_surrogate_cluster_bootstrap_ci95": [
                float(np.quantile(values[name], 0.025)),
                float(np.quantile(values[name], 0.975)),
            ],
        }
        for name in names
    }


def nested_predictions(
    method_frame: pd.DataFrame, splits: pd.DataFrame, feature_sets: dict,
    regularization_grid: list[float], outer_folds: int,
) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    outer_rows = []
    selected_records = []
    selection_records = []
    for outer_fold in range(outer_folds):
        fold_split = splits[splits["outer_fold"].eq(outer_fold)]
        dev_split = fold_split[fold_split["role"].eq("internal_development")]
        ext_split = fold_split[fold_split["role"].eq("external_validation")]
        if set(dev_split["subject_surrogate"]) & set(ext_split["subject_surrogate"]):
            raise RuntimeError(f"Fuga de grupo en fold externo {outer_fold}")
        development = method_frame.merge(
            dev_split[["image_id", "inner_fold"]], on="image_id",
            how="inner", validate="one_to_one",
        )
        external = method_frame[
            method_frame["image_id"].isin(ext_split["image_id"])
        ].copy()
        selected, candidates = select_inside_outer(
            development, feature_sets, regularization_grid,
        )
        probabilities, _, _, _ = fit_predict(
            development, external, selected["features"], selected["regularization"],
        )
        external["probability"] = probabilities
        external["prediction"] = probabilities >= selected["decision_threshold"]
        external["evaluated_outer_fold"] = outer_fold
        outer_rows.append(external)
        for candidate in candidates:
            selection_records.append({
                "outer_fold": outer_fold,
                "family": candidate["family"],
                "regularization": candidate["regularization"],
                "decision_threshold": candidate["decision_threshold"],
                **candidate["inner_metrics"],
                "selected": bool(candidate is selected),
            })
        selected_records.append({
            "outer_fold": outer_fold,
            "family": selected["family"],
            "regularization": selected["regularization"],
            "decision_threshold": selected["decision_threshold"],
            "inner_metrics": selected["inner_metrics"],
        })
    predictions = pd.concat(outer_rows, ignore_index=True)
    if len(predictions) != len(method_frame) or predictions["image_id"].duplicated().any():
        raise RuntimeError("Predicciones externas incompletas")
    return predictions.sort_values("image_id"), selected_records, selection_records


def freeze_dart_model(
    frame: pd.DataFrame, splits: pd.DataFrame, feature_sets: dict,
    regularization_grid: list[float], outer_folds: int,
) -> dict:
    assignments = splits[splits["role"].eq("external_validation")][
        ["image_id", "outer_fold"]
    ].copy().rename(columns={"outer_fold": "freeze_outer_fold"})
    if len(assignments) != len(frame) or assignments["image_id"].duplicated().any():
        raise RuntimeError("Asignacion externa no es uno-a-uno")
    data = frame.merge(assignments, on="image_id", validate="one_to_one")
    candidates = []
    for family, features in feature_sets.items():
        for regularization in regularization_grid:
            oof = np.full(len(data), np.nan)
            for outer_fold in range(outer_folds):
                validation_mask = data["freeze_outer_fold"].eq(outer_fold).to_numpy()
                probabilities, _, _, _ = fit_predict(
                    data.loc[~validation_mask], data.loc[validation_mask],
                    list(features), regularization,
                )
                oof[validation_mask] = probabilities
            threshold, result = choose_threshold(data["gt_positive"], oof)
            candidates.append({
                "family": family,
                "features": list(features),
                "regularization": regularization,
                "decision_threshold": threshold,
                "selection_oof_metrics": result,
            })

    def rank(candidate: dict) -> tuple:
        result = candidate["selection_oof_metrics"]
        return (
            result["balanced_accuracy"], result["sensitivity"],
            result["specificity"], -len(candidate["features"]),
            candidate["regularization"],
            -abs(candidate["decision_threshold"] - 0.5),
        )

    selected = max(candidates, key=rank)
    x = data[selected["features"]].to_numpy(dtype=float)
    y = data["gt_positive"].to_numpy(dtype=int)
    mean, scale = fit_standardizer(x)
    coefficients = fit_logistic(
        (x - mean) / scale, y, selected["regularization"],
    )
    return {
        "status": "frozen_for_future_external_validation",
        "performance_note": (
            "The full-data fit is not evaluated on its training data. Reported performance "
            "comes exclusively from the nested out-of-fold experiment."
        ),
        "threshold_formula_invariant": "T=min(0.95,mean_M(D)+20*std_M(D)); D>T",
        **selected,
        "training_images": int(len(data)),
        "feature_mean": mean.tolist(),
        "feature_scale": scale.tolist(),
        "intercept": float(coefficients[0]),
        "coefficients_standardized": coefficients[1:].tolist(),
    }


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    all_features = pd.read_csv(
        args.features, dtype={"image_id": str, "subject_surrogate": str},
    )
    all_features["gt_positive"] = as_bool(all_features["gt_positive"])
    splits = pd.read_csv(args.splits, dtype={"image_id": str, "subject_surrogate": str})
    feature_sets = config["feature_sets"]
    regularization_grid = [float(value) for value in config["regularization_grid"]]
    outer_folds = int(config["validation"]["outer_folds"])
    methods = {int(mode): name for mode, name in config["methods"].items()}
    expected_rows = int(config["images_expected"]) * 29
    if len(all_features) != expected_rows:
        raise RuntimeError(f"Matriz H010 inesperada: {len(all_features)}")

    prediction_frames = []
    method_summaries = []
    model_selection = []
    selected_models = {}
    for mode, label in methods.items():
        method_frame = all_features[all_features["mode"].eq(mode)].copy()
        if len(method_frame) != config["images_expected"]:
            raise RuntimeError(f"Metodo incompleto: {mode}")
        predictions, selected, selection = nested_predictions(
            method_frame, splits, feature_sets, regularization_grid, outer_folds,
        )
        predictions["mode"] = mode
        predictions["method_label"] = label
        prediction_frames.append(predictions)
        result = metrics(predictions["gt_positive"], predictions["prediction"])
        method_summaries.append({"mode": mode, "method": label, **result})
        selected_models[str(mode)] = selected
        for row in selection:
            model_selection.append({"mode": mode, "method": label, **row})
        print(
            f"H010 modo {mode:02d} {label}: BA={result['balanced_accuracy']:.6f} "
            f"Se={result['sensitivity']:.6f} Sp={result['specificity']:.6f}",
            flush=True,
        )

    predictions_long = pd.concat(prediction_frames, ignore_index=True)
    index_columns = [
        "image_id", "subject_surrogate", "gt_positive", "acr", "view", "laterality",
    ]
    wide = predictions_long.pivot(
        index=index_columns, columns="mode", values="prediction",
    ).reset_index()
    wide.columns = [
        f"prediction_mode_{int(value)}" if isinstance(value, (int, np.integer)) else value
        for value in wide.columns
    ]
    h009 = pd.read_csv(args.h009, dtype={"image_id": str})
    h009["h009_prediction"] = as_bool(h009["h009_prediction"])
    audit = wide.merge(
        h009[["image_id", "h009_prediction"]], on="image_id",
        validate="one_to_one",
    )
    dart_mismatches = int((audit["prediction_mode_0"] != audit["h009_prediction"]).sum())
    if dart_mismatches:
        raise RuntimeError(f"DART H010 no reproduce predicciones H009: {dart_mismatches}")

    summaries = pd.DataFrame(method_summaries).sort_values(
        ["balanced_accuracy", "sensitivity", "specificity"], ascending=False,
    )
    dart = summaries[summaries["mode"].eq(0)].iloc[0].to_dict()
    inference = {}
    repetitions = int(config["validation"]["bootstrap_replicates"])
    seed = int(config["validation"]["bootstrap_seed"])
    for offset, (mode, label) in enumerate(methods.items()):
        if mode == 0:
            continue
        a = "prediction_mode_0"
        b = f"prediction_mode_{mode}"
        inference[str(mode)] = {
            "comparator": label,
            "dart_minus_comparator": bootstrap_difference(
                wide, a, b, repetitions, seed + offset,
            ),
            "mcnemar_all_images": paired_exact(
                wide["gt_positive"], wide[a], wide[b],
            ),
        }

    frozen = freeze_dart_model(
        all_features[all_features["mode"].eq(0)].copy(), splits,
        feature_sets, regularization_grid, outer_folds,
    )
    predictions_path = args.output / "h010_outer_predictions_long.csv"
    wide_path = args.output / "h010_outer_predictions_wide.csv"
    metrics_path = args.output / "h010_method_metrics.csv"
    selection_path = args.output / "h010_inner_model_selection.csv"
    selected_path = args.output / "h010_selected_models.json"
    frozen_path = args.output / "h010_frozen_dart_model.json"
    summary_path = args.output / "h010_summary.json"
    predictions_long.to_csv(predictions_path, index=False)
    wide.to_csv(wide_path, index=False)
    summaries.to_csv(metrics_path, index=False)
    pd.DataFrame(model_selection).to_csv(selection_path, index=False)
    selected_path.write_text(json.dumps(selected_models, indent=2), encoding="utf-8")
    frozen_path.write_text(json.dumps(frozen, indent=2), encoding="utf-8")
    summary = {
        "experiment_id": config["experiment_id"],
        "status": "completed",
        "images": int(config["images_expected"]),
        "positives": int(wide["gt_positive"].sum()),
        "negatives": int((~wide["gt_positive"]).sum()),
        "patient_identity_available": False,
        "patient_level_validation_claimed": False,
        "grouping_field": "subject_surrogate",
        "grouping_limitation": config["grouping"]["limitation"],
        "threshold_formula_invariant": config["dart_threshold_invariant"],
        "dart_reproduction_mismatches_vs_h009": dart_mismatches,
        "method_metrics": method_summaries,
        "dart_metrics": dart,
        "inference": inference,
        "frozen_model": {
            key: frozen[key] for key in (
                "status", "family", "features", "regularization",
                "decision_threshold", "selection_oof_metrics",
            )
        },
        "interpretation": config["interpretation"],
    }
    summary.update({
        "artifacts_sha256": {
            "config": sha256(args.config), "features": sha256(args.features),
            "splits": sha256(args.splits), "h009": sha256(args.h009),
            "predictions_long": sha256(predictions_path), "predictions_wide": sha256(wide_path),
            "metrics": sha256(metrics_path), "selection": sha256(selection_path),
            "selected_models": sha256(selected_path), "frozen_model": sha256(frozen_path),
        }
    })
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({
        "dart_reproduction_mismatches_vs_h009": dart_mismatches,
        "method_metrics_ranked": summaries.to_dict("records"),
        "frozen_model": summary["frozen_model"],
    }, indent=2))


if __name__ == "__main__":
    main()
