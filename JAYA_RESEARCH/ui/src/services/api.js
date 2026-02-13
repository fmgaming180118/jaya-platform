const API_BASE = 'http://localhost:8000';

export const api = {
    // --- Workspace Management ---
    listWorkspaces: async () => {
        const res = await fetch(`${API_BASE}/workspaces`);
        return res.json();
    },

    createWorkspace: async (name) => {
        const res = await fetch(`${API_BASE}/workspaces/create?name=${encodeURIComponent(name)}`, {
            method: 'POST'
        });
        return res.json();
    },

    // --- Core Features ---

    // Health Check
    getHealth: async () => {
        try {
            const res = await fetch(`${API_BASE}/`);
            return res.json();
        } catch (e) {
            return { status: "offline" };
        }
    },

    // Chat request
    chat: async (message, contextFiles = [], workspaceId = "default") => {
        const res = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                context_files: contextFiles,
                workspace_id: workspaceId
            }),
        });
        return res.json();
    },

    // Start autonomous research
    startResearch: async (topic, focusAreas = "", workspaceId = "default") => {
        const res = await fetch(`${API_BASE}/research/autonomous`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                topic,
                focus_areas: focusAreas,
                workspace_id: workspaceId
            })
        });
        return res.json();
    },

    // Get research history (Mock)
    getHistory: async () => {
        // const res = await fetch(`${API_BASE}/history`);
        return [];
    },

    // Get Knowledge Graph
    getGraph: async (workspaceId = "default") => {
        const res = await fetch(`${API_BASE}/graph?workspace_id=${workspaceId}`);
        return res.json();
    },

    // Ingest Video
    ingestVideo: async (url) => {
        const res = await fetch(`${API_BASE}/ingest/video`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        return res.json();
    }
};

export default api;
