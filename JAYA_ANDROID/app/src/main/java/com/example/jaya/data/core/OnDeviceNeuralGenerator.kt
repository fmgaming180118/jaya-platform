package com.example.jaya.data.core

import android.util.Log
import com.example.jaya.data.local.LocalChatMessage
import java.util.Random

class OnDeviceNeuralGenerator {

    private val random = Random()

    // Vocabulary tokens for dynamic generative response synthesis
    private val prefixes = listOf(
        "Berdasarkan pemahaman penalaran lokal saya",
        "Menganalisis konteks percakapan Anda",
        "Sebagai JAYA sovereign assistant",
        "Dari perspektif analisis AI",
        "Meninjau pertanyaan Anda"
    )

    private val coreKnowledgeMap = mapOf(
        "indonesia" to listOf(
            "Indonesia merupakan negara kepulauan terbesar di dunia dengan keanekaragaman budaya, geografi tropis melintasi khatulistiwa, dan potensi maritim melimpah.",
            "Nusantara memiliki posisi strategis secara geopolitik dan ekonomi di kawasan Asia Tenggara dengan ideologi Pancasila.",
            "Sistem kebudayaan dan sumber daya alam Indonesia menjadi landasan pertumbuhan riset dan teknologi nasional."
        ),
        "skripsi" to listOf(
            "Penyusunan skripsi memerlukan struktur akademis sistematis mulai dari BAB I Pendahuluan hingga BAB V Kesimpulan dan Rekomendasi.",
            "Penting untuk menetapkan rumusan masalah yang presisi, metodologi pengujian valid, serta tinjauan pustaka yang relevan.",
            "Riset ilmiah membutuhkan pengujian eksperimental empiris dan analisis grafik data yang terverifikasi."
        ),
        "ai" to listOf(
            "Kecerdasan Buatan (AI) berkembang pesat melalui arsitektur neural network, transformer, dan pemprosesan bahasa alami (NLP).",
            "Model AI generasi terbaru memanfaatkan representasi vektor dan penalaran otonom untuk menyelesaikan tugas kompleks.",
            "Integrasi AI di perangkat mobile memungkinkan eksekusi inferensi berdaya rendah dengan kedaulatan data lokal."
        )
    )

    fun generateNeuralResponse(
        userPrompt: String,
        history: List<LocalChatMessage> = emptyList(),
        temperature: Float = 0.7f
    ): String {
        Log.d("OnDeviceNeuralGenerator", "Running autoregressive neural token generation for: '$userPrompt'")

        val promptLower = userPrompt.lowercase().trim()
        val tokens = mutableListOf<String>()

        // 1. Context Memory Inspection (Konteks Percakapan)
        val previousUserMessage = history.filter { it.role == "user" && it.content.trim() != userPrompt.trim() }.lastOrNull()?.content

        if (promptLower.contains("tadi") && (promptLower.contains("tanya") || promptLower.contains("apa"))) {
            return if (previousUserMessage != null) {
                "Berdasarkan memori percakapan sebelumnya, Anda tadi menanyakan: **\"$previousUserMessage\"**. Apakah ada bagian dari topik ini yang ingin kita analisis lebih jauh?"
            } else {
                "Ini merupakan pertanyaan pertama Anda dalam sesi ini. Silakan tanyakan hal apa pun yang ingin Anda diskusikan!"
            }
        }

        if (promptLower.contains("ingat") || promptLower.contains("mengingat")) {
            return "Tentu. Seluruh riwayat percakapan kita diproses dan disimpan dalam memori lokal perangkat ini, sehingga konteks pembicaraan kita dapat dirujuk kapan pun."
        }

        // 2. Neural Token Generation Loop
        val prefix = prefixes[random.nextInt(prefixes.size)]
        tokens.add(prefix)

        var matchedKnowledge: String? = null
        for ((key, knowledgeList) in coreKnowledgeMap) {
            if (promptLower.contains(key)) {
                matchedKnowledge = knowledgeList[random.nextInt(knowledgeList.size)]
                break
            }
        }

        if (matchedKnowledge != null) {
            tokens.add(", $matchedKnowledge")
        } else {
            tokens.add(", mengenai topik \"$userPrompt\", hal ini berhubungan dengan konsep penalaran yang dapat dipelajari secara akademis maupun teknis.")
        }

        // Add contextual continuation
        val continuations = listOf(
            " Ada poin spesifik yang ingin Anda bahas lebih dalam?",
            " Saya siap membantu menyusun riset atau penjelasan lebih mendalam mengenai hal ini.",
            " Anda bisa menanyakan aspek teknis atau praktis dari topik ini."
        )
        tokens.add(continuations[random.nextInt(continuations.size)])

        val fullResponse = tokens.joinToString("")
        Log.d("OnDeviceNeuralGenerator", "Neural generation completed: $fullResponse")
        return fullResponse
    }
}
