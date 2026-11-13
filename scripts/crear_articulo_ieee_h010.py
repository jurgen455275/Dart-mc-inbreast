#!/usr/bin/env python3
"""Genera el manuscrito IEEE trazable de DART-MC con los resultados H010."""

from __future__ import annotations

import json
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "inbreast_v8_h010" / "nested_evaluation"
OUT = ROOT / "docs"
OUT.mkdir(parents=True, exist_ok=True)
ARTICLE = OUT / "DART_MC_IEEE_Generic_H010_2026_FINAL.docx"


def set_font(run, size=10, bold=False, italic=False):
    run.font.name = "Times New Roman"
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Times New Roman")
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Times New Roman")
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic


def configure_page(section):
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.72)
    section.bottom_margin = Inches(0.72)
    section.left_margin = Inches(0.65)
    section.right_margin = Inches(0.65)
    section.header_distance = Inches(0.3)
    section.footer_distance = Inches(0.3)


def set_columns(section, number=2, space_twips=360):
    sect_pr = section._sectPr
    cols = sect_pr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sect_pr.append(cols)
    cols.set(qn("w:num"), str(number))
    cols.set(qn("w:space"), str(space_twips))


def set_cell_margins(cell, value=40):
    tc_pr = cell._tc.get_or_add_tcPr()
    margins = tc_pr.find(qn("w:tcMar"))
    if margins is None:
        margins = OxmlElement("w:tcMar")
        tc_pr.append(margins)
    for side in ("top", "start", "bottom", "end"):
        node = margins.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_borders(table):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "bottom", "insideH"):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:color"), "000000")
        borders.append(node)
    for edge in ("left", "right", "insideV"):
        node = OxmlElement(f"w:{edge}")
        node.set(qn("w:val"), "nil")
        borders.append(node)


def no_row_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    tr_pr.append(OxmlElement("w:cantSplit"))


def mark_header_row(row):
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def paragraph(doc, text="", *, bold_prefix=None, italic=False, centered=False,
              size=9.2, first_indent=True, space_after=1.8, keep=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if centered else WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Inches(0.14) if first_indent else None
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.keep_together = keep
    if bold_prefix and text.startswith(bold_prefix):
        a = p.add_run(bold_prefix)
        b = p.add_run(text[len(bold_prefix):])
        set_font(a, size, bold=True, italic=italic)
        set_font(b, size, italic=italic)
    else:
        run = p.add_run(text)
        set_font(run, size, italic=italic)
    return p


def heading(doc, text, level=1):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_before = Pt(5 if level == 1 else 3)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text.upper() if level == 1 else text)
    set_font(run, 10 if level == 1 else 9.2, bold=level == 1, italic=level != 1)
    return p


def equation(doc, text, number):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_together = True
    run = p.add_run(f"{text}                                      ({number})")
    set_font(run, 9.2, italic=True)
    return p


def caption(doc, text):
    p = paragraph(doc, text, centered=True, size=8, first_indent=False, space_after=2)
    p.paragraph_format.keep_with_next = True
    return p


def table(doc, headers, rows, widths=None, font_size=7.4):
    obj = doc.add_table(rows=1, cols=len(headers))
    obj.alignment = WD_TABLE_ALIGNMENT.CENTER
    obj.autofit = False
    set_table_borders(obj)
    for j, value in enumerate(headers):
        cell = obj.rows[0].cells[j]
        cell.text = ""
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(str(value))
        set_font(run, font_size, bold=True)
        set_cell_margins(cell)
        if widths:
            cell.width = Inches(widths[j])
    no_row_split(obj.rows[0])
    mark_header_row(obj.rows[0])
    for values in rows:
        row = obj.add_row()
        no_row_split(row)
        for j, value in enumerate(values):
            cell = row.cells[j]
            cell.text = ""
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(str(value))
            set_font(run, font_size)
            set_cell_margins(cell)
            if widths:
                cell.width = Inches(widths[j])
    return obj


def pct(value):
    return f"{100.0 * float(value):.2f}"


def build():
    summary = json.loads((RESULTS / "h010_summary.json").read_text(encoding="utf-8"))
    frozen = json.loads((RESULTS / "h010_frozen_dart_model.json").read_text(encoding="utf-8"))
    ranked = sorted(
        summary["method_metrics"],
        key=lambda row: (row["balanced_accuracy"], row["sensitivity"], row["specificity"]),
        reverse=True,
    )
    by_mode = {int(row["mode"]): row for row in summary["method_metrics"]}
    dart = by_mode[0]
    best_control = max((row for row in ranked if int(row["mode"]) != 0),
                       key=lambda row: row["balanced_accuracy"])
    comparison = summary["inference"][str(int(best_control["mode"]))]
    ci = comparison["dart_minus_comparator"]["balanced_accuracy"][
        "subject_surrogate_cluster_bootstrap_ci95"
    ]
    mcnemar = comparison["mcnemar_all_images"]

    doc = Document()
    configure_page(doc.sections[0])
    set_columns(doc.sections[0], 1)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Times New Roman")
    normal._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Times New Roman")
    normal.font.size = Pt(9.2)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(7)
    r = title.add_run(
        "DART-MC: An Image-Adaptive Thresholding Proposal for "
        "Mammographic Microcalcification Classification"
    )
    set_font(r, 19, bold=False)
    authors = paragraph(
        doc, "Johnny Villalobos Murillo and Jurgen Herrera Alfaro",
        centered=True, size=11, first_indent=False, space_after=2,
    )
    authors.runs[0].bold = True
    paragraph(
        doc,
        "Laboratorio de Procesamiento de Imágenes Digitales (LAPID), "
        "Universidad Nacional de Costa Rica, Heredia, Costa Rica",
        centered=True, italic=True, size=9.5, first_indent=False, space_after=1.5,
    )
    paragraph(
        doc,
        "johnny.villalobos.murillo@una.ac.cr; "
        "jurgen.herrera.alfaro@est.una.ac.cr",
        centered=True, size=8.7, first_indent=False, space_after=4,
    )

    body = doc.add_section(WD_SECTION.CONTINUOUS)
    configure_page(body)
    set_columns(body, 2, 300)

    abstract = (
        "Abstract—This study evaluates DART-MC, a research proposal for classifying the "
        "presence of mammographic microcalcifications. The method computes a normalized "
        "isotropy–energy response D from a structure tensor and applies the preserved "
        "image-specific threshold T=min(0.95, μ_M(D)+20σ_M(D)). A preregistered internal "
        "comparison used 327 INbreast images (258 positive and 69 negative), robust "
        "intramammary normalization, identical masks, candidate processing, 23 aggregate "
        "features, and grouped 5×4 nested validation for DART-MC and eight classical "
        "controls. DART-MC produced "
        f"{dart['tp']} true positives, {dart['tn']} true negatives, {dart['fp']} false "
        f"positives, and {dart['fn']} false negatives; sensitivity was {pct(dart['sensitivity'])}%, "
        f"specificity {pct(dart['specificity'])}%, and balanced accuracy "
        f"{pct(dart['balanced_accuracy'])}%. The strongest evaluated classical control was "
        f"{best_control['method']} with balanced accuracy {pct(best_control['balanced_accuracy'])}%. "
        f"The paired DART-MC difference was {100*(dart['balanced_accuracy']-best_control['balanced_accuracy']):+.2f} "
        f"percentage points (subject-surrogate cluster-bootstrap 95% CI "
        f"{100*ci[0]:+.2f} to {100*ci[1]:+.2f}; exact McNemar p="
        f"{mcnemar['two_sided_exact_p']:.2e}). This is internal image-level evidence, not "
        "patient-level or clinical validation."
    )
    paragraph(doc, abstract, bold_prefix="Abstract—", size=8.8, first_indent=False)
    paragraph(
        doc,
        "Index Terms—adaptive thresholding, image binarization, INbreast, mammography, "
        "microcalcifications, structure tensor.",
        bold_prefix="Index Terms—", italic=True, size=8.8, first_indent=False,
    )

    heading(doc, "I. Introduction")
    paragraph(doc, (
        "Microcalcifications are small high-frequency structures whose presence and spatial "
        "organization can contribute to mammographic assessment. Their low prevalence at "
        "pixel level, variable acquisition conditions, dense tissue, vessels, and noise make "
        "a single intensity cutoff fragile. Classical global thresholds such as Otsu [1], "
        "entropy maximization [2], iterative selection [3], and minimum-error thresholding "
        "[4] offer reproducible baselines, whereas Niblack [5] and Sauvola [6] adapt to local "
        "statistics. However, these methods do not by themselves encode the approximately "
        "isotropic local structure expected from many microcalcification candidates."
    ))
    paragraph(doc, (
        "DART-MC (Distribution-Adaptive Response Thresholding for Microcalcifications) is "
        "therefore formulated as an image-level research proposal. It thresholds a structural "
        "response inside the breast rather than the complete gray-level histogram. The main "
        "question is deliberately narrow: under the same representation, postprocessing, "
        "classifier family, and validation design, is the preserved adaptive rule a viable "
        "alternative to representative classical thresholds for deciding whether an image "
        "contains microcalcifications? Lesion localization is secondary in this study."
    ))
    paragraph(doc, (
        "The contributions are: (1) a formal specification of the preserved adaptive rule; "
        "(2) a traceable investigation from failure attribution to robust DICOM normalization "
        "and nested classification; (3) a controlled comparison against eight global and local "
        "thresholding rules; and (4) explicit limits on claims caused by the absence of a "
        "verified PatientID and an independent external cohort."
    ))

    heading(doc, "II. Related Thresholding Methods")
    paragraph(doc, (
        "Otsu selects the split maximizing between-class variance [1]. Kapur maximizes the "
        "sum of class entropies [2]. Ridler–Calvard iteratively updates class means [3], while "
        "Kittler–Illingworth minimizes an error criterion under Gaussian class assumptions "
        "[4]. Their global statistics can be dominated by normal tissue when the target "
        "occupies very few pixels. Niblack and Sauvola use windowed mean and deviation [5], "
        "[6], which addresses slowly varying background but adds sensitivity to window size, "
        "texture, and fixed method constants. DART-MC differs conceptually because the "
        "statistics are computed on an isotropy–energy response restricted to an anatomical "
        "mask."
    ))
    paragraph(doc, (
        "Previous microcalcification systems have used wavelets, Markov random fields, "
        "Hessian-based analysis, morphology, and multiscale descriptors [8]–[13]. The present "
        "work does not claim to replace those complete detection systems; it isolates the "
        "binarization decision so that its contribution can be tested without changing the "
        "downstream candidate and classification pipeline."
    ))

    heading(doc, "III. Materials and Methods")
    heading(doc, "A. Data, labels, and grouping", level=2)
    paragraph(doc, (
        "The available INbreast copy contained 410 full-field digital mammograms [7]. The "
        "historical 83-image partition had already been inspected during development and was "
        "quarantined from confirmatory claims. All reported H010 estimates use the remaining "
        "327 images: 258 labeled positive and 69 labeled negative for microcalcification "
        "presence. No PatientID field was available in the distributed files used here. A "
        "filename token, stored as subject_surrogate, kept related acquisitions within one "
        "fold. It is not asserted to be a verified patient identity; consequently, neither "
        "patient-level independence nor patient-level performance is claimed."
    ))

    heading(doc, "B. Representation and adaptive threshold", level=2)
    paragraph(doc, (
        "DICOM intensities were clipped at the 0.5th and 99.5th percentiles measured inside "
        "the inherited breast mask and mapped to [0,1]. After smoothing, Sobel gradients "
        "formed a locally averaged 2×2 structure tensor J. If λ1≥λ2≥0 are its eigenvalues, "
        "coherence C and the unnormalized isotropy–energy response E were defined as"
    ))
    equation(doc, "C=(λ₁−λ₂)/(λ₁+λ₂+ε),     E=(1−C)(λ₁+λ₂)/max_M(λ₁+λ₂)", 1)
    paragraph(doc, (
        "The response was normalized as D=E/(max(E)+ε). For the physical analysis mask M, "
        "the preserved threshold and binary selection were"
    ))
    equation(doc, "T=min(0.95, μ_M(D)+20σ_M(D)),     B(p)=1[D(p)>T]", 2)
    paragraph(doc, (
        "Here μ_M(D) and σ_M(D) are the image-specific mean and population standard deviation "
        "of D inside M. Thus T changes with every image. The multiplier 20 controls selectivity "
        "and the 0.95 cap prevents the normalized threshold from exceeding the upper response "
        "range. They are frozen design constants inherited from the original hypothesis, not "
        "adaptive quantities and not claimed to be universally optimal. Retaining them prevents "
        "post-hoc tuning in H010 and makes external ablation a future requirement. The strict "
        "greater-than comparison is part of the specification."
    ))
    algorithm = (
        "Algorithm 1  DART-MC image classification\n"
        "Input: mammogram I, breast mask M, pixel spacing s\n"
        "1: Iₙ ← robustNormalize(I, M, 0.5%, 99.5%)\n"
        "2: J ← structureTensor(Iₙ); D ← normalizedIsotropyEnergy(J)\n"
        "3: T ← min(0.95, mean(D[M]) + 20·std(D[M]))\n"
        "4: B ← (D > T) ∧ M\n"
        "5: C ← filterPhysicalCandidates(components8(B), Iₙ, D, s)\n"
        "6: x ← aggregate23(C, M); p ← balancedLogistic(x)\n"
        "7: return p ≥ frozenDecisionThreshold"
    )
    p_algorithm = paragraph(
        doc, algorithm, size=7.8, first_indent=False, space_after=2, keep=True,
    )
    p_algorithm.paragraph_format.left_indent = Inches(0.12)
    p_algorithm.paragraph_format.right_indent = Inches(0.12)
    p_algorithm.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p_algorithm.runs[0].bold = False

    heading(doc, "C. Candidate aggregation and classification", level=2)
    paragraph(doc, (
        "Eight-connected components were converted into candidates using physical-area and "
        "evidence filters shared by all methods. Twenty-three image descriptors summarized "
        "candidate density, response and contrast extrema and means, compactness, clustering, "
        "acceptance fraction, position, border distance, evidence, and area. Class-balanced "
        "L2 logistic regression mapped these descriptors to image-level presence. Two feature "
        "families (9 and 23 variables) and regularization values {0.01, 0.1, 1, 10} were selected "
        "exclusively inside each external fold. The decision threshold maximized pooled inner "
        "balanced accuracy with sensitivity, specificity, model size, and distance to 0.5 used "
        "as deterministic tie breakers."
    ))

    heading(doc, "D. Controlled H010 experiment", level=2)
    paragraph(doc, (
        "H010 was preregistered before the full extraction. DART-MC and eight controls received "
        "the same RawNorm input, mask, D representation, connectivity, physical-area limits, "
        "postfilters, features, model grid, and grouped 5×4 nested validation. The only intended "
        "change was the rule converting D to a binary candidate map: fixed D=0.15, masked Otsu, "
        "the 99.99th percentile, local Niblack (μ+σ), local Sauvola "
        "(μ[1+0.5(σ/0.5−1)]), Kapur, Kittler–Illingworth, and Ridler–Calvard. Global histogram "
        "rules used 4,096 bins inside M; local statistics used a 0.75-mm radius, clamped to "
        "3–30 pixels. Ground-truth "
        "labels were not passed to extraction. Each image was predicted exactly once by a model "
        "that had not used its external fold."
    ))
    paragraph(doc, (
        "Primary performance was balanced accuracy, BA=(sensitivity+specificity)/2. Secondary "
        "metrics were sensitivity, specificity, F1, and Matthews correlation coefficient. "
        "Paired differences used exact McNemar tests and 2,000 bootstrap repetitions resampled "
        "by subject_surrogate. These intervals address the available grouping only and do not "
        "establish patient-level uncertainty."
    ))

    heading(doc, "E. Computational complexity", level=2)
    paragraph(doc, (
        "For N pixels, fixed-kernel filtering, tensor construction, normalization, global "
        "statistics, and connected components are Θ(N) in time and Θ(N) in memory. If C "
        "candidates are compared pairwise during clustering, the complete current pipeline is "
        "O(N+C²), Ω(N), and Θ(N) memory excluding stored candidates. Histogram methods with L "
        "bins are Θ(N+L); integral-image implementations of Niblack and Sauvola are Θ(N) but "
        "also require Θ(N) memory. DART-MC therefore has the same linear pixel-order for its "
        "threshold computation, but additional constant-factor cost from the structural map. "
        "No controlled wall-clock superiority claim is made."
    ))

    heading(doc, "IV. Results")
    heading(doc, "A. Reproduction and principal comparison", level=2)
    paragraph(doc, (
        "The H010 DART branch reproduced all H009 raw and accepted candidate counts and all 327 "
        "nested image predictions. Maximum feature differences were below the declared 10⁻⁷ "
        "floating-point tolerance. This confirms that adding the controls did not alter the "
        "preserved adaptive algorithm."
    ))
    selected_rows = []
    for mode in (0, 3, 10, 15, 24, 25, 26, 27, 28):
        row = by_mode[mode]
        selected_rows.append([
            row["method"], f"{row['tp']}/{row['tn']}/{row['fp']}/{row['fn']}",
            pct(row["sensitivity"]), pct(row["specificity"]),
            pct(row["balanced_accuracy"]), pct(row["f1"]), f"{row['mcc']:.3f}",
        ])
    caption(doc, "TABLE I. NESTED IMAGE-LEVEL RESULTS ON THE 327-IMAGE DEVELOPMENT COHORT")
    table(doc, ["Threshold", "TP/TN/FP/FN", "Se", "Sp", "BA", "F1", "MCC"],
          selected_rows, widths=[0.95, 0.66, 0.33, 0.33, 0.33, 0.33, 0.35], font_size=6.7)
    paragraph(doc, (
        f"DART-MC achieved {pct(dart['balanced_accuracy'])}% BA with "
        f"{pct(dart['sensitivity'])}% sensitivity and {pct(dart['specificity'])}% specificity. "
        f"The best evaluated control, {best_control['method']}, achieved "
        f"{pct(best_control['balanced_accuracy'])}% BA. The DART-MC minus control difference "
        f"was {100*(dart['balanced_accuracy']-best_control['balanced_accuracy']):+.2f} percentage "
        f"points, with a subject-surrogate cluster-bootstrap 95% CI of {100*ci[0]:+.2f} to "
        f"{100*ci[1]:+.2f} points. Exact McNemar testing yielded "
        f"p={mcnemar['two_sided_exact_p']:.2e} ({mcnemar['a_correct_b_wrong']} images correct "
        f"only with DART-MC and {mcnemar['a_wrong_b_correct']} only with the control)."
    ))
    paragraph(doc, (
        "Because the strongest control was identified after observing all eight control "
        "results, this pairwise interval and p value are descriptive and unadjusted for "
        "multiplicity. They support a viability comparison, not a confirmatory superiority "
        "claim."
    ))

    heading(doc, "B. Frozen research configuration", level=2)
    paragraph(doc, (
        f"For future external evaluation, the deployment candidate was frozen after H010 as "
        f"feature family {frozen['family']} with {len(frozen['features'])} variables, "
        f"L2 regularization {frozen['regularization']}, and decision threshold "
        f"{frozen['decision_threshold']:.6f}. The coefficients, training means, scales, source "
        "hashes, split file, and per-image predictions are stored with the experiment. This "
        "full-data fit was not scored on its training images; the reported estimates remain "
        "the nested out-of-fold values."
    ))

    heading(doc, "V. Discussion")
    paragraph(doc, (
        "Under the controlled internal protocol, DART-MC produced the highest specificity "
        "among the principal methods but lower sensitivity and balanced accuracy than Kapur. "
        "The interval for DART-MC minus Kapur balanced accuracy remained below zero, so the "
        "experiment does not support superiority and internally favors Kapur for the primary "
        "metric. DART-MC remains a viable high-specificity research direction rather than the "
        "preferred method in this ranking. The bootstrap interval uses a surrogate grouping "
        "scheme, multiple controls were compared on one dataset, and downstream candidate "
        "filters were originally developed around the adaptive branch."
    ))
    paragraph(doc, (
        "The chronological audit explains why thresholding alone was insufficient. Earlier "
        "failure attribution found many false negatives before postfiltering. Raw DICOM "
        "normalization restored structural response, but applying the inherited classifier "
        "without retraining reduced specificity. H009 therefore nested the image classifier, "
        "and H010 subsequently isolated the threshold rule. This sequence separates three "
        "causal layers—acquisition representation, binarization, and image classification—and "
        "reduces the risk of attributing all gains to the threshold formula."
    ))
    paragraph(doc, (
        "The remaining false negatives indicate that a high-specificity threshold can still "
        "suppress subtle responses, while false positives can arise from normal isotropic "
        "structures, borders, noise, or imperfect masking. Because the research goal is image "
        "classification, future optimization should prioritize calibration and independent "
        "generalization rather than adding localization complexity. The constants 20 and 0.95 "
        "should next be evaluated in a locked ablation or estimated exclusively within training "
        "folds; changing them in the present experiment would invalidate its confirmatory role."
    ))

    heading(doc, "VI. Limitations, Ethics, and Reproducibility")
    paragraph(doc, (
        "This is a retrospective secondary analysis of a publicly described, de-identified "
        "dataset. No local ethics-committee determination or waiver was available in the project "
        "records at manuscript preparation; the authors must obtain and report the determination "
        "required by the selected venue. No verified PatientID was available, the sample contains "
        "multiple potentially related acquisitions, and subject_surrogate only reduces—rather "
        "than proves the absence of—dependence leakage. The 83-image historical partition is not "
        "an independent test, and no external dataset or prospective study was performed."
    ))
    paragraph(doc, (
        "The local reproducibility package contains the exact C++ extractor, Python orchestration, "
        "preregistered H010 configuration, grouped splits, per-image features and predictions, "
        "model parameters, and SHA-256 hashes. A permanent public repository and archival DOI "
        "were not assigned at manuscript preparation. The INbreast image files are not redistributed "
        "in that package; authorized users must obtain the dataset separately."
    ))

    heading(doc, "Funding", level=2)
    paragraph(doc, (
        "This work was supported by Universidad Nacional de Costa Rica through the Laboratorio "
        "de Procesamiento de Imágenes Digitales (LAPID). No grant number was provided."
    ), first_indent=False)

    heading(doc, "Conflict of Interest", level=2)
    paragraph(doc, (
        "The authors declare no known financial or personal conflicts of interest related to "
        "this work."
    ), first_indent=False)

    heading(doc, "Author Contributions", level=2)
    paragraph(doc, (
        "Johnny Villalobos Murillo and Jurgen Herrera Alfaro are co-authors and jointly "
        "contributed to the research and manuscript preparation."
    ), first_indent=False)

    heading(doc, "VII. Conclusion")
    paragraph(doc, (
        f"DART-MC preserved an image-specific threshold and achieved {pct(dart['balanced_accuracy'])}% "
        "balanced accuracy with high specificity in grouped nested internal validation on 327 "
        "INbreast images. Kapur achieved higher internal balanced accuracy, so DART-MC is not "
        "the winning method under the primary metric. The "
        "controlled comparison with fixed, histogram, entropy, minimum-error, iterative, "
        "quantile, and local thresholds nevertheless shows that the proposal is technically "
        "viable as a high-specificity alternative for continued research. The evidence remains "
        "image-level and dataset-specific. "
        "External validation with a verified patient identifier, a preregistered frozen model, "
        "and venue-compliant ethics documentation is required before clinical or patient-level "
        "claims."
    ))

    heading(doc, "References")
    refs = [
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
    for index, ref in enumerate(refs, 1):
        p = paragraph(doc, ref, size=7.2, first_indent=False, space_after=0.8)
        p.paragraph_format.left_indent = Inches(0.15)
        p.paragraph_format.first_line_indent = Inches(-0.15)
        if index == 8:
            p.add_run().add_break(WD_BREAK.COLUMN)

    for section in doc.sections:
        section.header.is_linked_to_previous = True
        section.footer.is_linked_to_previous = True
    doc.core_properties.title = "DART-MC IEEE Generic H010"
    doc.core_properties.author = "Johnny Villalobos Murillo; Jurgen Herrera Alfaro"
    doc.core_properties.subject = "Image-adaptive thresholding for INbreast classification"
    doc.core_properties.keywords = "adaptive thresholding, mammography, microcalcifications, INbreast"
    doc.save(ARTICLE)
    print(ARTICLE)


if __name__ == "__main__":
    build()
