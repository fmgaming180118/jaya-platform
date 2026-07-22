package com.example.jaya.skills

interface AiSkill {
    val name: String
    val description: String
    fun matches(input: String): Boolean
    suspend fun execute(input: String, sessionId: Long): SkillResult
}

data class SkillResult(
    val content: String,
    val attachedFileContent: String? = null,
    val attachedFileName: String? = null
)
