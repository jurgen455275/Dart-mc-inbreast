// Variante experimental v4: instrumentacion sin cambiar el nucleo adaptativo.
// No sustituye versiones anteriores. La inferencia no recibe ground truth.
//
// Invariante cientifico conservado:
//   T = min(0.95, media_M(D) + 20 * desviacion_M(D))
//   seleccion primaria estricta: D > T
//
// La v4 exporta evidencia candidato a candidato para que el matching y la
// evaluacion se realicen fuera del detector.

#define INBREAST_V3_LIBRARY
#include "deform_inbreast_v3_locked.cpp"

#include <numeric>

static bool safe_float_range_inside_mask(
    const float* image, const uint8_t* mask, size_t n) {
    double minimum = std::numeric_limits<double>::infinity();
    double maximum = -std::numeric_limits<double>::infinity();
    for (size_t p = 0; p < n; ++p) {
        if (!mask[p]) continue;
        const double value = static_cast<double>(image[p]);
        minimum = std::min(minimum, value);
        maximum = std::max(maximum, value);
    }
    return std::isfinite(minimum) && std::isfinite(maximum)
        && maximum - minimum <= static_cast<double>(std::numeric_limits<float>::max());
}

struct V4TraceCandidate {
    double x{};
    double y{};
    double area_mm2{};
    double compactness{};
    double local_contrast_z{};
    double dog_z{};
    double legacy_score{};
    double contrast_rank{};
    double dog_rank{};
    double compactness_rank{};
    double evidence{};
    uint32_t cluster_id{};
    int strict_accept{};
    int v3_accept{};
    int adaptive_accept{};
    int rejection_stage{};
};

static double percentile_double(std::vector<double> values, double q) {
    if (values.empty()) return 0.0;
    q = std::clamp(q, 0.0, 1.0);
    const double position = q * static_cast<double>(values.size() - 1);
    const size_t lo = static_cast<size_t>(std::floor(position));
    const size_t hi = static_cast<size_t>(std::ceil(position));
    std::nth_element(values.begin(), values.begin() + lo, values.end());
    const double a = values[lo];
    if (lo == hi) return a;
    std::nth_element(values.begin(), values.begin() + hi, values.end());
    return a + (values[hi] - a) * (position - static_cast<double>(lo));
}

static std::vector<double> empirical_ranks(const std::vector<double>& values) {
    std::vector<double> ranks(values.size(), 1.0);
    if (values.size() <= 1) return ranks;
    std::vector<std::pair<double, size_t>> ordered;
    ordered.reserve(values.size());
    for (size_t i = 0; i < values.size(); ++i) ordered.emplace_back(values[i], i);
    std::stable_sort(ordered.begin(), ordered.end(),
        [](const auto& a, const auto& b) { return a.first < b.first; });
    size_t begin = 0;
    while (begin < ordered.size()) {
        size_t end = begin + 1;
        while (end < ordered.size() && ordered[end].first == ordered[begin].first) ++end;
        const double rank = ordered.size() == 1
            ? 1.0
            : static_cast<double>(end - 1) / static_cast<double>(ordered.size() - 1);
        for (size_t p = begin; p < end; ++p) ranks[ordered[p].second] = rank;
        begin = end;
    }
    return ranks;
}

static std::vector<uint32_t> raw_cluster_ids(
    const std::vector<CandidateFeature>& candidates, float spacing) {
    std::vector<uint32_t> ids(candidates.size(), 0);
    if (candidates.empty()) return ids;
    const double radius_px = 5.0 / std::max(0.01f, spacing);
    const double radius2 = radius_px * radius_px;
    std::vector<uint8_t> seen(candidates.size(), 0);
    std::vector<size_t> stack;
    uint32_t cluster = 0;
    for (size_t start = 0; start < candidates.size(); ++start) {
        if (seen[start]) continue;
        ++cluster;
        seen[start] = 1;
        stack.clear();
        stack.push_back(start);
        while (!stack.empty()) {
            const size_t current = stack.back();
            stack.pop_back();
            ids[current] = cluster;
            for (size_t other = 0; other < candidates.size(); ++other) {
                if (seen[other]) continue;
                const double dx = candidates[current].x - candidates[other].x;
                const double dy = candidates[current].y - candidates[other].y;
                if (dx * dx + dy * dy <= radius2) {
                    seen[other] = 1;
                    stack.push_back(other);
                }
            }
        }
    }
    return ids;
}

static std::vector<V4TraceCandidate> build_v4_trace(
    const std::vector<CandidateFeature>& raw, float spacing) {
    std::vector<double> contrast, dog, compactness;
    contrast.reserve(raw.size());
    dog.reserve(raw.size());
    compactness.reserve(raw.size());
    for (const auto& candidate : raw) {
        contrast.push_back(candidate.local_contrast_z);
        dog.push_back(candidate.dog_z);
        compactness.push_back(candidate.compactness);
    }
    const auto contrast_rank = empirical_ranks(contrast);
    const auto dog_rank = empirical_ranks(dog);
    const auto compactness_rank = empirical_ranks(compactness);
    const auto clusters = raw_cluster_ids(raw, spacing);

    std::vector<double> evidences(raw.size(), 0.0);
    for (size_t i = 0; i < raw.size(); ++i) {
        // Los pesos combinan variables ya normalizadas dentro de la imagen.
        // No son umbrales de intensidad ni dependen del dataset.
        evidences[i] = 0.40 * contrast_rank[i]
                     + 0.40 * dog_rank[i]
                     + 0.20 * compactness_rank[i];
    }
    const double evidence_median = percentile_double(evidences, 0.5);
    std::vector<double> deviations;
    deviations.reserve(evidences.size());
    for (double value : evidences) deviations.push_back(std::abs(value - evidence_median));
    const double evidence_mad = percentile_double(std::move(deviations), 0.5);
    // Corte calculado de nuevo para cada imagen. El coeficiente es estructural,
    // no un valor fijo de intensidad.
    const double adaptive_cutoff = evidence_median + 0.5 * 1.4826 * evidence_mad;

    std::vector<V4TraceCandidate> trace;
    trace.reserve(raw.size());
    for (size_t i = 0; i < raw.size(); ++i) {
        const auto& candidate = raw[i];
        const bool strict = candidate_accepts_v2(candidate, 0);
        const bool v3 = accepts_v3_score(candidate, V3_SCORE_CUTOFFS[0]);
        const bool adaptive = evidences[i] >= adaptive_cutoff;
        int stage = 0;
        if (candidate.local_contrast_z < 0.0
            || candidate.dog_z < 0.5
            || candidate.compactness < 0.03) {
            stage = 1; // piso de seguridad heredado
        } else if (!v3) {
            stage = 2; // puntuacion v3
        } else {
            stage = 3; // aceptado v3
        }
        trace.push_back({
            candidate.x,
            candidate.y,
            candidate.area_px * static_cast<double>(spacing) * spacing,
            candidate.compactness,
            candidate.local_contrast_z,
            candidate.dog_z,
            candidate_score_v2(candidate),
            contrast_rank[i],
            dog_rank[i],
            compactness_rank[i],
            evidences[i],
            clusters[i],
            strict ? 1 : 0,
            v3 ? 1 : 0,
            adaptive ? 1 : 0,
            stage,
        });
    }
    return trace;
}

#if defined(_WIN32)
#define INBREAST_V4_EXPORT extern "C" __declspec(dllexport)
#else
#define INBREAST_V4_EXPORT extern "C"
#endif

// API pura de inferencia. Retornos:
// 0 correcto; 1 excepcion; 2 argumento invalido; 3 QC; 4 capacidad insuficiente.
// Una primera llamada con capacidad cero devuelve 4 y raw_count permite
// dimensionar los buffers. No se reciben etiquetas reales.
INBREAST_V4_EXPORT int analyze_inbreast_v4_trace(
    const float* image, uint64_t image_len,
    const uint8_t* mask, uint64_t mask_len,
    uint32_t rows, uint32_t cols, float spacing,
    uint64_t candidate_capacity,
    double* adaptive_threshold, uint64_t* raw_count,
    double* x, double* y, double* area_mm2,
    double* compactness, double* local_contrast_z, double* dog_z,
    double* legacy_score, double* contrast_rank, double* dog_rank,
    double* compactness_rank, double* evidence,
    uint32_t* cluster_id,
    int* strict_accept, int* v3_accept, int* adaptive_accept,
    int* rejection_stage,
    int* quality_code, double* time_ms) {
    if (adaptive_threshold) *adaptive_threshold = std::numeric_limits<double>::quiet_NaN();
    if (raw_count) *raw_count = 0;
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

        // Formula original e invariantes deliberadamente conservadas.
        const double threshold = original_adaptive_threshold(deform, analysis_mask, 20.0);
        const auto raw = extract_candidate_features_v2(
            deform, pyramid.dog, normalized, analysis_mask, nullptr,
            rows, cols, spacing, threshold);
        const auto trace = build_v4_trace(raw, spacing);

        if (adaptive_threshold) *adaptive_threshold = threshold;
        if (raw_count) *raw_count = static_cast<uint64_t>(trace.size());
        if (candidate_capacity < trace.size()) {
            if (quality_code) *quality_code = 4;
            return 4;
        }

        for (size_t i = 0; i < trace.size(); ++i) {
            const auto& candidate = trace[i];
            if (x) x[i] = candidate.x;
            if (y) y[i] = candidate.y;
            if (area_mm2) area_mm2[i] = candidate.area_mm2;
            if (compactness) compactness[i] = candidate.compactness;
            if (local_contrast_z) local_contrast_z[i] = candidate.local_contrast_z;
            if (dog_z) dog_z[i] = candidate.dog_z;
            if (legacy_score) legacy_score[i] = candidate.legacy_score;
            if (contrast_rank) contrast_rank[i] = candidate.contrast_rank;
            if (dog_rank) dog_rank[i] = candidate.dog_rank;
            if (compactness_rank) compactness_rank[i] = candidate.compactness_rank;
            if (evidence) evidence[i] = candidate.evidence;
            if (cluster_id) cluster_id[i] = candidate.cluster_id;
            if (strict_accept) strict_accept[i] = candidate.strict_accept;
            if (v3_accept) v3_accept[i] = candidate.v3_accept;
            if (adaptive_accept) adaptive_accept[i] = candidate.adaptive_accept;
            if (rejection_stage) rejection_stage[i] = candidate.rejection_stage;
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

#ifndef INBREAST_V4_LIBRARY
int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Uso: deform_inbreast_v4_adaptive <archivo.inbr> [archivo.inbr ...]\n";
        return 2;
    }
    std::cout << "archivo,umbral_adaptativo,candidatos_crudos,tiempo_ms\n";
    for (int argument = 1; argument < argc; ++argument) {
        try {
            const InputImage input = read_input(argv[argument]);
            const size_t n = input.image.size();
            double threshold = 0.0, elapsed = 0.0;
            uint64_t count = 0;
            int quality = 0;
            const int first = analyze_inbreast_v4_trace(
                input.image.data(), n, input.breast_mask.data(), n,
                input.rows, input.cols, input.spacing, 0,
                &threshold, &count,
                nullptr, nullptr, nullptr, nullptr, nullptr, nullptr,
                nullptr, nullptr, nullptr, nullptr, nullptr,
                nullptr, nullptr, nullptr, nullptr, nullptr,
                &quality, &elapsed);
            if (first != 0 && first != 4) {
                throw std::runtime_error("fallo de control de calidad v4");
            }
            std::cout << std::filesystem::path(argv[argument]).filename().string()
                      << ',' << std::fixed << std::setprecision(9) << threshold
                      << ',' << count << ',' << std::setprecision(3) << elapsed << '\n';
        } catch (const std::exception& error) {
            std::cerr << "ERROR," << argv[argument] << ',' << error.what() << '\n';
            return 1;
        }
    }
    return 0;
}
#endif
