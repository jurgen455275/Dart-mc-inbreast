// H010: exportacion de caracteristicas para comparar reglas de umbral.
//
// El archivo V7 se incluye sin modificar. DART-MC conserva exactamente
// T=min(0.95, mean_M(D)+20*std_M(D)) y la comparacion estricta D>T.
// H010 agrega tres controles globales (Kapur, Kittler-Illingworth y
// Ridler-Calvard) y exporta las mismas 23 caracteristicas por imagen y metodo.

#include "deform_inbreast_v7_threshold_benchmark.cpp"

static constexpr int H010_MODE_COUNT = 29;
static constexpr int H010_FEATURE_COUNT = 23;

static std::array<uint64_t, 4096> masked_histogram_h010(
    const std::vector<float>& values,
    const std::vector<uint8_t>& mask) {
    std::array<uint64_t, 4096> histogram{};
    for (size_t index = 0; index < values.size(); ++index) {
        if (!mask[index]) continue;
        const double value = std::clamp(
            static_cast<double>(values[index]), 0.0, 1.0);
        const size_t bin = std::min(
            histogram.size() - 1,
            static_cast<size_t>(value * (histogram.size() - 1)));
        ++histogram[bin];
    }
    return histogram;
}

static double kapur_threshold_h010(
    const std::vector<float>& values,
    const std::vector<uint8_t>& mask) {
    const auto histogram = masked_histogram_h010(values, mask);
    const double total = static_cast<double>(std::accumulate(
        histogram.begin(), histogram.end(), uint64_t{0}));
    if (total <= 0.0) return 0.0;
    std::array<double, 4096> cumulative_probability{};
    std::array<double, 4096> cumulative_plogp{};
    double probability = 0.0;
    double plogp = 0.0;
    for (size_t bin = 0; bin < histogram.size(); ++bin) {
        const double p = static_cast<double>(histogram[bin]) / total;
        probability += p;
        if (p > 0.0) plogp += p * std::log(p);
        cumulative_probability[bin] = probability;
        cumulative_plogp[bin] = plogp;
    }
    const double total_plogp = cumulative_plogp.back();
    double best_score = -std::numeric_limits<double>::infinity();
    size_t best_bin = 0;
    for (size_t bin = 0; bin + 1 < histogram.size(); ++bin) {
        const double p0 = cumulative_probability[bin];
        const double p1 = 1.0 - p0;
        if (p0 <= 1e-12 || p1 <= 1e-12) continue;
        const double h0 = std::log(p0) - cumulative_plogp[bin] / p0;
        const double h1 = std::log(p1)
            - (total_plogp - cumulative_plogp[bin]) / p1;
        const double score = h0 + h1;
        if (score > best_score) {
            best_score = score;
            best_bin = bin;
        }
    }
    return static_cast<double>(best_bin) /
        static_cast<double>(histogram.size() - 1);
}

static double kittler_threshold_h010(
    const std::vector<float>& values,
    const std::vector<uint8_t>& mask) {
    const auto histogram = masked_histogram_h010(values, mask);
    const double total = static_cast<double>(std::accumulate(
        histogram.begin(), histogram.end(), uint64_t{0}));
    if (total <= 0.0) return 0.0;
    double total_m1 = 0.0;
    double total_m2 = 0.0;
    for (size_t bin = 0; bin < histogram.size(); ++bin) {
        const double x = static_cast<double>(bin) /
            static_cast<double>(histogram.size() - 1);
        total_m1 += static_cast<double>(histogram[bin]) * x;
        total_m2 += static_cast<double>(histogram[bin]) * x * x;
    }
    double count0 = 0.0;
    double m10 = 0.0;
    double m20 = 0.0;
    double best = std::numeric_limits<double>::infinity();
    size_t best_bin = 0;
    for (size_t bin = 0; bin + 1 < histogram.size(); ++bin) {
        const double x = static_cast<double>(bin) /
            static_cast<double>(histogram.size() - 1);
        const double count = static_cast<double>(histogram[bin]);
        count0 += count;
        m10 += count * x;
        m20 += count * x * x;
        const double count1 = total - count0;
        if (count0 <= 0.0 || count1 <= 0.0) continue;
        const double p0 = count0 / total;
        const double p1 = count1 / total;
        const double mean0 = m10 / count0;
        const double mean1 = (total_m1 - m10) / count1;
        const double variance0 = m20 / count0 - mean0 * mean0;
        const double variance1 = (total_m2 - m20) / count1 - mean1 * mean1;
        if (variance0 <= 1e-12 || variance1 <= 1e-12) continue;
        const double criterion = 1.0
            + p0 * std::log(variance0)
            + p1 * std::log(variance1)
            - 2.0 * (p0 * std::log(p0) + p1 * std::log(p1));
        if (criterion < best) {
            best = criterion;
            best_bin = bin;
        }
    }
    return static_cast<double>(best_bin) /
        static_cast<double>(histogram.size() - 1);
}

static double ridler_calvard_threshold_h010(
    const std::vector<float>& values,
    const std::vector<uint8_t>& mask) {
    const auto [global_mean, ignored_std] = masked_mean_std_v7(values, mask);
    (void)ignored_std;
    double threshold = global_mean;
    for (int iteration = 0; iteration < 100; ++iteration) {
        double low_sum = 0.0;
        double high_sum = 0.0;
        uint64_t low_count = 0;
        uint64_t high_count = 0;
        for (size_t index = 0; index < values.size(); ++index) {
            if (!mask[index]) continue;
            const double value = values[index];
            if (value <= threshold) {
                low_sum += value;
                ++low_count;
            } else {
                high_sum += value;
                ++high_count;
            }
        }
        if (!low_count || !high_count) break;
        const double updated = 0.5 * (
            low_sum / static_cast<double>(low_count)
            + high_sum / static_cast<double>(high_count));
        if (std::abs(updated - threshold) < 1e-7) {
            threshold = updated;
            break;
        }
        threshold = updated;
    }
    return std::clamp(threshold, 0.0, 1.0);
}

static double choose_h010_threshold(
    const std::vector<float>& deform,
    const std::vector<uint8_t>& mask,
    int mode) {
    if (mode < 24) return choose_v7_threshold(deform, mask, mode);
    if (mode == 26) return kapur_threshold_h010(deform, mask);
    if (mode == 27) return kittler_threshold_h010(deform, mask);
    if (mode == 28) return ridler_calvard_threshold_h010(deform, mask);
    throw std::invalid_argument("modo global H010 desconocido");
}

static void aggregate_features_h010(
    const std::vector<CandidateFeature>& raw,
    const std::vector<uint8_t>& input_mask,
    uint32_t rows, uint32_t cols, float spacing,
    double threshold,
    double* output) {
    std::fill(output, output + H010_FEATURE_COUNT, 0.0);
    const auto trace = build_v4_trace(raw, spacing);
    std::vector<const V4TraceCandidate*> accepted;
    accepted.reserve(trace.size());
    for (const auto& candidate : trace) {
        if (candidate.v3_accept) accepted.push_back(&candidate);
    }
    const double mask_area_mm2 =
        static_cast<double>(count_mask(input_mask)) * spacing * spacing;
    const double safe_area = std::max(mask_area_mm2, 1e-9);
    output[0] = threshold;
    output[1] = std::log1p(
        1000.0 * static_cast<double>(raw.size()) / safe_area);
    output[2] = std::log1p(
        1000.0 * static_cast<double>(accepted.size()) / safe_area);
    if (accepted.empty()) return;

    double score_sum = 0.0;
    double dog_sum = 0.0;
    double contrast_sum = 0.0;
    double compactness_sum = 0.0;
    double x_sum = 0.0;
    double y_sum = 0.0;
    double border_sum = 0.0;
    double area_sum = 0.0;
    double score_max = -std::numeric_limits<double>::infinity();
    double dog_max = -std::numeric_limits<double>::infinity();
    double contrast_max = -std::numeric_limits<double>::infinity();
    double compactness_max = -std::numeric_limits<double>::infinity();
    double evidence_max = -std::numeric_limits<double>::infinity();
    double area_max = 0.0;
    std::vector<double> scores;
    std::map<uint32_t, size_t> cluster_sizes;
    for (const auto* candidate : accepted) {
        const double xn = candidate->x /
            std::max(1.0, static_cast<double>(cols));
        const double yn = candidate->y /
            std::max(1.0, static_cast<double>(rows));
        const double border = std::min({xn, 1.0 - xn, yn, 1.0 - yn});
        score_sum += candidate->legacy_score;
        dog_sum += candidate->dog_z;
        contrast_sum += candidate->local_contrast_z;
        compactness_sum += candidate->compactness;
        x_sum += xn;
        y_sum += yn;
        border_sum += border;
        area_sum += candidate->area_mm2;
        score_max = std::max(score_max, candidate->legacy_score);
        dog_max = std::max(dog_max, candidate->dog_z);
        contrast_max = std::max(contrast_max, candidate->local_contrast_z);
        compactness_max = std::max(compactness_max, candidate->compactness);
        evidence_max = std::max(evidence_max, candidate->evidence);
        area_max = std::max(area_max, candidate->area_mm2);
        scores.push_back(candidate->legacy_score);
        ++cluster_sizes[candidate->cluster_id];
    }
    const double count = static_cast<double>(accepted.size());
    const double x_mean = x_sum / count;
    const double y_mean = y_sum / count;
    double x_variance = 0.0;
    double y_variance = 0.0;
    for (const auto* candidate : accepted) {
        const double xn = candidate->x /
            std::max(1.0, static_cast<double>(cols));
        const double yn = candidate->y /
            std::max(1.0, static_cast<double>(rows));
        x_variance += (xn - x_mean) * (xn - x_mean);
        y_variance += (yn - y_mean) * (yn - y_mean);
    }
    std::sort(scores.begin(), scores.end(), std::greater<double>());
    const double score_gap = scores.size() > 1
        ? scores[0] - scores[1] : scores[0];
    size_t max_cluster = 0;
    for (const auto& item : cluster_sizes) {
        max_cluster = std::max(max_cluster, item.second);
    }
    output[3] = score_max;
    output[4] = score_sum / count;
    output[5] = dog_max;
    output[6] = dog_sum / count;
    output[7] = contrast_max;
    output[8] = contrast_sum / count;
    output[9] = compactness_max;
    output[10] = compactness_sum / count;
    output[11] = static_cast<double>(max_cluster) / count;
    output[12] = std::log1p(static_cast<double>(cluster_sizes.size()));
    output[13] = count / std::max(1.0, static_cast<double>(raw.size()));
    output[14] = score_gap;
    output[15] = x_mean;
    output[16] = y_mean;
    output[17] = std::sqrt(x_variance / count);
    output[18] = std::sqrt(y_variance / count);
    output[19] = border_sum / count;
    output[20] = evidence_max;
    output[21] = std::log1p(area_max);
    output[22] = std::log1p(area_sum / count);
}

INBREAST_V7_EXPORT int extract_inbreast_h010_threshold_features(
    const float* image, uint64_t image_len,
    const uint8_t* mask, uint64_t mask_len,
    uint32_t rows, uint32_t cols, float spacing,
    double* thresholds, uint64_t* raw_counts, uint64_t* accepted_counts,
    double* features, uint64_t features_len,
    int* quality_code, double* time_ms) {
    if (quality_code) *quality_code = 0;
    if (time_ms) *time_ms = 0.0;
    if (!image || !mask || rows == 0 || cols == 0
        || !std::isfinite(static_cast<double>(spacing)) || spacing <= 0.0f) {
        if (quality_code) *quality_code = 2;
        return 2;
    }
    if (static_cast<size_t>(rows) > std::numeric_limits<size_t>::max() / cols) {
        if (quality_code) *quality_code = 2;
        return 2;
    }
    const size_t count = static_cast<size_t>(rows) * cols;
    if (image_len < count || mask_len < count
        || (features && features_len < H010_MODE_COUNT * H010_FEATURE_COUNT)) {
        if (quality_code) *quality_code = 2;
        return 2;
    }
    if (!finite_image_inside_mask(image, mask, count)
        || !safe_float_range_inside_mask(image, mask, count)) {
        if (quality_code) *quality_code = 3;
        return 3;
    }
    try {
        const auto start = std::chrono::steady_clock::now();
        const std::vector<float> input_image(image, image + count);
        const std::vector<uint8_t> input_mask(mask, mask + count);
        const auto normalized = robust_renormalize(input_image, input_mask);
        const auto analysis_mask =
            analysis_mask_physical(input_mask, rows, cols, spacing);
        const auto deform = deformation_map(normalized, rows, cols);
        const auto pyramid = physical_dog_pyramid(
            normalized, rows, cols, spacing);
        const auto local_stats = local_stats_v7(
            deform, analysis_mask, rows, cols, spacing);

        for (int mode = 0; mode < H010_MODE_COUNT; ++mode) {
            double threshold = 0.0;
            std::vector<CandidateFeature> raw;
            if (mode == 24 || mode == 25) {
                constexpr double sauvola_r = 0.5;
                std::vector<float> binary_score(deform.size(), 0.0f);
                double threshold_sum = 0.0;
                uint64_t threshold_count = 0;
                for (size_t index = 0; index < deform.size(); ++index) {
                    if (!analysis_mask[index]) continue;
                    double local_threshold = 0.0;
                    if (mode == 24) {
                        local_threshold = local_stats.mean[index]
                            + local_stats.stddev[index];
                    } else {
                        local_threshold = local_stats.mean[index] * (
                            1.0 + 0.5 * (
                                local_stats.stddev[index] / sauvola_r - 1.0));
                    }
                    local_threshold = std::clamp(local_threshold, 0.0, 1.0);
                    threshold_sum += local_threshold;
                    ++threshold_count;
                    binary_score[index] =
                        deform[index] > local_threshold ? 1.0f : 0.0f;
                }
                threshold = threshold_count
                    ? threshold_sum / static_cast<double>(threshold_count) : 0.0;
                raw = extract_candidate_features_v2(
                    binary_score, pyramid.dog, normalized, analysis_mask, nullptr,
                    rows, cols, spacing, 0.5);
            } else {
                threshold = choose_h010_threshold(deform, analysis_mask, mode);
                raw = extract_candidate_features_v2(
                    deform, pyramid.dog, normalized, analysis_mask, nullptr,
                    rows, cols, spacing, threshold);
            }
            const auto trace = build_v4_trace(raw, spacing);
            uint64_t accepted = 0;
            for (const auto& candidate : trace) {
                if (candidate.v3_accept) ++accepted;
            }
            if (thresholds) thresholds[mode] = threshold;
            if (raw_counts) raw_counts[mode] = raw.size();
            if (accepted_counts) accepted_counts[mode] = accepted;
            if (features) {
                aggregate_features_h010(
                    raw, analysis_mask, rows, cols, spacing, threshold,
                    features + mode * H010_FEATURE_COUNT);
            }
        }
        const auto finish = std::chrono::steady_clock::now();
        if (time_ms) {
            *time_ms = std::chrono::duration<double, std::milli>(
                finish - start).count();
        }
        return 0;
    } catch (...) {
        if (quality_code) *quality_code = 1;
        return 1;
    }
}

INBREAST_V7_EXPORT int inbreast_h010_mode_count() {
    return H010_MODE_COUNT;
}

INBREAST_V7_EXPORT int inbreast_h010_feature_count() {
    return H010_FEATURE_COUNT;
}
