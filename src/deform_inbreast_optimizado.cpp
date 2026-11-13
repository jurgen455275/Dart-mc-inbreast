// Nueva variante experimental. No sustituye deform_inbreast_mejorado.cpp.
// Ruta 0: umbral adaptativo original + validacion posterior y agrupamiento.
// Ruta 1: Difference of Gaussians clasico + umbral global fijo + la misma validacion posterior.
//
// El calculo central de la ruta adaptativa se conserva sin cambios:
// T = min(0.95, media_M(D) + 20 * desviacion_M(D)).

#define INBREAST_MEJORADO_LIBRARY
#include "deform_inbreast_mejorado.cpp"

struct CandidateFeature {
    double x{};
    double y{};
    double area_px{};
    double compactness{};
    double local_contrast_z{};
    double dog_z{};
    bool overlaps_gt{};
};

struct OptimizedResult {
    double threshold{};
    size_t raw_candidates{};
    size_t accepted_candidates{};
    size_t clusters{};
    size_t max_cluster{};
    size_t tp{};
    size_t fp{};
    bool localized{};
    bool predicted{};
};

struct DogPyramid {
    std::vector<float> dog;
};

static size_t count_mask(const std::vector<uint8_t>& mask) {
    return static_cast<size_t>(std::count_if(mask.begin(), mask.end(), [](uint8_t value) {
        return value != 0;
    }));
}

static std::vector<uint8_t> analysis_mask_physical(
    const std::vector<uint8_t>& input_mask,
    uint32_t rows, uint32_t cols, float spacing) {
    // Margen fisico de 0.50 mm. Se limita para evitar kernels patologicos si
    // los metadatos contienen un spacing invalido o extremo.
    const int radius = std::clamp(
        static_cast<int>(std::lround(0.50 / std::max(0.01f, spacing))), 3, 24);
    auto eroded = erode_mask_box(input_mask, rows, cols, radius);
    const size_t original_n = count_mask(input_mask);
    const size_t eroded_n = count_mask(eroded);
    // Control de calidad: la formula del umbral no cambia, pero se evita
    // calcularla sobre una mascara vacia o destruida por la erosion.
    if (original_n == 0 || eroded_n < 1000 || eroded_n * 5 < original_n) {
        return input_mask;
    }
    return eroded;
}

static DogPyramid physical_dog_pyramid(const std::vector<float>& image,
                                       uint32_t rows, uint32_t cols,
                                       float spacing) {
    const float safe_spacing = std::max(0.01f, spacing);
    const float sigma1 = std::clamp(0.06f / safe_spacing, 0.8f, 2.0f);
    const float sigma2 = std::clamp(0.12f / safe_spacing, 1.6f, 4.0f);
    const float sigma3 = std::clamp(0.24f / safe_spacing, 3.2f, 8.0f);
    const auto g1 = gaussian_blur_sigma(image, rows, cols, sigma1);
    const auto g2 = gaussian_blur_sigma(image, rows, cols, sigma2);
    auto g3 = gaussian_blur_sigma(image, rows, cols, sigma3);
    std::vector<float> dog(image.size(), 0.0f);
    for (size_t p = 0; p < image.size(); ++p) {
        dog[p] = std::max({0.0f, g1[p] - g2[p], g2[p] - g3[p]});
    }
    return {std::move(dog)};
}

static std::pair<double, double> robust_location_scale(
    const std::vector<float>& values, const std::vector<uint8_t>& mask) {
    std::vector<float> selected;
    selected.reserve(values.size() / 2);
    for (size_t p = 0; p < values.size(); ++p) {
        if (mask[p]) selected.push_back(values[p]);
    }
    if (selected.empty()) return {0.0, 1e-6};
    const double median = percentile(selected, 0.5);
    std::vector<float> deviations;
    deviations.reserve(selected.size());
    for (float value : selected) {
        deviations.push_back(static_cast<float>(std::abs(value - median)));
    }
    const double mad = percentile(std::move(deviations), 0.5);
    return {median, std::max(1e-6, 1.4826 * mad)};
}

static bool overlaps_ground_truth(const uint8_t* gt_mask,
                                  uint32_t rows, uint32_t cols,
                                  int cx, int cy) {
    if (!gt_mask) return false;
    // Se mantiene la tolerancia historica de cinco pixeles para que la
    // localizacion sea comparable con las corridas anteriores.
    for (int y = std::max(0, cy - 5); y <= std::min(static_cast<int>(rows) - 1, cy + 5); ++y) {
        for (int x = std::max(0, cx - 5); x <= std::min(static_cast<int>(cols) - 1, cx + 5); ++x) {
            if (gt_mask[static_cast<size_t>(y) * cols + x]) return true;
        }
    }
    return false;
}

static std::vector<CandidateFeature> extract_candidate_features(
    const std::vector<float>& score,
    const std::vector<float>& validation_dog,
    const std::vector<float>& image,
    const std::vector<uint8_t>& mask,
    const uint8_t* gt_mask,
    uint32_t rows, uint32_t cols,
    float spacing, double threshold,
    size_t& raw_candidates) {
    std::vector<uint8_t> binary(score.size(), 0), seen(score.size(), 0);
    for (size_t p = 0; p < score.size(); ++p) {
        binary[p] = mask[p] && score[p] >= threshold ? 1 : 0;
    }
    const double amin = 0.01 / (spacing * spacing);
    const double amax = 1.00 / (spacing * spacing);
    const auto [dog_median, dog_scale] = robust_location_scale(validation_dog, mask);
    const int annulus_inner = std::clamp(
        static_cast<int>(std::lround(0.15 / std::max(0.01f, spacing))), 2, 10);
    const int annulus_outer = std::clamp(
        static_cast<int>(std::lround(0.50 / std::max(0.01f, spacing))), annulus_inner + 2, 24);
    const int inner2 = annulus_inner * annulus_inner;
    const int outer2 = annulus_outer * annulus_outer;
    std::vector<size_t> stack;
    stack.reserve(2048);
    std::vector<CandidateFeature> candidates;
    raw_candidates = 0;

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
                    if (nx < 0 || ny < 0 || nx >= static_cast<int>(cols) || ny >= static_cast<int>(rows)
                        || !binary[static_cast<size_t>(ny) * cols + nx]) {
                        ++perimeter;
                    }
                }
                for (int dy = -1; dy <= 1; ++dy) for (int dx = -1; dx <= 1; ++dx) {
                    if (dx == 0 && dy == 0) continue;
                    const int nx = px + dx, ny = py + dy;
                    if (nx < 0 || ny < 0 || nx >= static_cast<int>(cols) || ny >= static_cast<int>(rows)) continue;
                    const size_t q = static_cast<size_t>(ny) * cols + nx;
                    if (binary[q] && !seen[q]) {
                        seen[q] = 1;
                        stack.push_back(q);
                    }
                }
            }
            if (!(static_cast<double>(area) > amin && static_cast<double>(area) < amax)) continue;
            ++raw_candidates;
            const int cx = static_cast<int>(sum_x / area);
            const int cy = static_cast<int>(sum_y / area);
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
                ? std::min(1.0, 4.0 * 3.14159265358979323846 * area / (perimeter * perimeter)) : 0.0;
            candidates.push_back({
                static_cast<double>(cx), static_cast<double>(cy), static_cast<double>(area),
                compactness, contrast_z, dog_z,
                overlaps_ground_truth(gt_mask, rows, cols, cx, cy),
            });
        }
    }
    return candidates;
}

static std::vector<CandidateFeature> validate_candidates(
    const std::vector<CandidateFeature>& raw) {
    std::vector<CandidateFeature> accepted;
    accepted.reserve(raw.size());
    for (const auto& candidate : raw) {
        const bool bright_local = candidate.local_contrast_z >= 0.75;
        const bool blob_response = candidate.dog_z >= 2.0;
        const bool plausible_shape = candidate.compactness >= 0.08;
        if (bright_local && blob_response && plausible_shape) accepted.push_back(candidate);
    }
    return accepted;
}

static void cluster_candidates(const std::vector<CandidateFeature>& candidates,
                               float spacing,
                               size_t& clusters, size_t& max_cluster) {
    clusters = 0;
    max_cluster = 0;
    if (candidates.empty()) return;
    const double radius_px = 5.0 / std::max(0.01f, spacing);
    const double radius2 = radius_px * radius_px;
    std::vector<uint8_t> seen(candidates.size(), 0);
    std::vector<size_t> stack;
    for (size_t start = 0; start < candidates.size(); ++start) {
        if (seen[start]) continue;
        seen[start] = 1;
        stack.clear();
        stack.push_back(start);
        size_t cluster_size = 0;
        while (!stack.empty()) {
            const size_t current = stack.back();
            stack.pop_back();
            ++cluster_size;
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
        ++clusters;
        max_cluster = std::max(max_cluster, cluster_size);
    }
}

static OptimizedResult analyze_score(
    const std::vector<float>& score,
    const std::vector<float>& dog,
    const std::vector<float>& image,
    const std::vector<uint8_t>& mask,
    const uint8_t* gt_mask,
    uint32_t rows, uint32_t cols,
    float spacing, double threshold) {
    OptimizedResult result;
    result.threshold = threshold;
    auto raw = extract_candidate_features(
        score, dog, image, mask, gt_mask, rows, cols, spacing, threshold, result.raw_candidates);
    auto accepted = validate_candidates(raw);
    result.accepted_candidates = accepted.size();
    for (const auto& candidate : accepted) {
        if (candidate.overlaps_gt) {
            ++result.tp;
            result.localized = true;
        } else {
            ++result.fp;
        }
    }
    cluster_candidates(accepted, spacing, result.clusters, result.max_cluster);
    // La clasificacion usa al menos un candidato ya validado. El agrupamiento
    // se conserva como evidencia cuantitativa y para posteriores curvas FROC,
    // pero no se exige un cluster minimo porque MIAS contiene positivas con
    // una unica microcalcificacion anotada.
    result.predicted = !accepted.empty();
    return result;
}

static void analyze_optimized_core(
    const std::vector<float>& input_image,
    const std::vector<uint8_t>& input_mask,
    const uint8_t* gt_mask,
    uint32_t rows, uint32_t cols, float spacing,
    OptimizedResult (&results)[2]) {
    const auto image = robust_renormalize(input_image, input_mask);
    const auto mask = analysis_mask_physical(input_mask, rows, cols, spacing);
    const auto deform = deformation_map(image, rows, cols);
    const auto pyramid = physical_dog_pyramid(image, rows, cols, spacing);

    // Ruta principal: formula adaptativa original intacta.
    const double adaptive_threshold = original_adaptive_threshold(deform, mask, 20.0);
    results[0] = analyze_score(
        deform, pyramid.dog, image, mask, gt_mask, rows, cols, spacing, adaptive_threshold);

    // Comparador clasico: detector de blobs Difference of Gaussians con un
    // umbral global fijo. A diferencia de la ruta principal, 0.10 no se
    // recalcula para cada imagen.
    const double classical_threshold = 0.10;
    results[1] = analyze_score(
        pyramid.dog, pyramid.dog, image, mask, gt_mask, rows, cols, spacing, classical_threshold);
}

#if defined(_WIN32)
#define INBREAST_OPT_EXPORT extern "C" __declspec(dllexport)
#else
#define INBREAST_OPT_EXPORT extern "C"
#endif

// Devuelve dos modos en orden: adaptive-optimized y classical-dog-fixed.
INBREAST_OPT_EXPORT int analyze_inbreast_optimizado(
    const float* image, const uint8_t* mask, const uint8_t* gt_mask,
    uint32_t rows, uint32_t cols, float spacing,
    double* thresholds2, uint64_t* raw2, uint64_t* accepted2,
    uint64_t* clusters2, uint64_t* max_cluster2,
    uint64_t* tp2, uint64_t* fp2, int* localized2, int* predicted2,
    double* time_ms) {
    if (!image || !mask || rows == 0 || cols == 0 || spacing <= 0.0f) return 2;
    try {
        const size_t n = static_cast<size_t>(rows) * cols;
        const std::vector<float> image_v(image, image + n);
        const std::vector<uint8_t> mask_v(mask, mask + n);
        OptimizedResult results[2];
        const auto start = std::chrono::steady_clock::now();
        analyze_optimized_core(image_v, mask_v, gt_mask, rows, cols, spacing, results);
        const auto finish = std::chrono::steady_clock::now();
        for (int mode = 0; mode < 2; ++mode) {
            if (thresholds2) thresholds2[mode] = results[mode].threshold;
            if (raw2) raw2[mode] = static_cast<uint64_t>(results[mode].raw_candidates);
            if (accepted2) accepted2[mode] = static_cast<uint64_t>(results[mode].accepted_candidates);
            if (clusters2) clusters2[mode] = static_cast<uint64_t>(results[mode].clusters);
            if (max_cluster2) max_cluster2[mode] = static_cast<uint64_t>(results[mode].max_cluster);
            if (tp2) tp2[mode] = static_cast<uint64_t>(results[mode].tp);
            if (fp2) fp2[mode] = static_cast<uint64_t>(results[mode].fp);
            if (localized2) localized2[mode] = results[mode].localized ? 1 : 0;
            if (predicted2) predicted2[mode] = results[mode].predicted ? 1 : 0;
        }
        if (time_ms) {
            *time_ms = std::chrono::duration<double, std::milli>(finish - start).count();
        }
        return 0;
    } catch (...) {
        return 1;
    }
}

#ifndef INBREAST_OPTIMIZADO_LIBRARY
int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Uso: deform_inbreast_optimizado <archivo.inbr> [archivo.inbr ...]\n";
        return 2;
    }
    std::cout << "archivo,modo,threshold,raw,aceptados,clusters,max_cluster,positiva,tiempo_ms\n";
    for (int argument = 1; argument < argc; ++argument) {
        try {
            const InputImage input = read_input(argv[argument]);
            OptimizedResult results[2];
            const auto start = std::chrono::steady_clock::now();
            analyze_optimized_core(
                input.image, input.breast_mask, nullptr,
                input.rows, input.cols, input.spacing, results);
            const auto finish = std::chrono::steady_clock::now();
            const double elapsed = std::chrono::duration<double, std::milli>(finish - start).count();
            for (int mode = 0; mode < 2; ++mode) {
                std::cout << std::filesystem::path(argv[argument]).filename().string() << ','
                          << (mode == 0 ? "adaptive-optimized" : "classical-dog-fixed") << ','
                          << std::setprecision(9) << results[mode].threshold << ','
                          << results[mode].raw_candidates << ',' << results[mode].accepted_candidates << ','
                          << results[mode].clusters << ',' << results[mode].max_cluster << ','
                          << (results[mode].predicted ? 1 : 0) << ','
                          << std::fixed << std::setprecision(3) << elapsed << '\n';
            }
        } catch (const std::exception& error) {
            std::cerr << "ERROR," << argv[argument] << ',' << error.what() << '\n';
            return 1;
        }
    }
    return 0;
}
#endif
