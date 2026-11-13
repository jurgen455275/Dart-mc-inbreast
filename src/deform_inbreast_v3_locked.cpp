// Variante experimental v3 locked. No sustituye ninguna version anterior.
//
// Invariante cientifico del proyecto (sin cambios):
//   T = min(0.95, media_M(D) + 20 * desviacion_M(D))
// y la seleccion primaria usa estrictamente D > T.
//
// Las mejoras se limitan a controles de entrada y al postfiltro de candidatos
// ya producidos por el nucleo adaptativo. No se generan candidatos clasicos ni
// se modifica el umbral para rescatar imagenes.

#define INBREAST_V2_LIBRARY
#include "deform_inbreast_v2.cpp"

#include <limits>

static constexpr int V3_MODE_COUNT = 5;
static constexpr double V3_SCORE_CUTOFFS[V3_MODE_COUNT] = {0.825, 0.80, 0.85, 0.875, -1.0};

struct V3Result {
    size_t accepted{};
    size_t clusters{};
    size_t max_cluster{};
    size_t tp{};
    size_t fp{};
    bool localized{};
    bool predicted{};
};

static bool finite_image_inside_mask(const float* image, const uint8_t* mask, size_t n) {
    size_t active = 0;
    for (size_t p = 0; p < n; ++p) {
        if (!mask[p]) continue;
        ++active;
        if (!std::isfinite(static_cast<double>(image[p]))) return false;
    }
    return active >= 64;
}

static bool accepts_v3_score(const CandidateFeature& candidate, double cutoff) {
    // Pisos amplios de seguridad: evitan que una evidencia extrema compense
    // por completo un contraste, respuesta blob o forma implausibles.
    if (candidate.local_contrast_z < 0.0
        || candidate.dog_z < 0.5
        || candidate.compactness < 0.03) {
        return false;
    }
    return candidate_score_v2(candidate) >= cutoff;
}

static void analyze_v3_locked_core(
    const std::vector<float>& input_image,
    const std::vector<uint8_t>& input_mask,
    const uint8_t* gt_mask,
    uint32_t rows, uint32_t cols, float spacing,
    double& adaptive_threshold, size_t& raw_count,
    V3Result (&results)[V3_MODE_COUNT]) {
    // Estas cuatro operaciones permanecen exactamente alineadas con v2.
    const auto image = robust_renormalize(input_image, input_mask);
    const auto mask = analysis_mask_physical(input_mask, rows, cols, spacing);
    const auto deform = deformation_map(image, rows, cols);
    const auto pyramid = physical_dog_pyramid(image, rows, cols, spacing);
    adaptive_threshold = original_adaptive_threshold(deform, mask, 20.0);

    // La comparacion estricta D > T esta dentro de esta funcion heredada de v2.
    const auto raw = extract_candidate_features_v2(
        deform, pyramid.dog, image, mask, gt_mask,
        rows, cols, spacing, adaptive_threshold);
    raw_count = raw.size();

    for (int mode = 0; mode < V3_MODE_COUNT; ++mode) {
        std::vector<CandidateFeature> accepted;
        accepted.reserve(raw.size());
        for (const auto& candidate : raw) {
            const bool keep = mode == 4
                ? candidate_accepts_v2(candidate, 0)  // referencia estricta
                : accepts_v3_score(candidate, V3_SCORE_CUTOFFS[mode]);
            if (keep) accepted.push_back(candidate);
        }
        auto& result = results[mode];
        result.accepted = accepted.size();
        for (const auto& candidate : accepted) {
            if (candidate.overlaps_gt) {
                ++result.tp;
                result.localized = true;
            } else {
                ++result.fp;
            }
        }
        cluster_candidates(accepted, spacing, result.clusters, result.max_cluster);
        result.predicted = !accepted.empty();
    }
}

#if defined(_WIN32)
#define INBREAST_V3_EXPORT extern "C" __declspec(dllexport)
#else
#define INBREAST_V3_EXPORT extern "C"
#endif

// API con longitudes y capacidad explicitas. Retornos:
// 0 correcto; 1 excepcion; 2 argumento invalido; 3 control de calidad fallido.
INBREAST_V3_EXPORT int analyze_inbreast_v3_locked(
    const float* image, uint64_t image_len,
    const uint8_t* mask, uint64_t mask_len,
    const uint8_t* gt_mask, uint64_t gt_len,
    uint32_t rows, uint32_t cols, float spacing,
    uint32_t output_capacity,
    double* adaptive_threshold, double* score_cutoffs,
    uint64_t* raw_count, uint64_t* accepted,
    uint64_t* clusters, uint64_t* max_cluster,
    uint64_t* tp, uint64_t* fp,
    int* localized, int* predicted,
    int* quality_code, double* time_ms) {
    if (quality_code) *quality_code = 0;
    if (!image || !mask || rows == 0 || cols == 0
        || !std::isfinite(static_cast<double>(spacing)) || spacing <= 0.0f
        || output_capacity < V3_MODE_COUNT) {
        return 2;
    }
    if (static_cast<size_t>(rows) > std::numeric_limits<size_t>::max() / cols) return 2;
    const size_t n = static_cast<size_t>(rows) * cols;
    if (image_len < n || mask_len < n || (gt_mask && gt_len < n)) return 2;
    if (!finite_image_inside_mask(image, mask, n)) {
        if (quality_code) *quality_code = 1;
        return 3;
    }
    try {
        const std::vector<float> image_v(image, image + n);
        const std::vector<uint8_t> mask_v(mask, mask + n);
        V3Result results[V3_MODE_COUNT];
        double threshold = 0.0;
        size_t raw = 0;
        const auto start = std::chrono::steady_clock::now();
        analyze_v3_locked_core(
            image_v, mask_v, gt_mask, rows, cols, spacing, threshold, raw, results);
        const auto finish = std::chrono::steady_clock::now();
        if (adaptive_threshold) *adaptive_threshold = threshold;
        if (raw_count) *raw_count = static_cast<uint64_t>(raw);
        for (int mode = 0; mode < V3_MODE_COUNT; ++mode) {
            if (score_cutoffs) score_cutoffs[mode] = V3_SCORE_CUTOFFS[mode];
            if (accepted) accepted[mode] = static_cast<uint64_t>(results[mode].accepted);
            if (clusters) clusters[mode] = static_cast<uint64_t>(results[mode].clusters);
            if (max_cluster) max_cluster[mode] = static_cast<uint64_t>(results[mode].max_cluster);
            if (tp) tp[mode] = static_cast<uint64_t>(results[mode].tp);
            if (fp) fp[mode] = static_cast<uint64_t>(results[mode].fp);
            if (localized) localized[mode] = results[mode].localized ? 1 : 0;
            if (predicted) predicted[mode] = results[mode].predicted ? 1 : 0;
        }
        if (time_ms) {
            *time_ms = std::chrono::duration<double, std::milli>(finish - start).count();
        }
        return 0;
    } catch (...) {
        return 1;
    }
}

#ifndef INBREAST_V3_LIBRARY
int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Uso: deform_inbreast_v3_locked <archivo.inbr> [archivo.inbr ...]\n";
        return 2;
    }
    std::cout << "archivo,modo,umbral_adaptativo,corte_score,raw,aceptados,clusters,max_cluster,positiva,tiempo_ms\n";
    for (int argument = 1; argument < argc; ++argument) {
        try {
            const InputImage input = read_input(argv[argument]);
            V3Result results[V3_MODE_COUNT];
            double threshold = 0.0;
            size_t raw = 0;
            const auto start = std::chrono::steady_clock::now();
            analyze_v3_locked_core(input.image, input.breast_mask, nullptr,
                                   input.rows, input.cols, input.spacing,
                                   threshold, raw, results);
            const auto finish = std::chrono::steady_clock::now();
            const double elapsed = std::chrono::duration<double, std::milli>(finish - start).count();
            for (int mode = 0; mode < V3_MODE_COUNT; ++mode) {
                std::cout << std::filesystem::path(argv[argument]).filename().string() << ','
                          << "adaptive-v3-mode-" << mode << ',' << std::fixed << std::setprecision(9)
                          << threshold << ',' << V3_SCORE_CUTOFFS[mode] << ',' << raw << ','
                          << results[mode].accepted << ',' << results[mode].clusters << ','
                          << results[mode].max_cluster << ',' << (results[mode].predicted ? 1 : 0)
                          << ',' << std::setprecision(3) << elapsed << '\n';
            }
        } catch (const std::exception& error) {
            std::cerr << "ERROR," << argv[argument] << ',' << error.what() << '\n';
            return 1;
        }
    }
    return 0;
}
#endif
