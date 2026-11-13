#!/usr/bin/env python3
"""Entrenamiento H009 con validacion anidada agrupada y comparacion pareada."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import binomtest


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--features", type=Path,
        default=ROOT / "results" / "inbreast_v8_h009" / "features"
        / "rawnorm_features_23.csv",
    )
    parser.add_argument(
        "--splits", type=Path,
        default=ROOT / "experiments" / "inbreast_v8" / "splits_v1"
        / "nested_folds.csv",
    )
    parser.add_argument(
        "--h008", type=Path,
        default=ROOT / "results" / "inbreast_v8_rawnorm" / "development"
        / "rawnorm_comparison_by_image.csv",
    )
    parser.add_argument(
        "--config", type=Path,
        default=ROOT / "experiments" / "inbreast_v8"
        / "INB-H009-RAWNORM-CLS01" / "config.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "results" / "inbreast_v8_h009" / "nested_evaluation",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    return series.astype(str).str.strip().str.lower().eq("true")


def balanced_weights(labels: np.ndarray) -> np.ndarray:
    labels = np.asarray(labels, dtype=int)
    positives = max(1, int(labels.sum()))
    negatives = max(1, int((1 - labels).sum()))
    return np.where(labels == 1, 0.5 / positives, 0.5 / negatives)


def sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -40.0, 40.0)))


def fit_standardizer(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = x.mean(axis=0)
    scale = x.std(axis=0, ddof=0)
    scale[scale < 1e-12] = 1.0
    return mean, scale


def fit_logistic(x: np.ndarray, y: np.ndarray, regularization: float) -> np.ndarray:
    weights = balanced_weights(y)

    def objective(parameters):
        logits = parameters[0] + x @ parameters[1:]
        probabilities = np.clip(sigmoid(logits), 1e-10, 1.0 - 1e-10)
        loss = -np.sum(weights * (
            y * np.log(probabilities) + (1 - y) * np.log(1 - probabilities)
        ))
        penalty = 0.5 * regularization * np.sum(parameters[1:] ** 2)
        residual = weights * (probabilities - y)
        gradient = np.r_[
            np.sum(residual),
            x.T @ residual + regularization * parameters[1:],
        ]
        return loss + penalty, gradient

    result = minimize(
        objective, np.zeros(x.shape[1] + 1), method="L-BFGS-B", jac=True,
        options={"maxiter": 3000, "ftol": 1e-12},
    )
    if not result.success:
        raise RuntimeError(f"Regresion sin convergencia: {result.message}")
    return result.x


def metrics(actual, predicted) -> dict:
    actual = np.asarray(actual, dtype=bool)
    predicted = np.asarray(predicted, dtype=bool)
    tp = int(np.sum(actual & predicted))
    tn = int(np.sum(~actual & ~predicted))
    fp = int(np.sum(~actual & predicted))
    fn = int(np.sum(actual & ~predicted))
    sensitivity = tp / (tp + fn) if tp + fn else float("nan")
    specificity = tn / (tn + fp) if tn + fp else float("nan")
    precision = tp / (tp + fp) if tp + fp else float("nan")
    npv = tn / (tn + fn) if tn + fn else float("nan")
    denominator = np.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "balanced_accuracy": 0.5 * (sensitivity + specificity),
        "accuracy": (tp + tn) / len(actual) if len(actual) else float("nan"),
        "precision": precision,
        "npv": npv,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        "mcc": (tp * tn - fp * fn) / denominator if denominator else 0.0,
    }


def choose_threshold(actual: np.ndarray, probabilities: np.ndarray) -> tuple[float, dict]:
    unique = np.unique(probabilities)
    candidates = np.unique(np.r_[0.0, unique, 1.0, (unique[:-1] + unique[1:]) / 2])
    best = None
    for threshold in candidates:
        result = metrics(actual, probabilities >= threshold)
        key = (
            result["balanced_accuracy"], result["sensitivity"],
            result["specificity"], -abs(float(threshold) - 0.5),
        )
        if best is None or key > best[0]:
            best = (key, float(threshold), result)
    return best[1], best[2]


def fit_predict(train: pd.DataFrame, validation: pd.DataFrame, features: list[str],
                regularization: float):
    x_train = train[features].to_numpy(dtype=float)
    x_validation = validation[features].to_numpy(dtype=float)
    y_train = train["gt_positive"].to_numpy(dtype=int)
    mean, scale = fit_standardizer(x_train)
    coefficients = fit_logistic((x_train - mean) / scale, y_train, regularization)
    probabilities = sigmoid(
        coefficients[0] + ((x_validation - mean) / scale) @ coefficients[1:]
    )
    return probabilities, mean, scale, coefficients


def select_inside_outer(development: pd.DataFrame, feature_sets: dict,
                        regularization_grid: list[float]):
    candidates = []
    for family, features in feature_sets.items():
        for regularization in regularization_grid:
            oof = np.full(len(development), np.nan)
            for inner_fold in sorted(development["inner_fold"].unique()):
                validation_mask = development["inner_fold"].eq(inner_fold).to_numpy()
                probabilities, _, _, _ = fit_predict(
                    development.loc[~validation_mask], development.loc[validation_mask],
                    list(features), float(regularization),
                )
                oof[validation_mask] = probabilities
            if np.isnan(oof).any():
                raise RuntimeError("Predicciones internas incompletas")
            threshold, result = choose_threshold(
                development["gt_positive"].to_numpy(dtype=bool), oof
            )
            candidates.append({
                "family": family,
                "features": list(features),
                "regularization": float(regularization),
                "decision_threshold": threshold,
                "inner_metrics": result,
                "inner_probabilities": oof,
            })
    def key(candidate):
        result = candidate["inner_metrics"]
        return (
            result["balanced_accuracy"], result["sensitivity"],
            result["specificity"], -len(candidate["features"]),
            candidate["regularization"],
            -abs(candidate["decision_threshold"] - 0.5),
        )
    selected = max(candidates, key=key)
    return selected, candidates


def paired_exact(actual, prediction_a, prediction_b) -> dict:
    actual = np.asarray(actual, dtype=bool)
    correct_a = np.asarray(prediction_a, dtype=bool) == actual
    correct_b = np.asarray(prediction_b, dtype=bool) == actual
    a_only = int(np.sum(correct_a & ~correct_b))
    b_only = int(np.sum(~correct_a & correct_b))
    discordant = a_only + b_only
    p = float(binomtest(min(a_only, b_only), discordant, 0.5).pvalue) \
        if discordant else 1.0
    return {
        "a_correct_b_wrong": a_only,
        "a_wrong_b_correct": b_only,
        "discordant": discordant,
        "two_sided_exact_p": p,
    }


def bootstrap_differences(frame: pd.DataFrame, comparator: str, repetitions: int,
                          seed: int) -> dict:
    groups = {
        group: rows.index.to_numpy(dtype=int)
        for group, rows in frame.groupby("subject_surrogate", sort=True)
    }
    keys = np.array(sorted(groups))
    rng = np.random.default_rng(seed)
    names = ["sensitivity", "specificity", "balanced_accuracy", "f1", "mcc"]
    values = {name: [] for name in names}
    observed_h009 = metrics(frame["gt_positive"], frame["h009_prediction"])
    observed_control = metrics(frame["gt_positive"], frame[comparator])
    for _ in range(repetitions):
        sampled = rng.choice(keys, size=len(keys), replace=True)
        indices = np.concatenate([groups[key] for key in sampled])
        bag = frame.loc[indices]
        h009 = metrics(bag["gt_positive"], bag["h009_prediction"])
        control = metrics(bag["gt_positive"], bag[comparator])
        for name in names:
            difference = h009[name] - control[name]
            if np.isfinite(difference):
                values[name].append(float(difference))
    return {
        name: {
            "observed_difference": float(observed_h009[name] - observed_control[name]),
            "cluster_bootstrap_ci95": [
                float(np.quantile(values[name], 0.025)),
                float(np.quantile(values[name], 0.975)),
            ],
        }
        for name in names
    }


def subgroup_table(frame: pd.DataFrame, column: str) -> list[dict]:
    output = []
    for value, group in frame.groupby(column, dropna=False, sort=True):
        output.append({
            column: str(value), "images": int(len(group)),
            **metrics(group["gt_positive"], group["h009_prediction"]),
        })
    return output


def main() -> None:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    features = pd.read_csv(args.features, dtype={"image_id": str, "subject_surrogate": str})
    features["gt_positive"] = as_bool(features["gt_positive"])
    splits = pd.read_csv(args.splits, dtype={"image_id": str, "subject_surrogate": str})
    h008 = pd.read_csv(args.h008, dtype={"image_id": str, "subject_surrogate": str})
    h008["legacy_predicted_positive"] = as_bool(h008["legacy_predicted_positive"])
    h008["rawnorm_predicted_positive"] = as_bool(h008["rawnorm_predicted_positive"])
    if len(features) != config["images_expected"] or features["image_id"].duplicated().any():
        raise RuntimeError("Matriz de caracteristicas H009 inesperada")
    feature_sets = config["models"]["candidate_feature_sets"]
    missing = sorted({name for values in feature_sets.values() for name in values} - set(features))
    if missing:
        raise RuntimeError(f"Faltan variables: {missing}")

    outer_rows = []
    model_records = []
    selection_records = []
    for outer_fold in range(int(config["validation"]["outer_folds"])):
        fold_split = splits[splits["outer_fold"].eq(outer_fold)].copy()
        dev_split = fold_split[fold_split["role"].eq("internal_development")]
        ext_split = fold_split[fold_split["role"].eq("external_validation")]
        if set(dev_split["subject_surrogate"]) & set(ext_split["subject_surrogate"]):
            raise RuntimeError(f"Fuga de grupo en fold externo {outer_fold}")
        if dev_split.groupby("subject_surrogate")["inner_fold"].nunique().max() != 1:
            raise RuntimeError(f"Grupo dividido entre folds internos en outer {outer_fold}")
        development = features.merge(
            dev_split[["image_id", "inner_fold"]], on="image_id",
            how="inner", validate="one_to_one",
        )
        external = features[features["image_id"].isin(ext_split["image_id"])].copy()
        selected, candidates = select_inside_outer(
            development, feature_sets,
            [float(value) for value in config["models"]["regularization_grid"]],
        )
        probabilities, mean, scale, coefficients = fit_predict(
            development, external, selected["features"], selected["regularization"]
        )
        external["h009_probability"] = probabilities
        external["h009_prediction"] = probabilities >= selected["decision_threshold"]
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
        model_records.append({
            "outer_fold": outer_fold,
            "development_images": int(len(development)),
            "external_images": int(len(external)),
            "family": selected["family"],
            "features": selected["features"],
            "regularization": selected["regularization"],
            "decision_threshold": selected["decision_threshold"],
            "inner_metrics": selected["inner_metrics"],
            "feature_mean": mean.tolist(),
            "feature_scale": scale.tolist(),
            "intercept": float(coefficients[0]),
            "coefficients_standardized": coefficients[1:].tolist(),
        })

    predictions = pd.concat(outer_rows, ignore_index=True)
    if len(predictions) != len(features) or predictions["image_id"].duplicated().any():
        raise RuntimeError("Evaluacion externa H009 incompleta o duplicada")
    predictions = predictions.merge(
        h008[[
            "image_id", "legacy_predicted_positive", "rawnorm_predicted_positive",
            "reference_prediction",
        ]], on="image_id", how="left", validate="one_to_one",
    )
    predictions = predictions.sort_values("image_id").reset_index(drop=True)
    predictions = predictions.rename(columns={
        "legacy_predicted_positive": "legacy_prediction",
        "rawnorm_predicted_positive": "rawnorm_frozen_prediction",
    })
    comparison = {
        "legacy_reference": metrics(predictions["gt_positive"], predictions["legacy_prediction"]),
        "rawnorm_frozen_classifier": metrics(
            predictions["gt_positive"], predictions["rawnorm_frozen_prediction"]
        ),
        "h009_nested_rawnorm": metrics(
            predictions["gt_positive"], predictions["h009_prediction"]
        ),
    }
    gates = config["promotion_gates"]
    h009_result = comparison["h009_nested_rawnorm"]
    promotion = {
        "sensitivity_pass": bool(h009_result["sensitivity"] >= gates["minimum_sensitivity"]),
        "specificity_pass": bool(h009_result["specificity"] >= gates["minimum_specificity"]),
        "balanced_accuracy_strict_pass": bool(
            h009_result["balanced_accuracy"] > gates["minimum_balanced_accuracy"]
        ),
    }
    promotion["all_gates_pass"] = bool(all(promotion.values()))
    bootstrap_repetitions = int(config["validation"]["bootstrap_replicates"])
    bootstrap_seed = int(config["validation"]["bootstrap_seed"])
    inference = {
        "h009_minus_legacy": bootstrap_differences(
            predictions, "legacy_prediction", bootstrap_repetitions, bootstrap_seed
        ),
        "h009_minus_rawnorm_frozen": bootstrap_differences(
            predictions, "rawnorm_frozen_prediction", bootstrap_repetitions,
            bootstrap_seed + 1,
        ),
        "mcnemar_h009_vs_legacy_all": paired_exact(
            predictions["gt_positive"], predictions["h009_prediction"],
            predictions["legacy_prediction"],
        ),
        "mcnemar_h009_vs_legacy_positives": paired_exact(
            predictions.loc[predictions["gt_positive"], "gt_positive"],
            predictions.loc[predictions["gt_positive"], "h009_prediction"],
            predictions.loc[predictions["gt_positive"], "legacy_prediction"],
        ),
        "mcnemar_h009_vs_legacy_negatives": paired_exact(
            predictions.loc[~predictions["gt_positive"], "gt_positive"],
            predictions.loc[~predictions["gt_positive"], "h009_prediction"],
            predictions.loc[~predictions["gt_positive"], "legacy_prediction"],
        ),
    }
    summary = {
        "experiment_id": config["experiment_id"],
        "status": "completed",
        "images": int(len(predictions)),
        "positives": int(predictions["gt_positive"].sum()),
        "negatives": int((~predictions["gt_positive"]).sum()),
        "threshold_formula_invariant": config["threshold_formula_invariant"],
        "test_v7_used": False,
        "patient_level_validation_claimed": False,
        "comparison": comparison,
        "promotion": promotion,
        "inference": inference,
        "subgroups": {
            "outer_fold": subgroup_table(predictions, "evaluated_outer_fold"),
            "view": subgroup_table(predictions, "view"),
            "acr": subgroup_table(predictions, "acr"),
        },
        "selected_models": [{
            key: record[key] for key in (
                "outer_fold", "family", "regularization", "decision_threshold",
                "inner_metrics",
            )
        } for record in model_records],
        "limitations": config["interpretation_limits"],
    }
    predictions_path = args.output / "h009_outer_predictions.csv"
    selection_path = args.output / "h009_inner_model_selection.csv"
    models_path = args.output / "h009_outer_models.json"
    summary_path = args.output / "h009_summary.json"
    predictions.to_csv(predictions_path, index=False)
    pd.DataFrame(selection_records).to_csv(selection_path, index=False)
    models_path.write_text(json.dumps(model_records, indent=2), encoding="utf-8")
    summary.update({
        "artifacts_sha256": {
            "config": sha256(args.config), "features": sha256(args.features),
            "splits": sha256(args.splits), "h008": sha256(args.h008),
            "predictions": sha256(predictions_path),
            "selection": sha256(selection_path), "models": sha256(models_path),
        }
    })
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({
        "comparison": comparison, "promotion": promotion,
        "selected_models": summary["selected_models"],
    }, indent=2))


if __name__ == "__main__":
    main()
