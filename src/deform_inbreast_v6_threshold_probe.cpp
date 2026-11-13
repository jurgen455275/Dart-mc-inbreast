// Sonda experimental v6 para estudiar parametros adaptativos por imagen.
// Es una copia separada: no modifica ni sustituye v5.

#define INBREAST_V4_LIBRARY
#include "deform_inbreast_v4_adaptive.cpp"
#include "v4_classifier_model.h"
#include "v5_fp_safe_model.h"

#include <array>
#include <map>

struct V6ThresholdChoice {
    double threshold{};
    double effective_k{};
    double effective_cap{};
};

static double masked_histogram_quantile(
    const std::vector<float>& values,
    const std::vector<uint8_t>& mask,
    double probability) {
    constexpr size_t bins = 65536;
    std::array<uint64_t, bins> histogram{};
    uint64_t count = 0;
    for (size_t index = 0; index < values.size(); ++index) {
        if (!mask[index]) continue;
        const double value = std::clamp(static_cast<double>(values[index]), 0.0, 1.0);
        const size_t bin = std::min(
            bins - 1, static_cast<size_t>(value * static_cast<double>(bins - 1)));
        ++histogram[bin];
        ++count;
    }
    if (count == 0) return 0.0;
    const uint64_t target = static_cast<uint64_t>(
        std::floor(std::clamp(probability, 0.0, 1.0) * static_cast<double>(count - 1)));
    uint64_t cumulative = 0;
    for (size_t bin = 0; bin < bins; ++bin) {
        cumulative += histogram[bin];
        if (cumulative > target) {
            return static_cast<double>(bin) / static_cast<double>(bins - 1);
        }
    }
    return 1.0;
}

static V6ThresholdChoice choose_v6_threshold(
    const std::vector<float>& deform,
    const std::vector<uint8_t>& mask,
    int mode) {
    double sum = 0.0, sum2 = 0.0;
    uint64_t count = 0;
    for (size_t index = 0; index < deform.size(); ++index) {
        if (!mask[index]) continue;
        const double value = deform[index];
        sum += value;
        sum2 += value * value;
        ++count;
    }
    const double mean = count ? sum / static_cast<double>(count) : 0.0;
    const double stddev = count
        ? std::sqrt(std::max(0.0, sum2 / static_cast<double>(count) - mean * mean))
        : 0.0;
    const double original_uncapped = mean + 20.0 * stddev;

    if (mode == 0) {
        return {std::min(0.95, original_uncapped), 20.0, 0.95};
    }
    if (mode == 1) {
        const double quantile = masked_histogram_quantile(deform, mask, 0.999);
        const double k = stddev > 1e-12 ? (quantile - mean) / stddev : 20.0;
        return {std::min(0.95, mean + k * stddev), k, 0.95};
    }
    if (mode == 2) {
        const double cap = original_uncapped > 0.95
            ? masked_histogram_quantile(deform, mask, 0.9999)
            : 0.95;
        return {std::min(cap, original_uncapped), 20.0, cap};
    }
    if (mode == 3) {
        const double probability = count > 0
            ? 1.0 - std::clamp(
                1.0 / std::sqrt(static_cast<double>(count)), 0.0001, 0.005)
            : 0.999;
        const double quantile = masked_histogram_quantile(deform, mask, probability);
        const double k = stddev > 1e-12 ? (quantile - mean) / stddev : 20.0;
        return {std::min(0.95, mean + k * stddev), k, 0.95};
    }
    throw std::invalid_argument("modo v6 desconocido");
}

struct V5ClassificationResult {
    double adaptive_threshold{};
    double effective_k{};
    double effective_cap{};
    uint64_t raw_candidates{};
    uint64_t accepted_candidates{};
    double probability{};
    double accepted_x_std{};
    double accepted_y_std{};
    double accepted_radial_spread{};
    double accepted_area_fraction_sum{};
    bool base_predicted{};
    bool vetoed{};
    bool predicted{};
};

static double stable_probability(double value) {
    if (value >= 0.0) {
        const double z = std::exp(-value);
        return 1.0 / (1.0 + z);
    }
    const double z = std::exp(value);
    return z / (1.0 + z);
}

template <typename PyramidType>
static V5ClassificationResult classify_v6_prepared(
    const std::vector<float>& image,
    const std::vector<uint8_t>& input_mask,
    const std::vector<uint8_t>& mask,
    const std::vector<float>& deform,
    const PyramidType& pyramid,
    uint32_t rows, uint32_t cols, float spacing, int threshold_mode) {
    const auto threshold_choice = choose_v6_threshold(deform, mask, threshold_mode);
    const double threshold = threshold_choice.threshold;
    const auto raw = extract_candidate_features_v2(
        deform, pyramid.dog, image, mask, nullptr,
        rows, cols, spacing, threshold);
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
        double x_sum = 0.0, y_sum = 0.0;
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
        double x_variance = 0.0, y_variance = 0.0;
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
    for (size_t i = 0; i < feature.size(); ++i) {
        const double standardized =
            (feature[i] - inbreast_v4_model::means[i])
            / inbreast_v4_model::scales[i];
        logit += inbreast_v4_model::coefficients[i] * standardized;
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
        threshold_choice.effective_k,
        threshold_choice.effective_cap,
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

static V5ClassificationResult classify_v6_probe_image(
    const std::vector<float>& input_image,
    const std::vector<uint8_t>& input_mask,
    uint32_t rows, uint32_t cols, float spacing, int threshold_mode) {
    const auto image = robust_renormalize(input_image, input_mask);
    const auto mask = analysis_mask_physical(input_mask, rows, cols, spacing);
    const auto deform = deformation_map(image, rows, cols);
    const auto pyramid = physical_dog_pyramid(image, rows, cols, spacing);
    return classify_v6_prepared(
        image, input_mask, mask, deform, pyramid,
        rows, cols, spacing, threshold_mode);
}

#if defined(_WIN32)
#define INBREAST_V5_CLASS_EXPORT extern "C" __declspec(dllexport)
#else
#define INBREAST_V5_CLASS_EXPORT extern "C"
#endif

INBREAST_V5_CLASS_EXPORT int classify_inbreast_v6_threshold_probe_all(
    const float* image, uint64_t image_len,
    const uint8_t* mask, uint64_t mask_len,
    uint32_t rows, uint32_t cols, float spacing,
    double* thresholds4, double* effective_k4, double* effective_cap4,
    uint64_t* raw4, uint64_t* accepted4, double* probabilities4,
    int* base_predicted4, int* vetoed4, int* predicted4,
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
    const size_t n = static_cast<size_t>(rows) * cols;
    if (image_len < n || mask_len < n) {
        if (quality_code) *quality_code = 2;
        return 2;
    }
    if (!finite_image_inside_mask(image, mask, n)
        || !safe_float_range_inside_mask(image, mask, n)) {
        if (quality_code) *quality_code = 3;
        return 3;
    }
    try {
        const auto start = std::chrono::steady_clock::now();
        const std::vector<float> input_image(image, image + n);
        const std::vector<uint8_t> input_mask(mask, mask + n);
        const auto normalized = robust_renormalize(input_image, input_mask);
        const auto analysis_mask = analysis_mask_physical(input_mask, rows, cols, spacing);
        const auto deform = deformation_map(normalized, rows, cols);
        const auto pyramid = physical_dog_pyramid(normalized, rows, cols, spacing);
        for (int mode = 0; mode < 4; ++mode) {
            const auto result = classify_v6_prepared(
                normalized, input_mask, analysis_mask, deform, pyramid,
                rows, cols, spacing, mode);
            if (thresholds4) thresholds4[mode] = result.adaptive_threshold;
            if (effective_k4) effective_k4[mode] = result.effective_k;
            if (effective_cap4) effective_cap4[mode] = result.effective_cap;
            if (raw4) raw4[mode] = result.raw_candidates;
            if (accepted4) accepted4[mode] = result.accepted_candidates;
            if (probabilities4) probabilities4[mode] = result.probability;
            if (base_predicted4) base_predicted4[mode] = result.base_predicted ? 1 : 0;
            if (vetoed4) vetoed4[mode] = result.vetoed ? 1 : 0;
            if (predicted4) predicted4[mode] = result.predicted ? 1 : 0;
        }
        const auto finish = std::chrono::steady_clock::now();
        if (time_ms) {
            *time_ms = std::chrono::duration<double, std::milli>(finish - start).count();
        }
        return 0;
    } catch (...) {
        if (quality_code) *quality_code = 1;
        return 1;
    }
}

INBREAST_V5_CLASS_EXPORT int classify_inbreast_v6_threshold_probe(
    const float* image, uint64_t image_len,
    const uint8_t* mask, uint64_t mask_len,
    uint32_t rows, uint32_t cols, float spacing, int threshold_mode,
    double* adaptive_threshold,
    double* effective_k, double* effective_cap,
    uint64_t* raw_candidates, uint64_t* accepted_candidates,
    double* probability,
    double* accepted_x_std, double* accepted_y_std,
    double* accepted_radial_spread, double* accepted_area_fraction_sum,
    int* base_predicted, int* vetoed, int* predicted,
    int* quality_code, double* time_ms) {
    if (adaptive_threshold) *adaptive_threshold = std::numeric_limits<double>::quiet_NaN();
    if (effective_k) *effective_k = std::numeric_limits<double>::quiet_NaN();
    if (effective_cap) *effective_cap = std::numeric_limits<double>::quiet_NaN();
    if (raw_candidates) *raw_candidates = 0;
    if (accepted_candidates) *accepted_candidates = 0;
    if (probability) *probability = std::numeric_limits<double>::quiet_NaN();
    if (accepted_x_std) *accepted_x_std = 0.0;
    if (accepted_y_std) *accepted_y_std = 0.0;
    if (accepted_radial_spread) *accepted_radial_spread = 0.0;
    if (accepted_area_fraction_sum) *accepted_area_fraction_sum = 0.0;
    if (base_predicted) *base_predicted = 0;
    if (vetoed) *vetoed = 0;
    if (predicted) *predicted = 0;
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
    const size_t n = static_cast<size_t>(rows) * cols;
    if (image_len < n || mask_len < n) {
        if (quality_code) *quality_code = 2;
        return 2;
    }
    if (!finite_image_inside_mask(image, mask, n)
        || !safe_float_range_inside_mask(image, mask, n)) {
        if (quality_code) *quality_code = 3;
        return 3;
    }

    try {
        const auto start = std::chrono::steady_clock::now();
        const std::vector<float> image_v(image, image + n);
        const std::vector<uint8_t> mask_v(mask, mask + n);
        const auto result = classify_v6_probe_image(
            image_v, mask_v, rows, cols, spacing, threshold_mode);
        const auto finish = std::chrono::steady_clock::now();
        if (adaptive_threshold) *adaptive_threshold = result.adaptive_threshold;
        if (effective_k) *effective_k = result.effective_k;
        if (effective_cap) *effective_cap = result.effective_cap;
        if (raw_candidates) *raw_candidates = result.raw_candidates;
        if (accepted_candidates) *accepted_candidates = result.accepted_candidates;
        if (probability) *probability = result.probability;
        if (accepted_x_std) *accepted_x_std = result.accepted_x_std;
        if (accepted_y_std) *accepted_y_std = result.accepted_y_std;
        if (accepted_radial_spread) {
            *accepted_radial_spread = result.accepted_radial_spread;
        }
        if (accepted_area_fraction_sum) {
            *accepted_area_fraction_sum = result.accepted_area_fraction_sum;
        }
        if (base_predicted) *base_predicted = result.base_predicted ? 1 : 0;
        if (vetoed) *vetoed = result.vetoed ? 1 : 0;
        if (predicted) *predicted = result.predicted ? 1 : 0;
        if (time_ms) {
            *time_ms = std::chrono::duration<double, std::milli>(finish - start).count();
        }
        return 0;
    } catch (...) {
        if (quality_code) *quality_code = 1;
        return 1;
    }
}

#ifndef INBREAST_V5_FP_SAFE_LIBRARY
int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Uso: deform_inbreast_v5_fp_safe <archivo.inbr> [archivo.inbr ...]\n";
        return 2;
    }
    std::cout << "archivo,umbral_adaptativo,raw,aceptados,probabilidad,x_std,y_std,dispersion_radial,fraccion_area_total,base_v4,veto_v5,positiva_v5\n";
    for (int argument = 1; argument < argc; ++argument) {
        try {
            const InputImage input = read_input(argv[argument]);
            const auto result = classify_v5_image(
                input.image, input.breast_mask,
                input.rows, input.cols, input.spacing);
            std::cout << std::filesystem::path(argv[argument]).filename().string()
                      << ',' << std::setprecision(12) << result.adaptive_threshold
                      << ',' << result.raw_candidates
                      << ',' << result.accepted_candidates
                      << ',' << result.probability
                      << ',' << result.accepted_x_std
                      << ',' << result.accepted_y_std
                      << ',' << result.accepted_radial_spread
                      << ',' << result.accepted_area_fraction_sum
                      << ',' << (result.base_predicted ? 1 : 0)
                      << ',' << (result.vetoed ? 1 : 0)
                      << ',' << (result.predicted ? 1 : 0) << '\n';
        } catch (const std::exception& error) {
            std::cerr << "ERROR," << argv[argument] << ',' << error.what() << '\n';
            return 1;
        }
    }
    return 0;
}
#endif
