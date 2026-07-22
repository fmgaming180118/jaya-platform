package com.example.jaya.skills

import android.content.Context
import org.json.JSONObject

class BlueprintSkill(private val context: Context) : AiSkill {
    override val name: String = "NVIDIA Blueprint Skills"
    override val description: String = "Provides information and generates documents based on NVIDIA AI Blueprints"

    private val skillsRegistry: JSONObject by lazy {
        val jsonString = context.assets.open("skills.sh.json").bufferedReader().use { it.readText() }
        JSONObject(jsonString)
    }

    override fun matches(input: String): Boolean {
        val lowercase = input.lowercase()
        return lowercase.contains("nvidia skill") || 
               lowercase.contains("blueprint") || 
               lowercase.contains("daftar skill") ||
               lowercase.contains("bicara") ||
               lowercase.contains("voice agent")
    }

    override suspend fun execute(input: String, sessionId: Long): SkillResult {
        val groups = skillsRegistry.getJSONArray("groupings")
        val lowercaseInput = input.lowercase()
        
        // Handle Speaking/Voice Agent specific request
        if (lowercaseInput.contains("bicara") || lowercaseInput.contains("voice agent")) {
            val promptContent = try {
                context.assets.open("blueprints/voice_agent_prompts.yaml").bufferedReader().use { it.readText() }
            } catch (e: Exception) {
                "Voice Agent blueprint prompts unavailable."
            }
            
            return if (lowercaseInput.contains("buat") || lowercaseInput.contains("create")) {
                SkillResult(
                    content = "Tentu! Saya telah menyiapkan blueprint 'Nemotron Voice Agent' untuk Anda. Dokumen teknis mengenai prompt sistem dan konfigurasi suara telah disimpan.",
                    attachedFileContent = promptContent,
                    attachedFileName = "voice_agent_blueprint.yaml"
                )
            } else {
                SkillResult(
                    content = "Saya memiliki blueprint NVIDIA untuk sistem berbicara (Voice Agent). Blueprint ini menggunakan model Nemotron untuk interaksi suara low-latency. Apakah Anda ingin saya membuatkan dokumen konfigurasinya?"
                )
            }
        }

        var foundSkill: String? = null
        var foundDoc: String? = null

        // Search for specific skill mention
        for (i in 0 until groups.length()) {
            val group = groups.getJSONObject(i)
            val skills = group.getJSONArray("skills")
            for (j in 0 until skills.length()) {
                val skillName = skills.getString(j)
                if (lowercaseInput.contains(skillName.lowercase())) {
                    foundSkill = skillName
                    try {
                        val docPath = "skills_docs/$skillName.md"
                        context.assets.open(docPath).use {
                            foundDoc = it.bufferedReader().use { reader -> reader.readText() }
                        }
                    } catch (e: Exception) {}
                }
            }
        }

        if (foundSkill != null) {
            if (lowercaseInput.contains("buat") || lowercaseInput.contains("create")) {
                val docName = "${foundSkill}_blueprint.txt"
                val docContent = foundDoc ?: "NVIDIA BLUEPRINT SKILL DOCUMENT\nSkill: $foundSkill\nSession: $sessionId"
                return SkillResult(
                    content = "Saya telah menemukan blueprint untuk '$foundSkill' dan membuatkan dokumen teknisnya untuk Anda.",
                    attachedFileContent = docContent,
                    attachedFileName = docName
                )
            } else {
                return SkillResult(
                    content = "Informasi Skill '$foundSkill':\n\n${foundDoc ?: "Blueprint untuk skill ini tersedia di library NVIDIA."}"
                )
            }
        }

        val sb = StringBuilder()
        sb.append("Berikut adalah kategori NVIDIA Blueprints & Skills yang tersedia:\n\n")
        for (i in 0 until groups.length()) {
            val group = groups.getJSONObject(i)
            sb.append("🔹 *${group.getString("title")}*\n")
            sb.append("${group.getString("description")}\n\n")
        }
        sb.append("💡 *Pro Tip*: Anda juga bisa bertanya tentang 'Voice Agent' atau blueprint untuk 'Bicara dengan AI'.")
        
        return SkillResult(content = sb.toString())
    }
}
