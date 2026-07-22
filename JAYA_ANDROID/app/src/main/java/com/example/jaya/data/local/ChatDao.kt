package com.example.jaya.data.local

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface ChatDao {
    @Query("SELECT * FROM chat_sessions ORDER BY createdAt DESC")
    fun getAllSessions(): Flow<List<ChatSession>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertSession(session: ChatSession): Long

    @Update
    suspend fun updateSession(session: ChatSession)

    @Delete
    suspend fun deleteSession(session: ChatSession)

    @Query("SELECT * FROM chat_messages WHERE sessionId = :sessionId AND isCompacted = 0 ORDER BY timestamp ASC")
    fun getMessagesForSession(sessionId: Long): Flow<List<LocalChatMessage>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertMessage(message: LocalChatMessage): Long

    @Query("SELECT * FROM chat_messages WHERE sessionId = :sessionId AND content LIKE :query")
    suspend fun searchMessages(sessionId: Long, query: String): List<LocalChatMessage>

    @Query("UPDATE chat_messages SET isCompacted = 1 WHERE sessionId = :sessionId AND timestamp <= :timestamp")
    suspend fun markMessagesAsCompacted(sessionId: Long, timestamp: Long)

    // File Operations
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertFile(file: ChatFile): Long

    @Update
    suspend fun updateFile(file: ChatFile)

    @Query("SELECT * FROM chat_files WHERE sessionId = :sessionId OR isGlobal = 1")
    fun getFilesForSession(sessionId: Long): Flow<List<ChatFile>>

    @Query("SELECT * FROM chat_files WHERE id = :fileId")
    suspend fun getFileById(fileId: Long): ChatFile?

    @Query("SELECT * FROM chat_files WHERE sessionId = :sessionId AND fileName = :fileName LIMIT 1")
    suspend fun getFileBySessionAndName(sessionId: Long, fileName: String): ChatFile?

    @Query("SELECT * FROM chat_files WHERE (sessionId = :sessionId OR isGlobal = 1) AND (fileName LIKE :query OR contentSummary LIKE :query)")
    suspend fun searchFiles(sessionId: Long, query: String): List<ChatFile>

    // User Preferences / Global Memory
    @Query("SELECT * FROM user_preferences")
    fun getAllUserPreferences(): Flow<List<UserPreference>>

    @Query("SELECT * FROM user_preferences WHERE `key` = :key LIMIT 1")
    suspend fun getPreference(key: String): UserPreference?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertUserPreference(pref: UserPreference)

    // Vector RAG
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertEmbeddings(embeddings: List<FileEmbedding>)

    @Query("SELECT * FROM file_embeddings WHERE fileId IN (SELECT id FROM chat_files WHERE sessionId = :sessionId OR isGlobal = 1)")
    suspend fun getRelevantEmbeddings(sessionId: Long): List<FileEmbedding>
}
