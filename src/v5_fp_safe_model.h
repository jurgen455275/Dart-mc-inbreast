#pragma once

// Supresor conservador aprendido sin modificar el umbral adaptativo.
// Reglas relativas seleccionadas en desarrollo con margen de seguridad
// de 0.5 IQR alrededor del soporte de verdaderos positivos.
namespace inbreast_v5_fp_safe_model {
inline constexpr double area_fraction_sum_upper = 0.0004268930897028592;
inline constexpr double y_std_upper = 0.4268182283845227;
inline constexpr double positive_support_margin_iqr = 0.5;
}
