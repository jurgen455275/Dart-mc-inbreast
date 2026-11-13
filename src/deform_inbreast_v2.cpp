// Variante v2 experimental. No sustituye ninguna implementacion anterior.
// Conserva exactamente el umbral adaptativo original:
//   T = min(0.95, media_M(D) + 20 * desviacion_M(D)).
//
// Cambios deliberados:
// 1. usa la comparacion estricta D > T de la implementacion original;
// 2. conserva todos los candidatos primarios antes de decidir;
// 3. agrega un rescate DoG solo cuando el umbral llega a 0 o 0.95;
// 4. conserva como ablaciones un rescate mas amplio y una regla dos-de-tres.
//
// Modos: 0 estricto; 1 principal con rescate extremo; 2 rescate si no hay
// candidatos crudos; 3 sensible con dos de tres evidencias fuertes.

#define INBREAST_OPTIMIZADO_LIBRARY
#include "deform_inbreast_optimizado.cpp"

static constexpr int V2_MODE_COUNT = 4;
static constexpr double V2_MODE_CODES[V2_MODE_COUNT] = {0, 1, 2, 3};

struct V2Result {
    size_t accepted{};
    size_t clusters{};
    size_t max_cluster{};
    size_t tp{};
    size_t fp{};
    bool localized{};
    bool predicted{};
    bool rescue_used{};
};

static double sigmoid_stable(double value) {
    if (value >= 0.0) {
        const double z = std::exp(-value);
        return 1.0 / (1.0 + z);
    }
    const double z = std::exp(value);
    return z / (1.0 + z);
}

// La puntuacion permite compensacion entre evidencias. Un candidato no se
// pierde solo por quedar levemente debajo de uno de los tres cortes antiguos.
static double candidate_score_v2(const CandidateFeature& candidate) {
    const double contrast = sigmoid_stable(1.20 * (candidate.local_contrast_z - 0.50));
    const double dog = sigmoid_stable(0.60 * (candidate.dog_z - 1.50));
    const double shape = sigmoid_stable(8.00 * (candidate.compactness - 0.08));
    return 0.45 * contrast + 0.40 * dog + 0.15 * shape;
}

static bool candidate_accepts_v2(const CandidateFeature& candidate, int mode) {
    const bool contrast_strict = candidate.local_contrast_z >= 0.75;
    const bool dog_strict = candidate.dog_z >= 2.0;
    const bool shape_strict = candidate.compactness >= 0.08;
    if (mode < 3) return contrast_strict && dog_strict && shape_strict;
    const int strong = static_cast<int>(contrast_strict)
                     + static_cast<int>(dog_strict)
                     + static_cast<int>(shape_strict);
    const bool moderate_floor = candidate.local_contrast_z >= 0.0
                             && candidate.dog_z >= 0.5
                             && candidate.compactness >= 0.03;
    return moderate_floor && strong >= 2 && candidate_score_v2(candidate) >= 0.55;
}

static std::vector<CandidateFeature> extract_candidate_features_v2(
    const std::vector<float>& score,
    const std::vector<float>& validation_dog,
    const std::vector<float>& image,
    const std::vector<uint8_t>& mask,
    const uint8_t* gt_mask,
    uint32_t rows, uint32_t cols,
    float spacing, double threshold) {
    std::vector<uint8_t> binary(score.size(), 0), seen(score.size(), 0);
    for (size_t p = 0; p < score.size(); ++p) {
        // Comparacion fiel al C++ original. Es especialmente importante si
        // el umbral adaptativo toma el valor degenerado cero.
        binary[p] = mask[p] && score[p] > threshold ? 1 : 0;
    }
    const double safe_spacing = std::max(0.01f, spacing);
    const double amin = 0.01 / (safe_spacing * safe_spacing);
    const double amax = 1.00 / (safe_spacing * safe_spacing);
    const auto [dog_median, dog_scale] = robust_location_scale(validation_dog, mask);
    const int annulus_inner = std::clamp(
        static_cast<int>(std::lround(0.15 / safe_spacing)), 2, 10);
    const int annulus_outer = std::clamp(
        static_cast<int>(std::lround(0.50 / safe_spacing)), annulus_inner + 2, 24);
    const int inner2 = annulus_inner * annulus_inner;
    const int outer2 = annulus_outer * annulus_outer;
    std::vector<size_t> stack;
    stack.reserve(2048);
    std::vector<CandidateFeature> candidates;

    for (uint32_t y = 0; y < rows; ++y) {
        for (uint32_t x = 0; x < cols; ++x) {
            const size_t start = static_cast<size_t>(y) * cols + x;
            if (!binary[start] || seen[start]) continue;
            seen[start] = 1;
            stack.clear();
            stack.push_back(start);
            size_t area = 0;
            uint64_t sum_x = 0, sum_y = 0;
            double sum_intensity = 0.0;
            double dog_max = 0.0;
            size_t perimeter = 0;
            while (!stack.empty()) {
                const size_t p = stack.back();
                stack.pop_back();
                ++area;
                const int py = static_cast<int>(p / cols);
                const int px = static_cast<int>(p % cols);
                sum_x += static_cast<uint64_t>(px);
                sum_y += static_cast<uint64_t>(py);
                sum_intensity += image[p];
                dog_max = std::max(dog_max, static_cast<double>(validation_dog[p]));
                const int dx4[4] = {-1, 1, 0, 0};
                const int dy4[4] = {0, 0, -1, 1};
                for (int k = 0; k < 4; ++k) {
                    const int nx = px + dx4[k], ny = py + dy4[k];
                    if (nx < 0 || ny < 0 || nx >= static_cast<int>(cols)
                        || ny >= static_cast<int>(rows)
                        || !binary[static_cast<size_t>(ny) * cols + nx]) {
                        ++perimeter;
                    }
                }
                for (int dy = -1; dy <= 1; ++dy) {
                    for (int dx = -1; dx <= 1; ++dx) {
                        if (dx == 0 && dy == 0) continue;
                        const int nx = px + dx, ny = py + dy;
                        if (nx < 0 || ny < 0 || nx >= static_cast<int>(cols)
                            || ny >= static_cast<int>(rows)) continue;
                        const size_t q = static_cast<size_t>(ny) * cols + nx;
                        if (binary[q] && !seen[q]) {
                            seen[q] = 1;
                            stack.push_back(q);
                        }
                    }
                }
            }
            if (!(static_cast<double>(area) > amin && static_cast<double>(area) < amax)) continue;
            const int cx = static_cast<int>(std::lround(static_cast<double>(sum_x) / area));
            const int cy = static_cast<int>(std::lround(static_cast<double>(sum_y) / area));
            const double center_mean = sum_intensity / area;
            double ring_sum = 0.0, ring_sum2 = 0.0;
            size_t ring_n = 0;
            for (int dy = -annulus_outer; dy <= annulus_outer; ++dy) {
                const int yy = cy + dy;
                if (yy < 0 || yy >= static_cast<int>(rows)) continue;
                for (int dx = -annulus_outer; dx <= annulus_outer; ++dx) {
                    const int distance2 = dx * dx + dy * dy;
                    if (distance2 < inner2 || distance2 > outer2) continue;
                    const int xx = cx + dx;
                    if (xx < 0 || xx >= static_cast<int>(cols)) continue;
                    const size_t q = static_cast<size_t>(yy) * cols + xx;
                    if (!mask[q]) continue;
                    const double value = image[q];
                    ring_sum += value;
                    ring_sum2 += value * value;
                    ++ring_n;
                }
            }
            const double ring_mean = ring_n ? ring_sum / ring_n : center_mean;
            const double ring_variance = ring_n
                ? std::max(0.0, ring_sum2 / ring_n - ring_mean * ring_mean) : 0.0;
            const double ring_std = std::sqrt(ring_variance);
            const double contrast_z = (center_mean - ring_mean) / std::max(0.01, ring_std);
            const double dog_z = (dog_max - dog_median) / dog_scale;
            const double compactness = perimeter
                ? std::min(1.0, 4.0 * 3.14159265358979323846 * area / (perimeter * perimeter))
                : 0.0;
            candidates.push_back({
                static_cast<double>(cx), static_cast<double>(cy), static_cast<double>(area),
                compactness, contrast_z, dog_z,
                overlaps_ground_truth(gt_mask, rows, cols, cx, cy),
            });
        }
    }
    return candidates;
}

static void analyze_v2_core(
    const std::vector<float>& input_image,
    const std::vector<uint8_t>& input_mask,
    const uint8_t* gt_mask,
    uint32_t rows, uint32_t cols, float spacing,
    double& adaptive_threshold, size_t& raw_count,
    V2Result (&results)[V2_MODE_COUNT]) {
    const auto image = robust_renormalize(input_image, input_mask);
    const auto mask = analysis_mask_physical(input_mask, rows, cols, spacing);
    const auto deform = deformation_map(image, rows, cols);
    const auto pyramid = physical_dog_pyramid(image, rows, cols, spacing);
    adaptive_threshold = original_adaptive_threshold(deform, mask, 20.0);
    const auto raw = extract_candidate_features_v2(
        deform, pyramid.dog, image, mask, gt_mask,
        rows, cols, spacing, adaptive_threshold);
    raw_count = raw.size();

    std::vector<CandidateFeature> strict;
    strict.reserve(raw.size());
    for (const auto& candidate : raw) {
        if (candidate_accepts_v2(candidate, 0)) strict.push_back(candidate);
    }
    std::vector<CandidateFeature> classical_strict;
    const bool need_classical = strict.empty()
        && (raw.empty() || adaptive_threshold <= 1e-12 || adaptive_threshold >= 0.95 - 1e-12);
    if (need_classical) {
        const auto classical_raw = extract_candidate_features_v2(
            pyramid.dog, pyramid.dog, image, mask, gt_mask,
            rows, cols, spacing, 0.10);
        classical_strict.reserve(classical_raw.size());
        for (const auto& candidate : classical_raw) {
            if (candidate_accepts_v2(candidate, 0)) classical_strict.push_back(candidate);
        }
    }

    for (int mode = 0; mode < V2_MODE_COUNT; ++mode) {
        std::vector<CandidateFeature> accepted;
        if (mode < 3) {
            accepted = strict;
            const bool extreme = adaptive_threshold <= 1e-12
                              || adaptive_threshold >= 0.95 - 1e-12;
            const bool use_rescue = accepted.empty()
                && ((mode == 1 && extreme) || (mode == 2 && raw.empty()));
            if (use_rescue) accepted = classical_strict;
            results[mode].rescue_used = use_rescue && !classical_strict.empty();
        } else {
            accepted.reserve(raw.size());
            for (const auto& candidate : raw) {
                if (candidate_accepts_v2(candidate, mode)) accepted.push_back(candidate);
            }
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
#define INBREAST_V2_EXPORT extern "C" __declspec(dllexport)
#else
#define INBREAST_V2_EXPORT extern "C"
#endif

INBREAST_V2_EXPORT int analyze_inbreast_v2(
    const float* image, const uint8_t* mask, const uint8_t* gt_mask,
    uint32_t rows, uint32_t cols, float spacing,
    double* adaptive_threshold, double* mode_codes4,
    uint64_t* raw_count, uint64_t* accepted4,
    uint64_t* clusters4, uint64_t* max_cluster4,
    uint64_t* tp4, uint64_t* fp4,
    int* localized4, int* predicted4, int* rescue_used4,
    double* time_ms) {
    if (!image || !mask || rows == 0 || cols == 0 || spacing <= 0.0f) return 2;
    try {
        const size_t n = static_cast<size_t>(rows) * cols;
        const std::vector<float> image_v(image, image + n);
        const std::vector<uint8_t> mask_v(mask, mask + n);
        V2Result results[V2_MODE_COUNT];
        double threshold = 0.0;
        size_t raw = 0;
        const auto start = std::chrono::steady_clock::now();
        analyze_v2_core(image_v, mask_v, gt_mask, rows, cols, spacing, threshold, raw, results);
        const auto finish = std::chrono::steady_clock::now();
        if (adaptive_threshold) *adaptive_threshold = threshold;
        if (raw_count) *raw_count = static_cast<uint64_t>(raw);
        for (int mode = 0; mode < V2_MODE_COUNT; ++mode) {
            if (mode_codes4) mode_codes4[mode] = V2_MODE_CODES[mode];
            if (accepted4) accepted4[mode] = static_cast<uint64_t>(results[mode].accepted);
            if (clusters4) clusters4[mode] = static_cast<uint64_t>(results[mode].clusters);
            if (max_cluster4) max_cluster4[mode] = static_cast<uint64_t>(results[mode].max_cluster);
            if (tp4) tp4[mode] = static_cast<uint64_t>(results[mode].tp);
            if (fp4) fp4[mode] = static_cast<uint64_t>(results[mode].fp);
            if (localized4) localized4[mode] = results[mode].localized ? 1 : 0;
            if (predicted4) predicted4[mode] = results[mode].predicted ? 1 : 0;
            if (rescue_used4) rescue_used4[mode] = results[mode].rescue_used ? 1 : 0;
        }
        if (time_ms) {
            *time_ms = std::chrono::duration<double, std::milli>(finish - start).count();
        }
        return 0;
    } catch (...) {
        return 1;
    }
}

#ifndef INBREAST_V2_LIBRARY
int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Uso: deform_inbreast_v2 <archivo.inbr> [archivo.inbr ...]\n";
        return 2;
    }
    std::cout << "archivo,modo,umbral_adaptativo,corte_score,raw,aceptados,clusters,max_cluster,positiva,tiempo_ms\n";
    for (int argument = 1; argument < argc; ++argument) {
        try {
            const InputImage input = read_input(argv[argument]);
            V2Result results[V2_MODE_COUNT];
            double threshold = 0.0;
            size_t raw = 0;
            const auto start = std::chrono::steady_clock::now();
            analyze_v2_core(input.image, input.breast_mask, nullptr,
                            input.rows, input.cols, input.spacing,
                            threshold, raw, results);
            const auto finish = std::chrono::steady_clock::now();
            const double elapsed = std::chrono::duration<double, std::milli>(finish - start).count();
            for (int mode = 0; mode < V2_MODE_COUNT; ++mode) {
                std::cout << std::filesystem::path(argv[argument]).filename().string() << ','
                          << "adaptive-v2-mode-" << mode << ',' << std::fixed << std::setprecision(9)
                          << threshold << ',' << V2_MODE_CODES[mode] << ',' << raw << ','
                          << results[mode].accepted << ','
                          << results[mode].clusters << ',' << results[mode].max_cluster << ','
                          << (results[mode].predicted ? 1 : 0) << ','
                          << std::setprecision(3) << elapsed << '\n';
            }
        } catch (const std::exception& error) {
            std::cerr << "ERROR," << argv[argument] << ',' << error.what() << '\n';
            return 1;
        }
    }
    return 0;
}
#endif
