"""Frozen constants shared by the #282 execution and diagnostic scripts."""

MODEL_SEEDS = tuple(282_101 + offset for offset in range(5))

CELL_FEATURES = (
    "native_handicap_line",
    "n_available_books",
    "mapping_accepted",
    "probability",
    "cell_value",
    "value_q10",
    "value_q90",
    "divergence",
    "predicted_sp_proxy",
    "cell_value_rank",
    "match_best_value",
    "match_value_rank",
)

FIXED_BASELINE_KEYS = {
    "FIXED_N7_K8_TOP_CELL_VALUE": "SALL_OVALUE_N7_TOP_VALUE_K8",
    "FIXED_N7_K8_TOP_MARKET": "SALL_OMARKET_N7_TOP_VALUE_K8",
    "FIXED_N7_K8_TOP_DIVERGENCE": "SALL_ODIVVALUE_N7_TOP_VALUE_K8",
    "FIXED_N7_K8_WR_CELL_VALUE": "SALL_OVALUE_N7_WEIGHTED_WR_K8",
    "FIXED_N7_K8_WOR_CELL_VALUE": "SALL_OVALUE_N7_WEIGHTED_WOR_K8",
}
