package com.example.jaya.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.ForeignKey
import androidx.room.Index

@Entity(tableName = "chat_sessions")
data class ChatSession(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val title: String,
    val createdAt: Long = System.currentTimeMillis()
)

@Entity(
    tableName = "chat_files",
    foreignKeys = [
        ForeignKey(
            entity = ChatSession::class,
            parentColumns = ["id"],
            childColumns = ["sessionId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index(value = ["sessionId"])]
)
data class ChatFile(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sessionId: Long,
    val fileName: String,
    val filePath: String,
    val fileType: String, // e.g., "text/plain", "application/pdf"
    val contentSummary: String, // For RAG indexing
    val isGlobal: Boolean = false, // If true, available to all chat sessions
    val createdAt: Long = System.currentTimeMillis()
)

@Entity(
    tableName = "chat_messages",
    foreignKeys = [
        ForeignKey(
            entity = ChatSession::class,
            parentColumns = ["id"],
            childColumns = ["sessionId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index(value = ["sessionId"])]
)
data class LocalChatMessage(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sessionId: Long,
    val role: String,
    val content: String,
    val attachedFileId: Long? = null,
    val isCompacted: Boolean = false, // True if this message is part of a summary
    val timestamp: Long = System.currentTimeMillis()
)

@Entity(tableName = "user_preferences")
data class UserPreference(
    @PrimaryKey val key: String,
    val value: String
)

@Entity(
    tableName = "file_embeddings",
    foreignKeys = [
        ForeignKey(
            entity = ChatFile::class,
            parentColumns = ["id"],
            childColumns = ["fileId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [Index(value = ["fileId"])]
)
data class FileEmbedding(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val fileId: Long,
    val embedding: String, // Stored as comma-separated floats
    val textChunk: String
)
