#!/usr/bin/env python3
"""Genera figuras trazables para el manuscrito EMBC 2027 de DART-MC H010."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "results" / "inbreast_v8_h010" / "nested_evaluation" / "h010_summary.json"
PREDICTIONS = (
    ROOT
    / "results"
    / "inbreast_v8_h010"
    / "nested_evaluation"
    / "h010_outer_predictions_long.csv"
)
OUT = ROOT / "docs" / "figures" / "embc2027"


FONT_REGULAR = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size=size)


def save(image: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    image.save(OUT / name, dpi=(300, 300), optimize=True)


def centered_multiline(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, text_font, fill: str) -> None:
    box = draw.multiline_textbbox((0, 0), text, font=text_font, spacing=3, align="center")
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.multiline_text((xy[0] - width / 2, xy[1] - height / 2), text, font=text_font, fill=fill, spacing=3, align="center")


def pipeline_figure() -> None:
    image = Image.new("RGB", (1005, 900), "white")
    draw = ImageDraw.Draw(image)
    labels = [
        "Mammogram and\nbreast mask",
        "Robust intramammary\nnormalization",
        "Structure tensor and\nisotropy-energy response D",
        "Image-specific threshold\nT = min(0.95, mean + 20 std)",
        "Candidate aggregation and\nnested image classification",
    ]
    ys = [90, 260, 430, 600, 770]
    fills = ["#EAF2F8", "#EAF2F8", "#D6EAF8", "#AED6F1", "#E8F6F3"]
    body_font = font(26)
    for i, (label, y, fill) in enumerate(zip(labels, ys, fills)):
        draw.rounded_rectangle((110, y, 895, y + 110), radius=16, fill=fill, outline="#34495E", width=3)
        centered_multiline(draw, (502, y + 55), label, body_font, "#17202A")
        if i < len(labels) - 1:
            x = 502
            draw.line((x, y + 110, x, ys[i + 1] - 12), fill="#34495E", width=4)
            draw.polygon([(x - 11, ys[i + 1] - 23), (x + 11, ys[i + 1] - 23), (x, ys[i + 1] - 5)], fill="#34495E")
    save(image, "dart_mc_pipeline.png")


def performance_figure(summary: dict) -> None:
    metrics = {int(row["mode"]): row for row in summary["method_metrics"]}
    selected = [metrics[0], metrics[26], metrics[10], metrics[3]]
    names = ["DART-MC", "Kapur", "Otsu", "Fixed 0.15"]
    sensitivity = [100 * row["sensitivity"] for row in selected]
    specificity = [100 * row["specificity"] for row in selected]
    balanced = [100 * row["balanced_accuracy"] for row in selected]

    image = Image.new("RGB", (1005, 705), "white")
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = 110, 55, 970, 570
    min_y, max_y = 55.0, 90.0
    axis_font = font(20)
    label_font = font(20)
    legend_font = font(18)

    def ypix(value: float) -> float:
        return bottom - (value - min_y) * (bottom - top) / (max_y - min_y)

    for tick in range(55, 91, 5):
        y = ypix(tick)
        draw.line((left, y, right, y), fill="#D9D9D9", width=2)
        draw.text((left - 55, y - 11), str(tick), font=axis_font, fill="#333333")
    draw.line((left, top, left, bottom), fill="#333333", width=3)
    draw.line((left, bottom, right, bottom), fill="#333333", width=3)

    colors = ["#4C78A8", "#F58518", "#54A24B"]
    series = [sensitivity, specificity, balanced]
    group_width = (right - left) / len(names)
    bar_width = 45
    for i, name in enumerate(names):
        center = left + group_width * (i + 0.5)
        for j, values in enumerate(series):
            x0 = center + (j - 1) * (bar_width + 5) - bar_width / 2
            y0 = ypix(values[i])
            draw.rectangle((x0, y0, x0 + bar_width, bottom), fill=colors[j])
        box = draw.textbbox((0, 0), name, font=label_font)
        draw.text((center - (box[2] - box[0]) / 2, bottom + 18), name, font=label_font, fill="#222222")

    legend = [("Sensitivity", colors[0]), ("Specificity", colors[1]), ("Balanced accuracy", colors[2])]
    x = 120
    for name, color in legend:
        draw.rectangle((x, 635, x + 25, 655), fill=color)
        draw.text((x + 33, 630), name, font=legend_font, fill="#222222")
        x += 245 if name != "Balanced accuracy" else 0
    save(image, "h010_performance.png")


def threshold_figure(predictions: pd.DataFrame) -> None:
    dart = predictions[predictions["mode"] == 0].copy()
    dart["outcome"] = np.select(
        [
            dart["gt_positive"] & dart["prediction"],
            ~dart["gt_positive"] & ~dart["prediction"],
            ~dart["gt_positive"] & dart["prediction"],
            dart["gt_positive"] & ~dart["prediction"],
        ],
        ["TP", "TN", "FP", "FN"],
        default="",
    )
    order = ["TP", "FN", "TN", "FP"]
    groups = [dart.loc[dart["outcome"] == key, "adaptive_threshold"].to_numpy() for key in order]

    image = Image.new("RGB", (1005, 675), "white")
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = 125, 45, 960, 565
    colors = ["#54A24B", "#E45756", "#4C78A8", "#F58518"]
    axis_font = font(20)
    label_font = font(22, bold=True)

    def ypix(value: float) -> float:
        return bottom - value * (bottom - top)

    for tick in np.arange(0, 1.01, 0.2):
        y = ypix(float(tick))
        draw.line((left, y, right, y), fill="#D9D9D9", width=2)
        draw.text((left - 70, y - 11), f"{tick:.1f}", font=axis_font, fill="#333333")
    draw.line((left, top, left, bottom), fill="#333333", width=3)
    draw.line((left, bottom, right, bottom), fill="#333333", width=3)
    cap_y = ypix(0.95)
    for x in range(left, right, 20):
        draw.line((x, cap_y, min(x + 10, right), cap_y), fill="#666666", width=2)
    draw.text((left + 8, cap_y - 30), "0.95 cap", font=axis_font, fill="#555555")

    positions = np.linspace(left + 110, right - 90, len(order))
    for x, values, color, key in zip(positions, groups, colors, order):
        q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75])
        iqr = q3 - q1
        low = max(float(values.min()), float(q1 - 1.5 * iqr))
        high = min(float(values.max()), float(q3 + 1.5 * iqr))
        box_w = 90
        draw.line((x, ypix(low), x, ypix(high)), fill="#333333", width=4)
        draw.line((x - 25, ypix(low), x + 25, ypix(low)), fill="#333333", width=4)
        draw.line((x - 25, ypix(high), x + 25, ypix(high)), fill="#333333", width=4)
        draw.rectangle((x - box_w / 2, ypix(q3), x + box_w / 2, ypix(q1)), fill=color, outline="#333333", width=3)
        draw.line((x - box_w / 2, ypix(median), x + box_w / 2, ypix(median)), fill="#111111", width=5)
        label_box = draw.textbbox((0, 0), key, font=label_font)
        draw.text((x - (label_box[2] - label_box[0]) / 2, bottom + 20), key, font=label_font, fill="#222222")
    draw.text((400, 630), "Classification outcome", font=axis_font, fill="#333333")
    save(image, "h010_threshold_by_outcome.png")


def main() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    predictions = pd.read_csv(PREDICTIONS)
    pipeline_figure()
    performance_figure(summary)
    threshold_figure(predictions)
    print(f"OK: figures written to {OUT}")


if __name__ == "__main__":
    main()
