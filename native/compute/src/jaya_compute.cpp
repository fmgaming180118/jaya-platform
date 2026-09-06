#include "jaya_compute.h"

#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>

namespace {

constexpr std::size_t kMaxBinaryElements = 16U * 1024U * 1024U;
constexpr std::size_t kMaxTernaryElements = 64U * 1024U * 1024U;
constexpr std::size_t kMaxTernaryOperations = 1U << 30U;

bool checked_product(std::size_t left, std::size_t right, std::size_t limit) {
    return left != 0U && right != 0U && left <= limit / right;
}

std::uint64_t tail_mask(std::size_t bits) {
    return bits == 64U ? std::numeric_limits<std::uint64_t>::max()
                       : (std::uint64_t{1} << bits) - 1U;
}

}  // namespace

extern "C" {

std::uint32_t jaya_compute_abi_version(void) {
    return 1U;
}

const char *jaya_compute_provider_id(void) {
    return "jaya-cpp20-cpu-v1";
}

std::int32_t jaya_binary_dot_i8(
    const std::int8_t *left,
    const std::int8_t *right,
    std::size_t length,
    std::int64_t *dot_product,
    std::uint64_t *matches
) {
    if (left == nullptr || right == nullptr || dot_product == nullptr || matches == nullptr) {
        return JAYA_COMPUTE_NULL_POINTER;
    }
    if (length == 0U) {
        return JAYA_COMPUTE_INVALID_SIZE;
    }
    if (length > kMaxBinaryElements) {
        return JAYA_COMPUTE_RESOURCE_LIMIT;
    }

    std::uint64_t match_count = 0U;
    for (std::size_t offset = 0U; offset < length; offset += 64U) {
        const std::size_t block_bits = (length - offset < 64U) ? length - offset : 64U;
        std::uint64_t left_bits = 0U;
        std::uint64_t right_bits = 0U;
        for (std::size_t index = 0U; index < block_bits; ++index) {
            const std::int8_t left_value = left[offset + index];
            const std::int8_t right_value = right[offset + index];
            if ((left_value != -1 && left_value != 1) ||
                (right_value != -1 && right_value != 1)) {
                return JAYA_COMPUTE_INVALID_VALUE;
            }
            left_bits |= static_cast<std::uint64_t>(left_value == 1) << index;
            right_bits |= static_cast<std::uint64_t>(right_value == 1) << index;
        }
        const std::uint64_t equal_bits = ~(left_bits ^ right_bits) & tail_mask(block_bits);
        match_count += std::popcount(equal_bits);
    }

    *matches = match_count;
    *dot_product = static_cast<std::int64_t>(2U * match_count) -
                   static_cast<std::int64_t>(length);
    return JAYA_COMPUTE_OK;
}

std::int32_t jaya_binary_pack_i8(
    const std::int8_t *values,
    std::size_t length,
    std::uint8_t *output,
    std::size_t output_size
) {
    if (values == nullptr || output == nullptr) {
        return JAYA_COMPUTE_NULL_POINTER;
    }
    if (length == 0U || output_size != (length + 7U) / 8U) {
        return JAYA_COMPUTE_INVALID_SIZE;
    }
    if (length > kMaxBinaryElements) {
        return JAYA_COMPUTE_RESOURCE_LIMIT;
    }
    std::memset(output, 0, output_size);
    for (std::size_t index = 0U; index < length; ++index) {
        if (values[index] != -1 && values[index] != 1) {
            return JAYA_COMPUTE_INVALID_VALUE;
        }
        if (values[index] == 1) {
            output[index / 8U] |= static_cast<std::uint8_t>(1U << (index % 8U));
        }
    }
    return JAYA_COMPUTE_OK;
}

std::int32_t jaya_binary_dot_packed(
    const std::uint8_t *left,
    const std::uint8_t *right,
    std::size_t bit_length,
    std::int64_t *dot_product,
    std::uint64_t *matches
) {
    if (left == nullptr || right == nullptr || dot_product == nullptr || matches == nullptr) {
        return JAYA_COMPUTE_NULL_POINTER;
    }
    if (bit_length == 0U) {
        return JAYA_COMPUTE_INVALID_SIZE;
    }
    if (bit_length > kMaxBinaryElements) {
        return JAYA_COMPUTE_RESOURCE_LIMIT;
    }

    const std::size_t full_words = bit_length / 64U;
    const std::size_t remainder = bit_length % 64U;
    std::uint64_t match_count = 0U;
    for (std::size_t index = 0U; index < full_words; ++index) {
        std::uint64_t left_word = 0U;
        std::uint64_t right_word = 0U;
        std::memcpy(&left_word, left + index * 8U, sizeof(left_word));
        std::memcpy(&right_word, right + index * 8U, sizeof(right_word));
        match_count += std::popcount(~(left_word ^ right_word));
    }
    if (remainder != 0U) {
        const std::size_t tail_bytes = (remainder + 7U) / 8U;
        std::uint64_t left_word = 0U;
        std::uint64_t right_word = 0U;
        std::memcpy(&left_word, left + full_words * 8U, tail_bytes);
        std::memcpy(&right_word, right + full_words * 8U, tail_bytes);
        match_count += std::popcount(~(left_word ^ right_word) & tail_mask(remainder));
    }

    *matches = match_count;
    *dot_product = static_cast<std::int64_t>(2U * match_count) -
                   static_cast<std::int64_t>(bit_length);
    return JAYA_COMPUTE_OK;
}

std::int32_t jaya_ternary_gemm_f32_i8(
    const float *input,
    const std::int8_t *weights,
    std::size_t rows,
    std::size_t inner,
    std::size_t columns,
    float *output
) {
    if (input == nullptr || weights == nullptr || output == nullptr) {
        return JAYA_COMPUTE_NULL_POINTER;
    }
    if (rows == 0U || inner == 0U || columns == 0U) {
        return JAYA_COMPUTE_INVALID_SIZE;
    }
    if (!checked_product(inner, columns, kMaxTernaryElements) ||
        !checked_product(rows, columns, kMaxTernaryElements) ||
        !checked_product(rows, inner, kMaxTernaryOperations) ||
        rows * inner > kMaxTernaryOperations / columns) {
        return JAYA_COMPUTE_RESOURCE_LIMIT;
    }

    const std::size_t weight_count = inner * columns;
    for (std::size_t index = 0U; index < weight_count; ++index) {
        if (weights[index] < -1 || weights[index] > 1) {
            return JAYA_COMPUTE_INVALID_VALUE;
        }
    }
    std::memset(output, 0, rows * columns * sizeof(float));
    for (std::size_t row = 0U; row < rows; ++row) {
        float *output_row = output + row * columns;
        const float *input_row = input + row * inner;
        for (std::size_t feature = 0U; feature < inner; ++feature) {
            const float value = input_row[feature];
            const std::int8_t *weight_row = weights + feature * columns;
            for (std::size_t column = 0U; column < columns; ++column) {
                output_row[column] += value * static_cast<float>(weight_row[column]);
            }
        }
    }
    return JAYA_COMPUTE_OK;
}

}  // extern "C"
