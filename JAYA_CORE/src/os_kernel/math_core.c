/* math_core.c - JAYA OS Pure C Math Implementation */
typedef float f32;
typedef unsigned int u32;

// Approximate fast inverse square root for normalizations
f32 fast_inv_sqrt(f32 number) {
    union {
        f32 f;
        long i;
    } conv;

    f32 x2;
    const f32 threehalfs = 1.5F;

    x2 = number * 0.5F;
    conv.f = number;
    conv.i = 0x5f3759df - ( conv.i >> 1 );               // what the fuck?
    conv.f = conv.f * ( threehalfs - ( x2 * conv.f * conv.f ) );   // 1st iteration

    return conv.f;
}

// Dot product between two vectors
f32 dot_product(const f32 *vec_a, const f32 *vec_b, int len) {
    f32 result = 0.0f;
    for (int i = 0; i < len; i++) {
        result += vec_a[i] * vec_b[i];
    }
    return result;
}

// L2 Norm calculation utilizing fast inverse sqrt
f32 l2_norm(const f32 *vec, int len) {
    f32 sq_sum = 0.0f;
    for (int i = 0; i < len; i++) {
        sq_sum += vec[i] * vec[i];
    }
    return 1.0f / fast_inv_sqrt(sq_sum);
}

// Cosine similarity
f32 cosine_similarity(const f32 *vec_a, const f32 *vec_b, int len) {
    f32 dot = dot_product(vec_a, vec_b, len);
    f32 norm_a = l2_norm(vec_a, len);
    f32 norm_b = l2_norm(vec_b, len);

    if (norm_a == 0.0f || norm_b == 0.0f) {
        return 0.0f;
    }
    return dot / (norm_a * norm_b);
}
