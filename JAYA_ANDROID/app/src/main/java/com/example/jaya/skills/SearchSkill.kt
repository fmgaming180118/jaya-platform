package com.example.jaya.skills

import java.net.URI

data class WebSearchItem(
    val title: String,
    val url: String,
    val snippet: String,
)

interface SearchProvider {
    suspend fun search(query: String, limit: Int): List<WebSearchItem>
}

class SearchSkill(
    private val provider: SearchProvider? = null,
) : AiSkill {
    override val name: String = "Web Search"
    override val description: String = "Mencari informasi terbaru dengan sumber yang dapat dibuka"

    override fun matches(input: String): Boolean {
        val lowercase = input.lowercase()
        return lowercase.contains("cari di internet") ||
            lowercase.contains("googling") ||
            lowercase.contains("search the web") ||
            lowercase.contains("berita terbaru tentang")
    }

    override suspend fun execute(input: String, sessionId: Long): SkillResult {
        val query = input
            .replace("cari di internet tentang", "", ignoreCase = true)
            .replace("cari di internet", "", ignoreCase = true)
            .replace("googling", "", ignoreCase = true)
            .replace("search the web", "", ignoreCase = true)
            .trim()
        if (query.isBlank()) {
            return SkillResult(
                content = "Masukkan topik pencarian yang jelas.",
                success = false,
                errorCode = "EMPTY_QUERY",
            )
        }
        val searchProvider = provider ?: return SkillResult(
            content = "Provider pencarian web belum dikonfigurasi; tidak ada hasil yang dibuat-buat.",
            success = false,
            errorCode = "SEARCH_PROVIDER_UNAVAILABLE",
        )
        return try {
            val results = searchProvider.search(query, MAX_RESULTS)
                .take(MAX_RESULTS)
                .filter(::hasSecureSource)
            if (results.isEmpty()) {
                SkillResult(
                    content = "Pencarian selesai tanpa sumber HTTPS yang dapat diverifikasi.",
                    success = false,
                    errorCode = "NO_VERIFIABLE_RESULTS",
                )
            } else {
                val rendered = results.mapIndexed { index, item ->
                    "${index + 1}. ${item.title.take(MAX_TITLE_CHARACTERS)}\n" +
                        "${item.snippet.take(MAX_SNIPPET_CHARACTERS)}\n${item.url}"
                }.joinToString("\n\n")
                SkillResult(content = "Hasil untuk '$query':\n\n$rendered")
            }
        } catch (error: Exception) {
            SkillResult(
                content = "Provider pencarian gagal merespons.",
                success = false,
                errorCode = "SEARCH_PROVIDER_FAILED",
            )
        }
    }

    private fun hasSecureSource(item: WebSearchItem): Boolean = try {
        val uri = URI(item.url)
        item.title.isNotBlank() &&
            uri.scheme.equals("https", ignoreCase = true) &&
            !uri.host.isNullOrBlank() &&
            uri.userInfo == null
    } catch (error: Exception) {
        false
    }

    private companion object {
        const val MAX_RESULTS = 5
        const val MAX_SNIPPET_CHARACTERS = 500
        const val MAX_TITLE_CHARACTERS = 200
    }
}