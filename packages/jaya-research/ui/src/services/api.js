import { API_BASE_URL, IS_DEV } from '../config/env.js';
import {
    buildIngestTextRequest,
    buildRecursiveResearchRequest,
} from './contracts.js';

// API log bus — DevPanel subscribes to ini
let _logCallback = null;
export const setApiLogCallback = (fn) => { _logCallback = fn; };

// Credentials remain in memory and are never compiled into VITE_* variables.
let _apiAccessToken = null;

export class ApiError extends Error {
    constructor(status, code, message) {
        super(message);
        this.name = 'ApiError';
        this.status = status;
        this.code = code;
    }
}

export const setApiAccessToken = (token) => {
    if (
        typeof token !== 'string'
        || token.length < 1
        || token.length > 4_096
        || token !== token.trim()
        || Array.from(token).some(
            (character) => /\s/u.test(character) || character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127
        )
    ) {
        throw new TypeError('API access token must contain 1-4096 non-whitespace characters');
    }
    _apiAccessToken = token;
};

export const clearApiAccessToken = () => {
    _apiAccessToken = null;
};

export const hasApiAccessToken = () => _apiAccessToken !== null;

const authorizationHeaders = () => (
    _apiAccessToken ? { Authorization: `Bearer ${_apiAccessToken}` } : {}
);

const responseError = async (response) => {
    let payload = null;
    try {
        payload = await response.json();
    } catch {
        // A non-JSON proxy response is represented by its HTTP status only.
    }
    const detail = payload?.error ?? payload?.detail;
    const code = typeof detail?.code === 'string'
        ? detail.code
        : `HTTP_${response.status}`;
    const message = typeof detail?.message === 'string'
        ? detail.message
        : typeof detail === 'string'
            ? detail
            : `Request failed with HTTP ${response.status}`;
    return new ApiError(response.status, code, message);
};

/**
 * Wrapper fetch yang otomatis mencatat request ke DevPanel log (hanya di DEV)
 */
async function apiFetch(url, options = {}) {
    const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;
    const method = options.method || 'GET';
    const start = Date.now();
    let responseReceived = false;

    try {
        const res = await fetch(fullUrl, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...authorizationHeaders(),
                ...(options.headers || {}),
            },
        });
        responseReceived = true;
        const duration = Date.now() - start;

        if (IS_DEV && _logCallback) {
            _logCallback({
                url: fullUrl, method, status: res.status, ok: res.ok, duration, timestamp: Date.now(),
            });
        }

        if (!res.ok) throw await responseError(res);
        if (res.status === 204) return null;
        return res.json();
    } catch (err) {
        const duration = Date.now() - start;
        if (!responseReceived && IS_DEV && _logCallback) {
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
    let responseReceived = false;
    try {
        const res = await fetch(fullUrl, {
            method: 'POST',
            body: formData,
            headers: authorizationHeaders(),
            // JANGAN set Content-Type — browser otomatis set boundary multipart
        });
        responseReceived = true;
        const duration = Date.now() - start;
        if (IS_DEV && _logCallback) {
            _logCallback({ url: fullUrl, method: 'POST', status: res.status, ok: res.ok, duration, timestamp: Date.now() });
        }
        if (!res.ok) throw await responseError(res);
        return res.json();
    } catch (err) {
        if (!responseReceived && IS_DEV && _logCallback) {
            _logCallback({ url: fullUrl, method: 'POST', status: 0, ok: false, duration: 0, timestamp: Date.now() });
        }
        throw err;
    }
}

async function apiFetchResource(url) {
    const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;
    const start = Date.now();
    let responseReceived = false;
    try {
        const res = await fetch(fullUrl, { headers: authorizationHeaders() });
        responseReceived = true;
        if (IS_DEV && _logCallback) {
            _logCallback({
                url: fullUrl,
                method: 'GET',
                status: res.status,
                ok: res.ok,
                duration: Date.now() - start,
                timestamp: Date.now(),
            });
        }
        if (!res.ok) throw await responseError(res);
        return res;
    } catch (error) {
        if (!responseReceived && IS_DEV && _logCallback) {
            _logCallback({
                url: fullUrl,
                method: 'GET',
                status: 0,
                ok: false,
                duration: Date.now() - start,
                timestamp: Date.now(),
            });
        }
        throw error;
    }
}

async function downloadResource(url, fileName) {
    const response = await apiFetchResource(url);
    const blobUrl = URL.createObjectURL(await response.blob());
    const anchor = document.createElement('a');
    try {
        anchor.href = blobUrl;
        anchor.download = fileName;
        document.body.appendChild(anchor);
        anchor.click();
    } finally {
        anchor.remove();
        URL.revokeObjectURL(blobUrl);
    }
    return { success: true };
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
    startResearch: (
        topic,
        focusAreas = '',
        workspaceId = 'default',
        maxQueries = 5,
        idempotencyKey
    ) => {
        if (
            typeof idempotencyKey !== 'string'
            || idempotencyKey.length < 8
            || idempotencyKey.length > 128
        ) {
            throw new TypeError('idempotencyKey must contain 8-128 characters');
        }
        return apiFetch('/research/autonomous', {
            method: 'POST',
            headers: { 'Idempotency-Key': idempotencyKey },
            body: JSON.stringify({
                topic,
                focus_areas: focusAreas,
                max_queries: maxQueries,
                workspace_id: workspaceId,
            }),
        });
    },

    startRecursiveResearch: (
        query,
        workspaceId = 'default',
        depth = 3,
        maxSourcesPerLevel = 5
    ) =>
        apiFetch('/research/recursive', {
            method: 'POST',
            body: JSON.stringify(buildRecursiveResearchRequest({
                query,
                workspaceId,
                depth,
                maxSourcesPerLevel,
            })),
        }),

    // --- Journal Search ---
    searchJournals: (query, maxPapers = 3) =>
        apiFetch('/research/journals', {
            method: 'POST',
            body: JSON.stringify({ query, max_papers: maxPapers }),
        }),

    // --- Documents ---
    ingestText: (
        text,
        metadata = {},
        workspaceId = 'default',
        licenseId = 'UNKNOWN'
    ) =>
        apiFetch('/ingest', {
            method: 'POST',
            body: JSON.stringify(buildIngestTextRequest({
                text,
                metadata,
                workspaceId,
                licenseId,
            })),
        }),

    ingestVideo: (url) =>
        apiFetch('/ingest/video', {
            method: 'POST',
            body: JSON.stringify({ url }),
        }),

    listDocuments: (workspaceId = 'default') =>
        apiFetch(`/documents?workspace_id=${workspaceId}`),

    readDocumentText: async (workspaceId, filename) => {
        const response = await apiFetchResource(
            `/documents/view/${encodeURIComponent(workspaceId)}/${encodeURIComponent(filename)}`
        );
        return response.text();
    },

    downloadDocument: (workspaceId, filename) => downloadResource(
        `/documents/view/${encodeURIComponent(workspaceId)}/${encodeURIComponent(filename)}`,
        filename
    ),

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
        return downloadResource(`/thesis/export/${encodeURIComponent(sessionId)}`, fileName);
    },

    // --- Dynamic Model Settings ---
    getModels: () => apiFetch('/config/models'),
    updateModel: (modelName) => apiFetch('/config/models', {
        method: 'POST',
        body: JSON.stringify({ model_name: modelName })
    }),
};

export default api;
