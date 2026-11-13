// Banco v7 para una comparacion causal de reglas de umbral.
//
// Conserva sin cambios la representacion, las caracteristicas, el clasificador
// V4 y el veto V5. La unica variable experimental es la regla que convierte
// el mapa de deformacion D en candidatos primarios. La version V6 de referencia
// se incluye, no se modifica ni se sustituye.

#define INBREAST_V5_FP_SAFE_LIBRARY
#include "deform_inbreast_v6_threshold_probe.cpp"

#include <array>

static constexpr int V7_MODE_COUNT = 26;

static std::pair<double, double> masked_mean_std_v7(
    const std::vector<float>& values,
    const std::vector<uint8_t>& mask) {
    double sum = 0.0;
    double sum2 = 0.0;
    uint64_t count = 0;
    for (size_t index = 0; index < values.size(); ++index) {
        if (!mask[index]) continue;
        const double value = values[index];
        sum += value;
        sum2 += value * value;
        ++count;
    }
    if (count == 0) return {0.0, 0.0};
    const double mean = sum / static_cast<double>(count);
    const double variance = std::max(
        0.0, sum2 / static_cast<double>(count) - mean * mean);
    return {mean, std::sqrt(variance)};
}

static double masked_otsu_threshold_v7(
    const std::vector<float>& values,
    const std::vector<uint8_t>& mask) {
    constexpr size_t bins = 4096;
    std::array<uint64_t, bins> histogram{};
    uint64_t total = 0;
    double total_weighted = 0.0;
    for (size_t index = 0; index < values.size(); ++index) {
        if (!mask[index]) continue;
        const double value = std::clamp(static_cast<double>(values[index]), 0.0, 1.0);
        const size_t bin = std::min(
            bins - 1, static_cast<size_t>(value * static_cast<double>(bins - 1)));
        ++histogram[bin];
        ++total;
        total_weighted += static_cast<double>(bin);
    }
    if (total == 0) return 0.0;

    uint64_t background_count = 0;
    double background_weighted = 0.0;
    double best_variance = -1.0;
    size_t best_bin = 0;
    for (size_t bin = 0; bin < bins; ++bin) {
        background_count += histogram[bin];
        if (background_count == 0) continue;
        const uint64_t foreground_count = total - background_count;
        if (foreground_count == 0) break;
        background_weighted += static_cast<double>(bin) * histogram[bin];
        const double mean_background =
            background_weighted / static_cast<double>(background_count);
        const double mean_foreground =
            (total_weighted - background_weighted)
            / static_cast<double>(foreground_count);
        const double difference = mean_background - mean_foreground;
        const double between = static_cast<double>(background_count)
            * static_cast<double>(foreground_count) * difference * difference;
        if (between > best_variance) {
            best_variance = between;
            best_bin = bin;
        }
    }
    return static_cast<double>(best_bin) / static_cast<double>(bins - 1);
}

static double choose_v7_threshold(
    const std::vector<float>& deform,
    const std::vector<uint8_t>& mask,
    int mode) {
    static constexpr std::array<double, 9> fixed = {
        0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60,
    };
    static constexpr std::array<double, 5> quantiles = {
        0.9900, 0.9950, 0.9990, 0.9995, 0.9999,
    };
    static constexpr std::array<double, 4> k_values = {
        8.0, 12.0, 16.0, 24.0,
    };
    const auto [mean, stddev] = masked_mean_std_v7(deform, mask);
    if (mode == 0) return std::min(0.95, mean + 20.0 * stddev);
    if (mode >= 1 && mode <= 9) return fixed[static_cast<size_t>(mode - 1)];
    if (mode == 10) return masked_otsu_threshold_v7(deform, mask);
    if (mode >= 11 && mode <= 15) {
        return masked_histogram_quantile(
            deform, mask, quantiles[static_cast<size_t>(mode - 11)]);
    }
    if (mode >= 16 && mode <= 19) {
        return std::min(
            0.95, mean + k_values[static_cast<size_t>(mode - 16)] * stddev);
    }
    if (mode == 20) return choose_v6_threshold(deform, mask, 2).threshold;
    if (mode == 21) return choose_v6_threshold(deform, mask, 3).threshold;
    if (mode == 22) return choose_v6_threshold(deform, mask, 1).threshold;
    if (mode == 23) return mean + 20.0 * stddev;
    throw std::invalid_argument("modo v7 desconocido");
}

static V5ClassificationResult classify_v7_from_raw(
    const std::vector<CandidateFeature>& raw,
    const std::vector<uint8_t>& input_mask,
    uint32_t rows, uint32_t cols, float spacing,
    double threshold) {
    const auto trace = build_v4_trace(raw, spacing);
    std::vector<const V4TraceCandidate*> accepted;
    accepted.reserve(trace.size());
    for (const auto& candidate : trace) {
        if (candidate.v3_accept) accepted.push_back(&candidate);
    }

    const double mask_area_mm2 =
        static_cast<double>(count_mask(input_mask)) * spacing * spacing;
    const double safe_area = std::max(mask_area_mm2, 1e-9);
    std::array<double, inbreast_v4_model::feature_count> feature{};
    feature[0] = threshold;
    feature[1] = std::log1p(
        1000.0 * static_cast<double>(raw.size()) / safe_area);
    feature[2] = std::log1p(
        1000.0 * static_cast<double>(accepted.size()) / safe_area);
    double accepted_x_std = 0.0;
    double accepted_y_std = 0.0;
    double accepted_radial_spread = 0.0;
    double accepted_area_fraction_sum = 0.0;

    if (!accepted.empty()) {
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
        scores.reserve(accepted.size());
        std::map<uint32_t, size_t> cluster_sizes;

        for (const auto* candidate : accepted) {
            const double xn = candidate->x / std::max(1.0, static_cast<double>(cols));
            const double yn = candidate->y / std::max(1.0, static_cast<double>(rows));
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
            const double xn = candidate->x / std::max(1.0, static_cast<double>(cols));
            const double yn = candidate->y / std::max(1.0, static_cast<double>(rows));
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

        feature[3] = score_max;
        feature[4] = score_sum / count;
        feature[5] = dog_max;
        feature[6] = dog_sum / count;
        feature[7] = contrast_max;
        feature[8] = contrast_sum / count;
        feature[9] = compactness_max;
        feature[10] = compactness_sum / count;
        feature[11] = static_cast<double>(max_cluster) / count;
        feature[12] = std::log1p(static_cast<double>(cluster_sizes.size()));
        feature[13] = count / std::max(1.0, static_cast<double>(raw.size()));
        feature[14] = score_gap;
        feature[15] = x_mean;
        feature[16] = y_mean;
        feature[17] = std::sqrt(x_variance / count);
        feature[18] = std::sqrt(y_variance / count);
        accepted_x_std = feature[17];
        accepted_y_std = feature[18];
        accepted_radial_spread = std::hypot(feature[17], feature[18]);
        accepted_area_fraction_sum = area_sum / safe_area;
        feature[19] = border_sum / count;
        feature[20] = evidence_max;
        feature[21] = std::log1p(area_max);
        feature[22] = std::log1p(area_sum / count);
    }

    double logit = inbreast_v4_model::intercept;
    for (size_t index = 0; index < feature.size(); ++index) {
        const double standardized =
            (feature[index] - inbreast_v4_model::means[index])
            / inbreast_v4_model::scales[index];
        logit += inbreast_v4_model::coefficients[index] * standardized;
    }
    const double probability = stable_probability(logit);
    const bool base_predicted =
        probability >= inbreast_v4_model::decision_threshold;
    const bool vetoed = base_predicted && !accepted.empty() && (
        accepted_area_fraction_sum
            > inbreast_v5_fp_safe_model::area_fraction_sum_upper
        || accepted_y_std > inbreast_v5_fp_safe_model::y_std_upper);
    return {
        threshold,
        std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::quiet_NaN(),
        static_cast<uint64_t>(raw.size()),
        static_cast<uint64_t>(accepted.size()),
        probability,
        accepted_x_std,
        accepted_y_std,
        accepted_radial_spread,
        accepted_area_fraction_sum,
        base_predicted,
        vetoed,
        base_predicted && !vetoed,
    };
}

static V5ClassificationResult classify_v7_prepared(
    const std::vector<float>& image,
    const std::vector<uint8_t>& input_mask,
    const std::vector<uint8_t>& mask,
    const std::vector<float>& deform,
    const DogPyramid& pyramid,
    uint32_t rows, uint32_t cols, float spacing,
    int mode) {
    const double threshold = choose_v7_threshold(deform, mask, mode);
    const auto raw = extract_candidate_features_v2(
        deform, pyramid.dog, image, mask, nullptr,
        rows, cols, spacing, threshold);
    return classify_v7_from_raw(
        raw, input_mask, rows, cols, spacing, threshold);
}

struct V7LocalStats {
    std::vector<float> mean;
    std::vector<float> stddev;
};

static void box_sum_v7(
    const std::vector<float>& source,
    std::vector<float>& destination,
    uint32_t rows, uint32_t cols,
    int radius) {
    std::vector<float> horizontal(source.size(), 0.0f);
    for (uint32_t y = 0; y < rows; ++y) {
        const size_t base = static_cast<size_t>(y) * cols;
        double sum = 0.0;
        const int initial_right = std::min(
            static_cast<int>(cols) - 1, radius);
        for (int x = 0; x <= initial_right; ++x) sum += source[base + x];
        for (uint32_t x = 0; x < cols; ++x) {
            horizontal[base + x] = static_cast<float>(sum);
            const int remove_x = static_cast<int>(x) - radius;
            const int add_x = static_cast<int>(x) + radius + 1;
            if (remove_x >= 0) sum -= source[base + static_cast<size_t>(remove_x)];
            if (add_x < static_cast<int>(cols)) {
                sum += source[base + static_cast<size_t>(add_x)];
            }
        }
    }
    destination.assign(source.size(), 0.0f);
    for (uint32_t x = 0; x < cols; ++x) {
        double sum = 0.0;
        const int initial_bottom = std::min(
            static_cast<int>(rows) - 1, radius);
        for (int y = 0; y <= initial_bottom; ++y) {
            sum += horizontal[static_cast<size_t>(y) * cols + x];
        }
        for (uint32_t y = 0; y < rows; ++y) {
            destination[static_cast<size_t>(y) * cols + x] = static_cast<float>(sum);
            const int remove_y = static_cast<int>(y) - radius;
            const int add_y = static_cast<int>(y) + radius + 1;
            if (remove_y >= 0) {
                sum -= horizontal[static_cast<size_t>(remove_y) * cols + x];
            }
            if (add_y < static_cast<int>(rows)) {
                sum += horizontal[static_cast<size_t>(add_y) * cols + x];
            }
        }
    }
}

static V7LocalStats local_stats_v7(
    const std::vector<float>& deform,
    const std::vector<uint8_t>& mask,
    uint32_t rows, uint32_t cols, float spacing) {
    const int radius = std::clamp(
        static_cast<int>(std::lround(0.75 / static_cast<double>(spacing))),
        3, 30);

    std::vector<float> weighted(deform.size(), 0.0f);
    for (size_t index = 0; index < deform.size(); ++index) {
        if (mask[index]) weighted[index] = deform[index];
    }
    std::vector<float> mean_numerator;
    box_sum_v7(weighted, mean_numerator, rows, cols, radius);

    for (size_t index = 0; index < deform.size(); ++index) {
        weighted[index] = mask[index] ? deform[index] * deform[index] : 0.0f;
    }
    std::vector<float> square_numerator;
    box_sum_v7(weighted, square_numerator, rows, cols, radius);

    for (size_t index = 0; index < deform.size(); ++index) {
        weighted[index] = mask[index] ? 1.0f : 0.0f;
    }
    std::vector<float> weight;
    box_sum_v7(weighted, weight, rows, cols, radius);
    std::vector<float>().swap(weighted);

    V7LocalStats result;
    result.mean.resize(deform.size(), 0.0f);
    result.stddev.resize(deform.size(), 0.0f);
    for (size_t index = 0; index < deform.size(); ++index) {
        if (!mask[index]) continue;
        const double safe_weight = std::max(1e-6, static_cast<double>(weight[index]));
        const double mean = mean_numerator[index] / safe_weight;
        const double second = square_numerator[index] / safe_weight;
        result.mean[index] = static_cast<float>(mean);
        result.stddev[index] = static_cast<float>(
            std::sqrt(std::max(0.0, second - mean * mean)));
    }
    return result;
}

static V5ClassificationResult classify_v7_local_prepared(
    const std::vector<float>& image,
    const std::vector<uint8_t>& input_mask,
    const std::vector<uint8_t>& mask,
    const std::vector<float>& deform,
    const DogPyramid& pyramid,
    const V7LocalStats& stats,
    uint32_t rows, uint32_t cols, float spacing,
    int mode) {
    constexpr double sauvola_r = 0.5;
    std::vector<float> binary_score(deform.size(), 0.0f);
    double threshold_sum = 0.0;
    uint64_t threshold_count = 0;
    for (size_t index = 0; index < deform.size(); ++index) {
        if (!mask[index]) continue;
        double threshold = 0.0;
        if (mode == 24) {
            constexpr double k = 1.0;
            threshold = stats.mean[index] + k * stats.stddev[index];
        } else if (mode == 25) {
            constexpr double k = 0.5;
            threshold = stats.mean[index]
                * (1.0 + k * (stats.stddev[index] / sauvola_r - 1.0));
        } else {
            throw std::invalid_argument("modo local v7 desconocido");
        }
        threshold = std::clamp(threshold, 0.0, 1.0);
        threshold_sum += threshold;
        ++threshold_count;
        binary_score[index] = deform[index] > threshold ? 1.0f : 0.0f;
    }
    const double effective_threshold = threshold_count
        ? threshold_sum / static_cast<double>(threshold_count) : 0.0;
    const auto raw = extract_candidate_features_v2(
        binary_score, pyramid.dog, image, mask, nullptr,
        rows, cols, spacing, 0.5);
    return classify_v7_from_raw(
        raw, input_mask, rows, cols, spacing, effective_threshold);
}

#if defined(_WIN32)
#define INBREAST_V7_EXPORT extern "C" __declspec(dllexport)
#else
#define INBREAST_V7_EXPORT extern "C"
#endif

INBREAST_V7_EXPORT int classify_inbreast_v7_threshold_benchmark_all(
    const float* image, uint64_t image_len,
    const uint8_t* mask, uint64_t mask_len,
    uint32_t rows, uint32_t cols, float spacing,
    double* thresholds, uint64_t* raw, uint64_t* accepted,
    double* probabilities, int* base_predicted,
    int* vetoed, int* predicted,
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
    if (image_len < count || mask_len < count) {
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
        for (int mode = 0; mode < 24; ++mode) {
            const auto result = classify_v7_prepared(
                normalized, input_mask, analysis_mask, deform, pyramid,
                rows, cols, spacing, mode);
            if (thresholds) thresholds[mode] = result.adaptive_threshold;
            if (raw) raw[mode] = result.raw_candidates;
            if (accepted) accepted[mode] = result.accepted_candidates;
            if (probabilities) probabilities[mode] = result.probability;
            if (base_predicted) {
                base_predicted[mode] = result.base_predicted ? 1 : 0;
            }
            if (vetoed) vetoed[mode] = result.vetoed ? 1 : 0;
            if (predicted) predicted[mode] = result.predicted ? 1 : 0;
        }
        const auto local_stats = local_stats_v7(
            deform, analysis_mask, rows, cols, spacing);
        for (int mode = 24; mode < V7_MODE_COUNT; ++mode) {
            const auto result = classify_v7_local_prepared(
                normalized, input_mask, analysis_mask, deform, pyramid,
                local_stats, rows, cols, spacing, mode);
            if (thresholds) thresholds[mode] = result.adaptive_threshold;
            if (raw) raw[mode] = result.raw_candidates;
            if (accepted) accepted[mode] = result.accepted_candidates;
            if (probabilities) probabilities[mode] = result.probability;
            if (base_predicted) {
                base_predicted[mode] = result.base_predicted ? 1 : 0;
            }
            if (vetoed) vetoed[mode] = result.vetoed ? 1 : 0;
            if (predicted) predicted[mode] = result.predicted ? 1 : 0;
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
