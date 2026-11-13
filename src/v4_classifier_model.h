#pragma once

#include <array>
#include <cstddef>

namespace inbreast_v4_model {

inline constexpr std::size_t feature_count = 23;
inline constexpr double intercept = 0.22920117543900509;
inline constexpr double decision_threshold = 0.51692545459541839;
inline constexpr double regularization = 0.10000000000000001;

inline constexpr std::array<double, feature_count> means = {
        0.3444311650164415,
        0.65815176937839792,
        0.15533850081430228,
        0.64365744826519988,
        0.61860151137408481,
        45458.947420236276,
        38242.079382842952,
        1.5174093925931775,
        1.0923650418906314,
        0.45098796167849714,
        0.39750032267248692,
        0.44052518458591472,
        0.86471567858283227,
        0.26238243944675366,
        0.16577592850263595,
        0.34168328160519412,
        0.2810906489490142,
        0.039367185706360122,
        0.07055394043134143,
        0.15953963966861798,
        0.57512971427699344,
        0.06769893888132536,
        0.037218742994406188
};

inline constexpr std::array<double, feature_count> scales = {
        0.22973729633546833,
        0.5376897708552828,
        0.19795094844054179,
        0.42424026836791845,
        0.40671768616576615,
        59475.257341285054,
        48702.05831320474,
        1.3437261048402318,
        0.83104931761967682,
        0.3068116605891687,
        0.26634983517229854,
        0.39319946485869928,
        0.74319660481896832,
        0.3073730781766143,
        0.32200210007558538,
        0.28907933913303085,
        0.25327701984784629,
        0.059808417902583726,
        0.098030439950889073,
        0.14610149018295679,
        0.39011144579635953,
        0.074016375571234277,
        0.035440955523114145
};

inline constexpr std::array<double, feature_count> coefficients = {
        -0.14404298735331,
        -0.42298458278640499,
        0.17705041857054912,
        -0.046682894372827133,
        -0.061967445217601794,
        -0.11109428287103375,
        -0.12487082103711465,
        -0.0010677008594564511,
        -0.05713008936317706,
        -0.069315309884532758,
        -0.10715725778788919,
        -0.15549497781887356,
        0.17347741602492214,
        0.027540913884672214,
        0.16500143699038958,
        0.064454453012430912,
        0.032739498245466465,
        0.1108387554138707,
        0.02964536178986946,
        0.22575485601299927,
        -0.079592884707781142,
        0.23630976129459855,
        0.18205407824263811
};

// Orden de caracteristicas:
// adaptive_threshold, raw_density_log, accepted_density_log, score_max, score_mean, dog_max, dog_mean, contrast_max, contrast_mean, compactness_max, compactness_mean, cluster_support, cluster_count_log, accept_fraction, score_gap, x_mean, y_mean, x_std, y_std, border_mean, evidence_max, area_max_log, area_mean_log
// El punto de decision es probabilistico y no es un corte de intensidad.
// Nucleo primario preservado: T=min(0.95,mean_M(D)+20*std_M(D)); D>T.

}  // namespace inbreast_v4_model
