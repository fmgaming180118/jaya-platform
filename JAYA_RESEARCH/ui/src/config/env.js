/**
 * JAYA Research - Environment Configuration
 * Dibaca dari Vite env variables (VITE_*)
 * DEV  → .env.development  (npm run dev)
 * PROD → .env.production   (npm run build)
 */

const ENV = import.meta.env || {};

export const APP_MODE = ENV.VITE_APP_MODE || 'production';
export const APP_NAME = ENV.VITE_APP_NAME || 'JAYA Research';
export const APP_VERSION = ENV.VITE_APP_VERSION || '2.1.0';
export const API_BASE_URL = ENV.VITE_API_BASE_URL || '/api';
export const API_AUTH_MODE = ENV.VITE_API_AUTH_MODE === 'test' ? 'test' : 'required';

// Mode booleans — gunakan ini di seluruh komponen
export const IS_DEV = APP_MODE === 'development';
export const IS_PROD = APP_MODE === 'production';

// Dev Tool Flags
export const SHOW_DEV_BANNER    = ENV.VITE_SHOW_DEV_BANNER === 'true';
export const SHOW_DEV_PANEL     = ENV.VITE_SHOW_DEV_PANEL === 'true';
export const SHOW_API_LOGS      = ENV.VITE_SHOW_API_LOGS === 'true';
export const SHOW_ENV_INSPECTOR = ENV.VITE_SHOW_ENV_INSPECTOR === 'true';

// Feature Flags
export const FEATURES = {
    journalSearch:       ENV.VITE_ENABLE_JOURNAL_SEARCH !== 'false',
    pdfUpload:           ENV.VITE_ENABLE_PDF_UPLOAD !== 'false',
    recursiveResearch:   ENV.VITE_ENABLE_RECURSIVE_RESEARCH !== 'false',
    knowledgeGraph:      ENV.VITE_ENABLE_KNOWLEDGE_GRAPH !== 'false',
    digitalTwin:         ENV.VITE_ENABLE_DIGITAL_TWIN !== 'false',
    thesisMode:          ENV.VITE_ENABLE_THESIS_MODE !== 'false',
    settingsPage:        ENV.VITE_ENABLE_SETTINGS_PAGE !== 'false',
};

// Semua env variables yang aman untuk ditampilkan di DevPanel
export const getPublicEnvVars = () => {
    return Object.entries(ENV)
        .filter(([key]) => key.startsWith('VITE_'))
        .reduce((acc, [k, v]) => ({ ...acc, [k]: v }), {});
};
