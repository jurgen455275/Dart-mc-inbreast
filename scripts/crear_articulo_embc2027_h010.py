#!/usr/bin/env python3
"""Genera el manuscrito candidato EMBC 2027 para la propuesta DART-MC H010."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from crear_articulo_ieee_h010 import (
    caption,
    configure_page,
    heading,
    paragraph as ieee_paragraph,
    pct,
    set_columns,
    set_font,
    table,
)


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "inbreast_v8_h010" / "nested_evaluation"
FIGURES = ROOT / "docs" / "figures" / "embc2027"
OUT = ROOT / "docs"
ARTICLE = OUT / "DART_MC_EMBC_2027_SUBMISSION_CANDIDATE_H010.docx"


def paragraph(doc, text="", **kwargs):
    """Use near-IEEE text density without modifying the generic manuscript builder."""
    kwargs.setdefault("size", 9.65)
    kwargs.setdefault("space_after", 2.1)
    return ieee_paragraph(doc, text, **kwargs)


def add_picture(doc: Document, path: Path, width: float, alt_text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.keep_together = True
    run = p.add_run()
    shape = run.add_picture(str(path), width=Inches(width))
    shape._inline.docPr.set("descr", alt_text)


def page_break(doc: Document) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.add_run().add_break(WD_BREAK.PAGE)


def threshold_audit(predictions: pd.DataFrame) -> dict:
    dart = predictions[predictions["mode"] == 0].copy()
    tp = dart[dart["gt_positive"] & dart["prediction"]]
    tn = dart[~dart["gt_positive"] & ~dart["prediction"]]
    fp = dart[~dart["gt_positive"] & dart["prediction"]]
    fn = dart[dart["gt_positive"] & ~dart["prediction"]]
    capped = dart[dart["adaptive_threshold"] >= 0.95 - 1e-12]
    return {
        "minimum": float(dart["adaptive_threshold"].min()),
        "median": float(dart["adaptive_threshold"].median()),
        "maximum": float(dart["adaptive_threshold"].max()),
        "cap_count": int(len(capped)),
        "cap_tn": int((~capped["gt_positive"] & ~capped["prediction"]).sum()),
        "cap_fn": int((capped["gt_positive"] & ~capped["prediction"]).sum()),
        "tp_median": float(tp["adaptive_threshold"].median()),
        "tn_median": float(tn["adaptive_threshold"].median()),
        "fp_median": float(fp["adaptive_threshold"].median()),
        "fn_median": float(fn["adaptive_threshold"].median()),
    }


def build() -> Path:
    summary = json.loads((RESULTS / "h010_summary.json").read_text(encoding="utf-8"))
    predictions = pd.read_csv(RESULTS / "h010_outer_predictions_long.csv")
    audit = threshold_audit(predictions)
    by_mode = {int(row["mode"]): row for row in summary["method_metrics"]}
    dart = by_mode[0]
    kapur = by_mode[26]
    comparison = summary["inference"]["26"]
    ci = comparison["dart_minus_comparator"]["balanced_accuracy"][
        "subject_surrogate_cluster_bootstrap_ci95"
    ]
    mcnemar = comparison["mcnemar_all_images"]

    doc = Document()
    configure_page(doc.sections[0])
    set_columns(doc.sections[0], 1)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(9.2)

    title = doc.add_paragraph()
    title.style = doc.styles["Title"]
    title_style_ppr = doc.styles["Title"].element.get_or_add_pPr()
    title_border = title_style_ppr.find(qn("w:pBdr"))
    if title_border is not None:
        title_style_ppr.remove(title_border)
    doc.styles["Title"].font.color.rgb = RGBColor(0, 0, 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(6)
    title.paragraph_format.keep_with_next = True
    r = title.add_run(
        "DART-MC: A Reproducible Image-Adaptive Thresholding Proposal for "
        "Microcalcification Presence Classification"
    )
    set_font(r, 18.5)
    r.font.color.rgb = RGBColor(0, 0, 0)

    authors = paragraph(
        doc,
        "Johnny Villalobos Murillo* and Jurgen Herrera Alfaro",
        centered=True,
        size=10.5,
        first_indent=False,
        space_after=1.5,
    )
    authors.runs[0].bold = True
    paragraph(
        doc,
        "Laboratorio de Procesamiento de Imágenes Digitales, Universidad Nacional, "
        "Heredia, Costa Rica",
        centered=True,
        italic=True,
        size=9.2,
        first_indent=False,
        space_after=1.2,
    )
    paragraph(
        doc,
        "johnny.villalobos.murillo@una.ac.cr; jurgen.herrera.alfaro@est.una.ac.cr",
        centered=True,
        size=8.5,
        first_indent=False,
        space_after=1.2,
    )
    paragraph(
        doc,
        "*Corresponding author",
        centered=True,
        italic=True,
        size=8.2,
        first_indent=False,
        space_after=3,
    )

    body = doc.add_section(WD_SECTION.CONTINUOUS)
    configure_page(body)
    set_columns(body, 2, 300)

    abstract = (
        "Abstract—This paper presents DART-MC, a reproducible research proposal for "
        "classifying the presence of mammographic microcalcifications with a threshold "
        "computed from each image. A normalized structure-tensor isotropy-energy response "
        "D is binarized by the preserved rule T=min(0.95, mean_M(D)+20 std_M(D)). The "
        "proposal was evaluated internally on 327 INbreast images (258 positive and 69 "
        "negative) with grouped 5×4 nested validation and eight classical controls under "
        "a shared candidate and classifier pipeline. DART-MC yielded 179 true positives, "
        "57 true negatives, 12 false positives, and 79 false negatives: sensitivity "
        f"{pct(dart['sensitivity'])}%, specificity {pct(dart['specificity'])}%, and balanced "
        f"accuracy {pct(dart['balanced_accuracy'])}%. Kapur entropy reached "
        f"{pct(kapur['balanced_accuracy'])}% balanced accuracy. The paired DART-MC minus "
        f"Kapur difference was {100*(dart['balanced_accuracy']-kapur['balanced_accuracy']):+.2f} "
        f"percentage points (surrogate-group bootstrap 95% CI {100*ci[0]:+.2f} to "
        f"{100*ci[1]:+.2f}). DART-MC is therefore reported as an interpretable, "
        "high-specificity proposal rather than a superior or clinically validated method."
    )
    paragraph(doc, abstract, bold_prefix="Abstract—", size=8.6, first_indent=False)
    paragraph(
        doc,
        "Index Terms—adaptive thresholding, image binarization, INbreast, mammography, "
        "microcalcifications, structure tensor.",
        bold_prefix="Index Terms—",
        italic=True,
        size=8.6,
        first_indent=False,
    )

    heading(doc, "I. Introduction")
    paragraph(doc, (
        "Microcalcifications are small high-frequency mammographic structures whose presence "
        "and distribution can contribute to breast assessment. Their low pixel prevalence, "
        "variable acquisition conditions, dense tissue, vessels, and noise make one fixed "
        "intensity cutoff fragile. Classical global thresholds such as Otsu [1], Kapur [2], "
        "Ridler-Calvard [3], and Kittler-Illingworth [4] provide reproducible baselines. "
        "Niblack [5] and Sauvola [6] adapt to local statistics, but their response still "
        "depends on window size and method constants."
    ))
    paragraph(doc, (
        "DART-MC, Distribution-Adaptive Response Thresholding for Microcalcifications, is an "
        "image-level research proposal. It thresholds a structural response inside the breast "
        "instead of applying one intensity value to all mammograms. The research question is "
        "whether this preserved image-specific rule is a viable and interpretable alternative "
        "for classifying microcalcification presence when representation, postprocessing, "
        "classifier family, and validation are held constant. Localization is secondary."
    ))
    paragraph(doc, (
        "This study contributes a formal specification of DART-MC, a traceable grouped nested "
        "evaluation, and a controlled comparison with eight thresholding rules. It also reports "
        "the proposal's negative result against the strongest control and defines the limits "
        "imposed by image-level labels, surrogate grouping, and the absence of external validation."
    ))

    heading(doc, "II. Background and Positioning")
    paragraph(doc, (
        "Global histogram methods answer different optimization questions. Otsu maximizes "
        "between-class variance [1]; Kapur maximizes foreground and background entropy [2]; "
        "Ridler-Calvard alternates class means until convergence [3]; and Kittler-Illingworth "
        "minimizes a Gaussian error criterion [4]. These rules are deterministic once the "
        "histogram and implementation are fixed. In mammography, however, normal tissue occupies "
        "most of the image and the target can represent very few pixels. A threshold optimized "
        "on the complete gray-level histogram may therefore emphasize tissue separation instead "
        "of small bright structures."
    ))
    paragraph(doc, (
        "Local rules address spatially varying backgrounds. Niblack compares each pixel with a "
        "window mean and deviation [5], while Sauvola modifies that relation for low-contrast "
        "backgrounds [6]. Their adaptation is local, but behavior still depends on window scale "
        "and method constants. Earlier microcalcification systems used wavelets, Markov random "
        "fields, Hessian responses, morphology, and multiscale descriptors [8]-[13]. Those "
        "systems combine several stages and are not direct substitutes for an isolated threshold."
    ))
    paragraph(doc, (
        "DART-MC occupies a narrower position. It converts the mammogram into a normalized "
        "structural response that rewards local energy with low directional coherence and then "
        "computes one response threshold from that image. It is global over the anatomical mask "
        "but image-adaptive in value. Its contribution is neither parameter-free binarization nor "
        "a clinical detector. It is a reproducible hypothesis that structural-response statistics "
        "may provide an interpretable operating point for presence classification. H010 tests that "
        "hypothesis under a common downstream pipeline."
    ))

    heading(doc, "III. Methods")
    heading(doc, "A. Data and study unit", level=2)
    paragraph(doc, (
        "The available INbreast copy contained 410 full-field digital mammograms [7]. An "
        "83-image historical partition had been inspected during development and was excluded "
        "from confirmatory claims. H010 used the remaining 327 images: 258 labeled positive and "
        "69 labeled negative for microcalcification presence. The study unit was the image. No "
        "verified PatientID was available in the files used. A filename token named "
        "subject_surrogate kept related acquisitions in one fold, but it is not asserted to be "
        "a patient identifier."
    ))

    heading(doc, "B. Structural response and adaptive threshold", level=2)
    paragraph(doc, (
        "DICOM values were clipped at the image-specific 0.5th and 99.5th percentiles inside "
        "the inherited breast mask M and mapped to [0,1]. Smoothed Sobel gradients formed a "
        "locally averaged 2×2 structure tensor J. For eigenvalues lambda1>=lambda2>=0, coherence "
        "C and isotropy-energy E were defined by"
    ))
    from crear_articulo_ieee_h010 import equation
    equation(doc, "C=(λ₁−λ₂)/(λ₁+λ₂+ε),   E=(1−C)(λ₁+λ₂)/max_M(λ₁+λ₂)", 1)
    paragraph(doc, (
        "The normalized response is D=E/(max(E)+ε). The preserved DART-MC threshold and binary "
        "map are"
    ))
    equation(doc, "T=min(0.95, μ_M(D)+20σ_M(D)),   B(p)=1[D(p)>T]", 2)
    paragraph(doc, (
        "The mean μ_M(D) and population standard deviation σ_M(D) are recomputed for every "
        "image. Thus T changes with the observed response distribution. The multiplier 20 "
        "controls selectivity and 0.95 caps the threshold within the normalized response range. "
        "Both are frozen constants inherited from the original hypothesis; they are not adaptive "
        "and are not claimed to be universally optimal. Freezing them prevents post-hoc tuning."
    ))
    paragraph(doc, (
        "Each term has a distinct role. Values of C near zero describe approximately isotropic "
        "local structure, whereas values near one describe strongly oriented structure. "
        "Multiplying 1-C by normalized gradient energy favors compact high-energy responses over "
        "elongated edges. The mean term places the decision relative to the image response "
        "background, and the deviation term increases selectivity when that response is dispersed. "
        "Because D is normalized to [0,1], 20 and 0.95 are dimensionless design constants rather "
        "than fixed mammographic intensity levels. The rule remains image-adaptive even though it "
        "is not free of fixed parameters."
    ))
    paragraph(doc, (
        "The robust normalization also uses fixed percentile positions, but their intensity "
        "values are recalculated inside M for every mammogram. A fixed raw gray level would change "
        "meaning with detector scaling, whereas an image percentile and normalized response "
        "operate on the observed distribution. The formula may still be influenced by contrast, "
        "noise, pixel spacing, and masking because these factors alter D. H010 evaluates the "
        "frozen formulation rather than claiming acquisition invariance."
    ))
    add_picture(
        doc,
        FIGURES / "dart_mc_pipeline.png",
        2.72,
        "DART-MC processing pipeline from mammogram normalization to image classification",
    )
    caption(doc, "Fig. 1. DART-MC H010 processing sequence. The threshold formula is preserved.")

    heading(doc, "C. Classification and validation", level=2)
    paragraph(doc, (
        "Eight-connected components were filtered by shared physical-area and evidence rules. "
        "Twenty-three aggregate descriptors summarized candidate density, response, contrast, "
        "compactness, clustering, position, and area. Class-balanced L2 logistic regression "
        "mapped these descriptors to image-level presence. Feature families of 9 and 23 "
        "variables and regularization values {0.01, 0.1, 1, 10} were selected only within each "
        "outer fold. Each image received one prediction from a model that had not used that fold."
    ))
    paragraph(doc, (
        "DART-MC and eight controls used the same normalized input, mask, response D, connectivity, "
        "postfilters, features, model grid, and grouped 5×4 nested validation. Only the rule that "
        "converted D to a binary map changed. Controls were fixed D=0.15, masked Otsu, the 99.99th "
        "percentile, Niblack, Sauvola, Kapur, Kittler-Illingworth, and Ridler-Calvard. Ground-truth "
        "labels were not supplied to the C++ extractor."
    ))
    paragraph(doc, (
        "Balanced accuracy was primary because 78.9% of images were positive. Secondary metrics "
        "were sensitivity, specificity, F1, precision, negative predictive value, and Matthews "
        "correlation coefficient. Paired differences used exact McNemar tests and 2,000 bootstrap "
        "repetitions resampled by subject_surrogate. The post-hoc threshold audit below is "
        "descriptive and was not used to alter the algorithm."
    ))

    heading(doc, "D. Development sequence and traceability", level=2)
    paragraph(doc, (
        "The comparison followed a documented sequence. Early failure attribution showed that "
        "many positive images lost candidate evidence before the final postfilters. Robust "
        "normalization of the available DICOM values restored structural response, but the prior "
        "image classifier was no longer calibrated to the changed features. H009 therefore moved "
        "feature-family, regularization, and decision-threshold selection inside grouped nested "
        "validation. H010 preserved that framework and changed only the rule that binarized D. "
        "This separates acquisition representation, binarization, and image classification."
    ))
    paragraph(doc, (
        "The H010 question, primary metric, controls, split file, and model grid were recorded "
        "before full extraction. The C++ extractor did not receive the ground-truth class. The "
        "repository stores source code, configuration, grouped folds, per-image features, "
        "out-of-fold predictions, selected models, summary tables, and SHA-256 hashes. A frozen "
        "full-data configuration is retained only for future external evaluation; its training fit "
        "is not reported as performance."
    ))

    heading(doc, "E. Computational complexity", level=2)
    paragraph(doc, (
        "For N pixels, fixed-kernel smoothing, tensor construction, normalization, global "
        "statistics, and connected components require Θ(N) time and Θ(N) memory. If C candidates "
        "are compared pairwise during clustering, the current complete pipeline is O(N+C²), "
        "Ω(N), and Θ(N) memory excluding candidate storage. Histogram methods with L bins are "
        "Θ(N+L). DART-MC retains linear pixel-order threshold computation but incurs the constant "
        "cost of constructing the structural response. No wall-clock superiority is claimed."
    ))

    heading(doc, "IV. Results")
    heading(doc, "A. Reproduction and primary comparison", level=2)
    paragraph(doc, (
        "The DART-MC branch reproduced the previous H009 candidate counts and all 327 nested "
        "predictions within the declared 10⁻⁷ floating-point tolerance. Adding the controls did "
        "not change the preserved adaptive branch. Table I reports the image-level results."
    ))
    rows = []
    for mode in [0, 3, 10, 15, 24, 25, 26, 27, 28]:
        row = by_mode[mode]
        name = {
            0: "DART-MC",
            3: "Fixed 0.15",
            10: "Otsu",
            15: "Pctl. .9999",
            24: "Niblack",
            25: "Sauvola",
            26: "Kapur",
            27: "Kittler",
            28: "Ridler",
        }[mode]
        rows.append([
            name,
            f"{row['tp']}/{row['tn']}/{row['fp']}/{row['fn']}",
            pct(row["sensitivity"]),
            pct(row["specificity"]),
            pct(row["balanced_accuracy"]),
            f"{row['mcc']:.3f}",
        ])
    caption(doc, "TABLE I. NESTED IMAGE-LEVEL RESULTS ON 327 INBREAST IMAGES")
    table(
        doc,
        ["Method", "TP/TN/FP/FN", "Se", "Sp", "BA", "MCC"],
        rows,
        widths=[0.73, 0.86, 0.35, 0.35, 0.35, 0.40],
        font_size=6.45,
    )
    paragraph(doc, (
        f"DART-MC achieved {pct(dart['balanced_accuracy'])}% balanced accuracy with "
        f"{pct(dart['sensitivity'])}% sensitivity and {pct(dart['specificity'])}% specificity. "
        f"Its precision was {pct(dart['precision'])}%, but this value must be read with the "
        "positive-heavy class distribution. Kapur was the strongest control at "
        f"{pct(kapur['balanced_accuracy'])}% balanced accuracy. DART-MC minus Kapur was "
        f"{100*(dart['balanced_accuracy']-kapur['balanced_accuracy']):+.2f} percentage points "
        f"(surrogate-group bootstrap 95% CI {100*ci[0]:+.2f} to {100*ci[1]:+.2f}). Exact "
        f"McNemar testing gave p={mcnemar['two_sided_exact_p']:.2e}, with "
        f"{mcnemar['a_correct_b_wrong']} images correct only for DART-MC and "
        f"{mcnemar['a_wrong_b_correct']} correct only for Kapur. Because Kapur was selected "
        "after inspecting eight controls, this comparison is descriptive and unadjusted for "
        "multiplicity."
    ))
    paragraph(doc, (
        f"The DART-MC confusion matrix contained {dart['tp']} true positives, {dart['tn']} true "
        f"negatives, {dart['fp']} false positives, and {dart['fn']} false negatives. Its negative "
        f"predictive value was {pct(dart['npv'])}%, consistent with the number of missed positive "
        "images and incompatible with stand-alone exclusion. Kapur recovered "
        f"{kapur['tp']-dart['tp']} additional positive images while adding "
        f"{kapur['fp']-dart['fp']} false positives relative to DART-MC. This paired tradeoff, not "
        "positive precision alone, determines the interpretation of the proposal."
    ))
    add_picture(
        doc,
        FIGURES / "h010_performance.png",
        3.18,
        "Sensitivity specificity and balanced accuracy for DART-MC and selected controls",
    )
    caption(doc, "Fig. 2. H010 performance for DART-MC and representative controls.")

    heading(doc, "B. Descriptive threshold audit", level=2)
    paragraph(doc, (
        f"Across the 327 DART-MC images, T ranged from {audit['minimum']:.3f} to "
        f"{audit['maximum']:.2f}, with median {audit['median']:.3f}. The 0.95 cap activated in "
        f"{audit['cap_count']} images: {audit['cap_tn']} true negatives and {audit['cap_fn']} "
        "false negatives. Median T was "
        f"{audit['tp_median']:.2f} for true positives, {audit['fn_median']:.2f} for false "
        f"negatives, {audit['tn_median']:.2f} for true negatives, and "
        f"{audit['fp_median']:.2f} for false positives. These distributions show that H010 "
        "adapted numerically across images and that higher thresholds accompanied many negative "
        "decisions. They do not establish that changing the threshold would improve independent "
        "performance."
    ))
    paragraph(doc, (
        "The ordering of medians is consistent with the intended selectivity: true negatives "
        "received the largest typical thresholds and true positives the smallest. The same "
        "behavior also exposes the principal failure mode because subtle positive images can fall "
        "on the restrictive side of the distribution. Normal isotropic structures, imperfect "
        "masking, and noise remain plausible sources of the 12 false positives, but H010 does not "
        "contain lesion-level adjudication sufficient to assign one anatomical cause to every error."
    ))
    add_picture(
        doc,
        FIGURES / "h010_threshold_by_outcome.png",
        3.18,
        "Distribution of DART-MC image-specific threshold by classification outcome",
    )
    caption(doc, "Fig. 3. Post-hoc threshold distributions by H010 classification outcome.")

    heading(doc, "V. Discussion")
    paragraph(doc, (
        "The experiment supports a limited but useful conclusion. DART-MC computed a distinct "
        "threshold from each image and achieved the highest specificity among the principal "
        "methods, with 12 false positives. It also produced 79 false negatives and lower "
        "balanced accuracy than Kapur. The result therefore supports technical feasibility and "
        "interpretability, not superiority. For screening, the observed sensitivity would be "
        "insufficient for a stand-alone rule-out system. A more defensible future role is an "
        "interpretable component or high-specificity stage whose contribution is tested in an "
        "independent cohort."
    ))
    paragraph(doc, (
        "The threshold audit provides a traceable explanation for part of the tradeoff. False "
        "negatives had a higher median T than true positives, and the cap included two positive "
        "images classified as negative. This observation is hypothesis-generating because the "
        "same data were used to identify it. The constants 20 and 0.95 should remain unchanged "
        "for the present report. A future locked ablation may compare the preserved formula with "
        "training-only estimates or image-derived alternatives without rewriting H010."
    ))
    paragraph(doc, (
        "Kapur's stronger internal balanced accuracy does not invalidate the research question. "
        "It establishes a demanding reference and prevents an unsupported superiority claim. "
        "DART-MC offers a different inductive bias: it uses a tensor-derived response and makes "
        "the image-specific threshold directly inspectable. Whether that interpretability is "
        "useful depends on future evidence that it transfers across acquisition settings or adds "
        "complementary information to a stronger classifier. The present experiment demonstrates "
        "how to test that question but does not answer it externally."
    ))
    paragraph(doc, (
        "Acquisition can influence the threshold indirectly. Detector calibration, bit depth, "
        "pixel spacing, compression, and exposure affect local gradients and tensor energy before "
        "normalization. Per-image percentile mapping removes absolute intensity scale but cannot "
        "recreate detail lost through resolution or noise. Physical candidate areas reduce one "
        "source of scale variation, while the spatial operators remain acquisition-dependent. "
        "External validation should therefore report equipment and acquisition characteristics."
    ))
    paragraph(doc, (
        "The main limitations are one dataset, image-level labels, class imbalance, no verified "
        "PatientID, no independent external cohort, and candidate filters developed around the "
        "adaptive branch. The surrogate bootstrap does not establish patient-level uncertainty. "
        "The historical 83-image partition is not a valid external test because it informed "
        "development. The repository permits computational reproduction, but the INbreast files "
        "must be obtained separately under their applicable access terms."
    ))
    paragraph(doc, (
        "The study also lacks prospective assessment, radiologist adjudication of individual "
        "errors, calibration across institutions, and a clinically defined operating threshold. "
        "The post-hoc threshold distributions are exploratory. The bootstrap resamples available "
        "surrogate groups and cannot compensate for unknown patient mapping. These limitations "
        "constrain the work to a methodological proposal with internal evidence."
    ))

    heading(doc, "A. Future validation", level=2)
    paragraph(doc, (
        "The next study should apply the frozen simplified_9 model, L2 regularization 0.01, and "
        "decision threshold 0.426932 to an independent cohort with verified patient identifiers. "
        "A separate preregistered ablation may then test the multiplier and cap without modifying "
        "the H010 record. Performance should be reported by patient and image, with acquisition "
        "strata, calibration, confidence intervals, and error review. Without an independent "
        "cohort, subsequent INbreast analyses remain exploratory rather than external confirmation."
    ))

    heading(doc, "VI. Reproducibility and prespecified next test")
    heading(doc, "A. Executable specification", level=2)
    paragraph(doc, (
        "Algorithm 1 states the proposal at the level required for an independent implementation. "
        "Input: mammogram I and breast mask M. Output: image-level microcalcification-presence "
        "prediction y. (1) Clip I at its 0.5th and 99.5th percentiles within M and map the retained "
        "range to [0,1]. (2) Compute smoothed Sobel gradients and the locally averaged 2×2 structure "
        "tensor J. (3) Obtain eigenvalues lambda1>=lambda2>=0 and calculate coherence C, "
        "isotropy-energy E, and normalized response D as in (1). (4) Compute mu_M(D) and "
        "sigma_M(D), then set T=min(0.95, mu_M(D)+20 sigma_M(D)). (5) Form B(p)=1 when D(p)>T "
        "inside M and zero otherwise. (6) Aggregate eight-connected candidates with the frozen "
        "physical and evidence filters and calculate the declared image descriptors. (7) Apply the "
        "classifier selected only within each outer training set to its held-out fold and concatenate "
        "one y per image. The full-data simplified_9 model and decision threshold 0.426932 are "
        "reserved for future external evaluation and are not used to estimate internal performance."
    ))
    paragraph(doc, (
        "The archived H010 implementation is the normative computational specification for this "
        "report. The equations and Algorithm 1 explain it, but they do not silently replace details "
        "such as border handling, smoothing, component connectivity, or numerical tolerances. "
        "Reproduction requires the recorded configuration, grouped folds, and software artifacts. "
        "The repository verifier checks required files and SHA-256 hashes; the source data remain "
        "outside the repository because their distribution is governed separately."
    ))

    heading(doc, "B. Evidence boundaries", level=2)
    paragraph(doc, (
        "Three evidence levels are kept distinct. Direct evidence consists of the archived 327 "
        "out-of-fold predictions, candidate tables, summary metrics, and paired comparisons. "
        "Descriptive evidence consists of the post-hoc T distributions and error counts; it can "
        "motivate hypotheses but cannot establish their causal mechanism. Proposed evidence "
        "consists of external validation, patient-level uncertainty, acquisition-stratified analysis, "
        "and ablations of 20 or 0.95. None of those proposed experiments is presented as completed."
    ))
    paragraph(doc, (
        "The central falsifiable claim is therefore narrow: the preserved rule produces an "
        "image-specific threshold and can be evaluated reproducibly as a presence-classification "
        "component. The present data support the first part and an internal estimate of the second. "
        "They do not establish clinical benefit, lesion localization, cross-institutional "
        "generalization, or superiority to classical thresholding."
    ))

    heading(doc, "C. Decision criteria for continuation", level=2)
    paragraph(doc, (
        "A confirmatory study should freeze preprocessing, H010, the simplified_9 classifier, and "
        "the 0.426932 decision threshold before reading external labels. Its primary endpoint should "
        "remain balanced accuracy, with sensitivity and specificity reported jointly and with "
        "patient-grouped confidence intervals. Kapur should remain a prespecified control under the "
        "same candidate and classifier pipeline. Calibration, failure review, computation time, and "
        "acquisition strata should be secondary analyses."
    ))
    paragraph(doc, (
        "The proposal should be considered strengthened only if its operating tradeoff and "
        "image-adaptive behavior reproduce in an independent cohort. Any experiment that derives "
        "a multiplier or cap from images must estimate that choice using training data only and "
        "evaluate it once on untouched data. Reporting should include every attempted variant, "
        "not only the best result. If sensitivity remains near the current internal estimate, "
        "DART-MC should not be advanced as a stand-alone screening rule even if specificity remains "
        "high. These criteria prevent the proposal framing from being mistaken for validation."
    ))

    heading(doc, "VII. Conclusion")
    paragraph(doc, (
        "DART-MC H010 is a reproducible proposal for image-adaptive structural thresholding in "
        "microcalcification presence classification. Grouped nested internal evaluation on 327 "
        "INbreast images yielded 75.99% balanced accuracy and 82.61% specificity. Kapur achieved "
        "higher balanced accuracy, so the present evidence does not support a superiority claim. "
        "DART-MC remains a transparent high-specificity research proposal whose clinical value "
        "and generalization require independent validation with verified patient grouping."
    ))

    page_break(doc)
    heading(doc, "Acknowledgment")
    paragraph(doc, (
        "This work was supported by Universidad Nacional, Costa Rica, through the Laboratorio de "
        "Procesamiento de Imágenes Digitales. No grant number was available. The authors declare "
        "no known financial or personal conflicts of interest related to this work. OpenAI Codex "
        "assisted with code review, analysis scripting, figure preparation, language editing, and "
        "drafting portions of the manuscript. Numerical statements were linked to repository "
        "artifacts; the authors retain responsibility for final verification and the submitted text."
    ), size=8.0, first_indent=False)
    paragraph(doc, (
        "The reproducibility package is available at https://github.com/jurgen455275/"
        "Dart-mc-inbreast. INbreast images are not redistributed. An institutional ethics "
        "determination and archival DOI were not available at manuscript preparation."
    ), size=8.0, first_indent=False)

    heading(doc, "References")
    references = [
        "[1] N. Otsu, “A threshold selection method from gray-level histograms,” IEEE Trans. Syst., Man, Cybern., vol. 9, no. 1, pp. 62–66, 1979, doi: 10.1109/TSMC.1979.4310076.",
        "[2] J. N. Kapur, P. K. Sahoo, and A. K. C. Wong, “A new method for gray-level picture thresholding using the entropy of the histogram,” Comput. Vis. Graph. Image Process., vol. 29, no. 3, pp. 273–285, 1985, doi: 10.1016/0734-189X(85)90125-2.",
        "[3] T. W. Ridler and S. Calvard, “Picture thresholding using an iterative selection method,” IEEE Trans. Syst., Man, Cybern., vol. 8, no. 8, pp. 630–632, 1978, doi: 10.1109/TSMC.1978.4310039.",
        "[4] J. Kittler and J. Illingworth, “Minimum error thresholding,” Pattern Recognit., vol. 19, no. 1, pp. 41–47, 1986, doi: 10.1016/0031-3203(86)90030-0.",
        "[5] W. Niblack, An Introduction to Digital Image Processing. Englewood Cliffs, NJ, USA: Prentice-Hall, 1986.",
        "[6] J. Sauvola and M. Pietikäinen, “Adaptive document image binarization,” Pattern Recognit., vol. 33, no. 2, pp. 225–236, 2000, doi: 10.1016/S0031-3203(99)00055-2.",
        "[7] I. C. Moreira et al., “INbreast: Toward a full-field digital mammographic database,” Acad. Radiol., vol. 19, no. 2, pp. 236–248, 2012, doi: 10.1016/j.acra.2011.09.014.",
        "[8] W. Qian et al., “Tree structured wavelet transform segmentation of microcalcifications in digital mammography,” Med. Phys., vol. 22, no. 8, pp. 1247–1254, 1995, doi: 10.1118/1.597562.",
        "[9] M. G. Mini, V. P. Devassia, and T. Thomas, “Multiplexed wavelet transform technique for detection of microcalcification in digitized mammograms,” J. Digit. Imaging, vol. 17, no. 4, pp. 285–291, 2004, doi: 10.1007/s10278-004-1020-8.",
        "[10] S.-N. Yu, K.-Y. Li, and Y.-K. Huang, “Detection of microcalcifications in digital mammograms using wavelet filter and Markov random field model,” Comput. Med. Imaging Graph., vol. 30, no. 3, pp. 163–173, 2006, doi: 10.1016/j.compmedimag.2006.03.002.",
        "[11] B. Thangaraju, I. Vennila, and G. Chinnasamy, “Detection of microcalcification clusters using Hessian matrix and foveal segmentation method on multiscale analysis in digital mammograms,” J. Digit. Imaging, vol. 25, no. 5, pp. 607–619, 2012, doi: 10.1007/s10278-012-9489-z.",
        "[12] M. Ciecholewski, “Microcalcification segmentation from mammograms: A morphological approach,” J. Digit. Imaging, vol. 30, no. 2, pp. 172–184, 2017, doi: 10.1007/s10278-016-9923-8.",
        "[13] C. Marasinou et al., “Improving the quantitative analysis of breast microcalcifications: A multiscale approach,” J. Digit. Imaging, vol. 36, no. 3, pp. 1016–1028, 2023, doi: 10.1007/s10278-022-00751-3.",
        "[14] J. Bigun and G. H. Granlund, “Optimal orientation detection of linear symmetry,” in Proc. IEEE Int. Conf. Computer Vision, 1987, pp. 433–438, doi: 10.1109/CCV.1987.312833.",
        "[15] H. Knutsson, “Representing local structure using tensors,” in Proc. 6th Scandinavian Conf. Image Analysis, 1989, pp. 244–251.",
    ]
    for ref in references:
        paragraph(doc, ref, size=7.3, first_indent=False, space_after=1.2)

    core = doc.core_properties
    core.title = "DART-MC EMBC 2027 submission candidate H010"
    core.subject = "Image-adaptive thresholding proposal for INbreast microcalcification presence classification"
    core.author = "Johnny Villalobos Murillo; Jurgen Herrera Alfaro"
    core.keywords = "DART-MC, INbreast, adaptive thresholding, microcalcifications, EMBC 2027"
    core.comments = "Generated from traceable H010 repository artifacts."

    OUT.mkdir(parents=True, exist_ok=True)
    doc.save(ARTICLE)
    print(f"OK: {ARTICLE}")
    return ARTICLE


if __name__ == "__main__":
    build()
