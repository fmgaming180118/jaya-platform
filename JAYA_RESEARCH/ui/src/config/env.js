/**
 * JAYA Research - Environment Configuration
 * Dibaca dari Vite env variables (VITE_*)
 * DEV  → .env.development  (npm run dev)
 * PROD → .env.production   (npm run build)
 */

export const APP_MODE = import.meta.env.VITE_APP_MODE || 'production';
export const APP_NAME = import.meta.env.VITE_APP_NAME || 'JAYA Research';
export const APP_VERSION = import.meta.env.VITE_APP_VERSION || '2.1.0';
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

// Mode booleans — gunakan ini di seluruh komponen
export const IS_DEV = APP_MODE === 'development';
export const IS_PROD = APP_MODE === 'production';

// Dev Tool Flags
export const SHOW_DEV_BANNER    = import.meta.env.VITE_SHOW_DEV_BANNER === 'true';
export const SHOW_DEV_PANEL     = import.meta.env.VITE_SHOW_DEV_PANEL === 'true';
export const SHOW_API_LOGS      = import.meta.env.VITE_SHOW_API_LOGS === 'true';
export const SHOW_ENV_INSPECTOR = import.meta.env.VITE_SHOW_ENV_INSPECTOR === 'true';

// Feature Flags
export const FEATURES = {
    journalSearch:       import.meta.env.VITE_ENABLE_JOURNAL_SEARCH !== 'false',
    pdfUpload:           import.meta.env.VITE_ENABLE_PDF_UPLOAD !== 'false',
    recursiveResearch:   import.meta.env.VITE_ENABLE_RECURSIVE_RESEARCH !== 'false',
    knowledgeGraph:      import.meta.env.VITE_ENABLE_KNOWLEDGE_GRAPH !== 'false',
    digitalTwin:         import.meta.env.VITE_ENABLE_DIGITAL_TWIN !== 'false',
    thesisMode:          import.meta.env.VITE_ENABLE_THESIS_MODE !== 'false',
    settingsPage:        import.meta.env.VITE_ENABLE_SETTINGS_PAGE !== 'false',
};

// Semua env variables yang aman untuk ditampilkan di DevPanel
export const getPublicEnvVars = () => {
    return Object.entries(import.meta.env)
        .filter(([key]) => key.startsWith('VITE_'))
        .reduce((acc, [k, v]) => ({ ...acc, [k]: v }), {});
};
