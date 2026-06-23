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
                url: fullUrl,
                method,
                status: res.status,
                ok: res.ok,
                duration,
                timestamp: Date.now(),
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

    // --- Knowledge Graph ---
    getGraph: (workspaceId = 'default') =>
        apiFetch(`/graph?workspace_id=${workspaceId}`),

    // --- History ---
    getHistory: async () => [],
};

export default api;
