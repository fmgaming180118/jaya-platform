import { API_BASE_URL, IS_DEV } from '../config/env';

// API log bus — DevPanel subscribes to ini
let _logCallback = null;
export const setApiLogCallback = (fn) => { _logCallback = fn; };

/**
 * Wrapper fetch yang otomatis mencatat request ke DevPanel log (hanya di DEV)
 */
async function apiFetch(url, options = {}) {
    const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;
    const method = options.method || 'GET';
    const start = Date.now();

    try {
        const res = await fetch(fullUrl, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        });
        const duration = Date.now() - start;

        if (IS_DEV && _logCallback) {
            _logCallback({
                url: fullUrl, method, status: res.status, ok: res.ok, duration, timestamp: Date.now(),
            });
        }

        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        return res.json();
    } catch (err) {
        const duration = Date.now() - start;
        if (IS_DEV && _logCallback) {
            _logCallback({ url: fullUrl, method, status: 0, ok: false, duration, timestamp: Date.now() });
        }
        throw err;
    }
}

/**
 * Multipart fetch — untuk upload file (tidak pakai JSON header)
 */
async function apiFetchMultipart(url, formData) {
    const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;
    const start = Date.now();
    try {
        const res = await fetch(fullUrl, {
            method: 'POST',
            body: formData,
            // JANGAN set Content-Type — browser otomatis set boundary multipart
        });
        const duration = Date.now() - start;
        if (IS_DEV && _logCallback) {
            _logCallback({ url: fullUrl, method: 'POST', status: res.status, ok: res.ok, duration, timestamp: Date.now() });
        }
        if (!res.ok) {
            const errText = await res.text();
            throw new Error(`HTTP ${res.status}: ${errText}`);
        }
        return res.json();
    } catch (err) {
        if (IS_DEV && _logCallback) {
            _logCallback({ url: fullUrl, method: 'POST', status: 0, ok: false, duration: 0, timestamp: Date.now() });
        }
        throw err;
    }
}

export const api = {
    // --- Workspace Management ---
    listWorkspaces: () => apiFetch('/workspaces'),

    createWorkspace: (name) => apiFetch(
        `/workspaces/create?name=${encodeURIComponent(name)}`,
        { method: 'POST' }
    ),

    deleteWorkspace: (id) => apiFetch(
        `/workspaces/${encodeURIComponent(id)}`,
        { method: 'DELETE' }
    ),

    // --- Health Check ---
    getHealth: async () => {
        try { return await apiFetch('/'); }
        catch { return { status: 'offline' }; }
    },

    // --- Chat ---
    chat: (message, contextFiles = [], workspaceId = 'default') =>
        apiFetch('/chat', {
            method: 'POST',
            body: JSON.stringify({ message, context_files: contextFiles, workspace_id: workspaceId }),
        }),

    // --- Research ---
    startResearch: (topic, focusAreas = '', workspaceId = 'default') =>
        apiFetch('/research/autonomous', {
            method: 'POST',
            body: JSON.stringify({ topic, focus_areas: focusAreas, workspace_id: workspaceId }),
        }),

    startRecursiveResearch: (topic, workspaceId = 'default', maxIterations = 3) =>
        apiFetch('/research/recursive', {
            method: 'POST',
            body: JSON.stringify({ topic, workspace_id: workspaceId, max_iterations: maxIterations }),
        }),

    // --- Journal Search ---
    searchJournals: (query, maxPapers = 3) =>
        apiFetch('/research/journals', {
            method: 'POST',
            body: JSON.stringify({ query, max_papers: maxPapers }),
        }),

    // --- Documents ---
    ingestDocument: (filePath, workspaceId = 'default') =>
        apiFetch('/ingest', {
            method: 'POST',
            body: JSON.stringify({ file_path: filePath, workspace_id: workspaceId }),
        }),

    ingestVideo: (url) =>
        apiFetch('/ingest/video', {
            method: 'POST',
            body: JSON.stringify({ url }),
        }),

    listDocuments: (workspaceId = 'default') =>
        apiFetch(`/documents?workspace_id=${workspaceId}`),

    viewDocumentUrl: (workspaceId, filename) =>
        `${API_BASE_URL}/documents/view/${encodeURIComponent(workspaceId)}/${encodeURIComponent(filename)}`,

    deleteDocument: (workspaceId, filename) =>
        apiFetch(`/documents/delete/${encodeURIComponent(workspaceId)}/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        }),

    uploadDocumentToWorkspace: (file, workspaceId = 'default') => {
        const formData = new FormData();
        formData.append('file', file);
        return apiFetchMultipart(`/documents/upload/${encodeURIComponent(workspaceId)}`, formData);
    },

    // --- Knowledge Graph ---
    getGraph: (workspaceId = 'default') =>
        apiFetch(`/graph?workspace_id=${workspaceId}`),

    // --- Citation Graph (Journal → References mapping) ---
    getCitationGraph: () =>
        apiFetch('/research/journals/citation-graph'),

    getCachedJournals: () =>
        apiFetch('/research/journals/cache'),

    findCachedJournal: (query, topK = 5) =>
        apiFetch('/research/journals/find-cached', {
            method: 'POST',
            body: JSON.stringify({ query, top_k: topK }),
        }),

    // --- History ---
    getHistory: () => apiFetch('/history'),

    // --- Academic ---
    academicGaps: (topic) =>
        apiFetch(`/academic/gaps?topic=${encodeURIComponent(topic)}`, { method: 'POST' }),

    // ============================================================
    // THESIS UPLOAD & ANALYSIS
    // ============================================================

    /**
     * Upload file PDF Tugas Akhir ke backend.
     * @param {File} file - File object dari input/drag-drop
     * @param {string} workspaceId
     * @returns {{ session_id, file_name, char_count, status, message }}
     */
    uploadThesis: (file, workspaceId = 'default') => {
        const formData = new FormData();
        formData.append('file', file);
        return apiFetchMultipart(
            `/thesis/upload?workspace_id=${encodeURIComponent(workspaceId)}`,
            formData
        );
    },

    /**
     * Mulai analisis komprehensif setelah upload.
     * @param {string} sessionId - dari uploadThesis response
     */
    analyzeThesis: (sessionId) =>
        apiFetch(`/thesis/analyze/${sessionId}`, { method: 'POST', body: '{}' }),

    /**
     * Poll status analisis.
     * @param {string} sessionId
     * @returns {{ status, progress, steps, analysis, error }}
     */
    getThesisStatus: (sessionId) =>
        apiFetch(`/thesis/status/${sessionId}`),

    /**
     * Tanya-jawab langsung dengan isi dokumen TA via RAG.
     * @param {string} sessionId
     * @param {string} message
     * @param {string} workspaceId
     */
    chatWithThesis: (sessionId, message, workspaceId = 'default') =>
        apiFetch(`/thesis/chat/${sessionId}`, {
            method: 'POST',
            body: JSON.stringify({ message, workspace_id: workspaceId }),
        }),

    /**
     * Revisi bagian teks TA berdasarkan instruksi.
     * @param {string} sessionId
     * @param {string} sectionText - teks bagian TA yang akan direvisi
     * @param {string} instruction - instruksi revisi dari user
     * @param {string} revisionType - 'general' | 'formal' | 'citation' | 'methodology'
     */
    reviseThesisSection: (sessionId, sectionText, instruction, revisionType = 'general') =>
        apiFetch(`/thesis/revise/${sessionId}`, {
            method: 'POST',
            body: JSON.stringify({
                section_text: sectionText,
                instruction,
                revision_type: revisionType,
            }),
        }),

    /**
     * Cari jurnal relevan berdasarkan topik TA yang sudah dianalisis.
     * @param {string} sessionId
     * @param {number} maxPapers
     */
    findRelevantJournals: (sessionId, maxPapers = 10) =>
        apiFetch(`/thesis/journals/${sessionId}?max_papers=${maxPapers}`, { method: 'POST' }),

    /**
     * Download laporan analisis lengkap sebagai file Markdown.
     * Trigger browser download langsung.
     * @param {string} sessionId
     * @param {string} fileName - nama file yang disarankan
     */
    exportThesisReport: async (sessionId, fileName = 'laporan_ta.md') => {
        const fullUrl = `${API_BASE_URL}/thesis/export/${sessionId}`;
        const res = await fetch(fullUrl);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        return { success: true };
    },

    // --- Dynamic Model Settings ---
    getModels: () => apiFetch('/config/models'),
    updateModel: (modelName) => apiFetch('/config/models', {
        method: 'POST',
        body: JSON.stringify({ model_name: modelName })
    }),
};

export default api;
