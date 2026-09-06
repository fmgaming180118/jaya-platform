#ifndef JAYA_COMPUTE_H
#define JAYA_COMPUTE_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#if defined(JAYA_COMPUTE_BUILD)
#define JAYA_COMPUTE_API __declspec(dllexport)
#else
#define JAYA_COMPUTE_API __declspec(dllimport)
#endif
#else
#define JAYA_COMPUTE_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

enum jaya_compute_status {
    JAYA_COMPUTE_OK = 0,
    JAYA_COMPUTE_NULL_POINTER = -1,
    JAYA_COMPUTE_INVALID_SIZE = -2,
    JAYA_COMPUTE_INVALID_VALUE = -3,
    JAYA_COMPUTE_RESOURCE_LIMIT = -4
};

JAYA_COMPUTE_API uint32_t jaya_compute_abi_version(void);
JAYA_COMPUTE_API const char *jaya_compute_provider_id(void);

JAYA_COMPUTE_API int32_t jaya_binary_dot_i8(
    const int8_t *left,
    const int8_t *right,
    size_t length,
    int64_t *dot_product,
    uint64_t *matches
);

JAYA_COMPUTE_API int32_t jaya_binary_pack_i8(
    const int8_t *values,
    size_t length,
    uint8_t *output,
    size_t output_size
);

JAYA_COMPUTE_API int32_t jaya_binary_dot_packed(
    const uint8_t *left,
    const uint8_t *right,
    size_t bit_length,
    int64_t *dot_product,
    uint64_t *matches
);

JAYA_COMPUTE_API int32_t jaya_ternary_gemm_f32_i8(
    const float *input,
    const int8_t *weights,
    size_t rows,
    size_t inner,
    size_t columns,
    float *output
);

#ifdef __cplusplus
}
#endif

#endif
