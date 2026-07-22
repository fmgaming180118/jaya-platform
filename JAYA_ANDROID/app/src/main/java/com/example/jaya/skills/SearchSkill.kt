package com.example.jaya.skills

class SearchSkill : AiSkill {
    override val name: String = "Web Search"
    override val description: String = "Mencari informasi terbaru di internet"

    override fun matches(input: String): Boolean {
        val lowercase = input.lowercase()
        return lowercase.contains("cari di internet") || 
               lowercase.contains("googling") || 
               lowercase.contains("search the web") ||
               lowercase.contains("berita terbaru tentang")
    }

    override suspend fun execute(input: String, sessionId: Long): SkillResult {
        // Logika Skill: Di sini kita mensimulasikan pemanggilan API Pencarian (seperti Serper.dev atau Google Custom Search)
        val query = input.replace("cari di internet tentang", "", ignoreCase = true)
                         .replace("googling", "", ignoreCase = true)
                         .trim()

        // Simulasi hasil pencarian
        val searchResults = """
            [Sourced from Jaya Web Crawler]
            1. Info Utama: $query sedang menjadi topik hangat di komunitas AI.
            2. Berita Terkait: Implementasi terbaru menunjukkan peningkatan efisiensi sebesar 40%.
            3. Referensi: NVIDIA baru saja merilis blueprint terkait $query di katalog NIM mereka.
        """.trimIndent()

        return SkillResult(
            content = "Saya telah melakukan pencarian cepat di internet untuk '$query'. Berikut ringkasannya:\n\n$searchResults\n\nApakah Anda ingin saya membuatkan dokumen teknis berdasarkan hasil ini?"
        )
    }
}
