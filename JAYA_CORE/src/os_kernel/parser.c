/* parser.c - JAYA OS Text to Vector Parser */
typedef float f32;
typedef unsigned int u32;

// ASCII character count
#define CHAR_MAP_SIZE 256
#define RECORD_VEC_LEN 64

extern f32 cosine_similarity(const f32 *vec_a, const f32 *vec_b, int len);

void text_to_vector(const char* text, f32* out_vec) {
    // Very primitive char-bag to vector conversion
    for(int i = 0; i < RECORD_VEC_LEN; i++) {
        out_vec[i] = 0.0f;
    }

    int idx = 0;
    while(text[idx] != '\0') {
        unsigned char c = (unsigned char)text[idx];
        if (c < CHAR_MAP_SIZE) {
            // Hash down to vec len
            int bin = c % RECORD_VEC_LEN;
            out_vec[bin] += 1.0f;
        }
        idx++;
    }
}

// Basic RAG search against loaded VFS
struct vector_record {
    u32 id;
    f32 vector[RECORD_VEC_LEN];
    char text[512 - sizeof(u32) - (RECORD_VEC_LEN * sizeof(f32))];
};

// Assuming max records 64
extern struct vector_record db[64];
extern int record_count;

int rag_search(const char* query, f32 threshold, char* out_text) {
    f32 q_vec[RECORD_VEC_LEN];
    text_to_vector(query, q_vec);

    int best_match = -1;
    f32 max_sim = -1.0f;

    for (int i = 0; i < record_count; i++) {
        f32 sim = cosine_similarity(q_vec, db[i].vector, RECORD_VEC_LEN);
        if (sim > max_sim && sim >= threshold) {
            max_sim = sim;
            best_match = i;
        }
    }

    if (best_match != -1) {
        int idx = 0;
        while(db[best_match].text[idx] != '\0') {
            out_text[idx] = db[best_match].text[idx];
            idx++;
        }
        out_text[idx] = '\0';
        return 1;
    }

    return 0; // No match found
}
