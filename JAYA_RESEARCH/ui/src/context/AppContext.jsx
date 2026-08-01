import { createContext, useCallback, useContext, useState } from 'react';
import { APP_MODE, APP_NAME, APP_VERSION, IS_DEV, IS_PROD, FEATURES, SHOW_DEV_PANEL } from '../config/env';

const AppContext = createContext(null);

/**
 * AppProvider — Sediakan context global untuk seluruh JAYA Research UI
 * Wrap di App.jsx agar semua komponen bisa akses mode, fitur, dan API logs.
 */
export function AppProvider({ children }) {
    const [isDevPanelOpen, setIsDevPanelOpen] = useState(false);
    const [apiLogs, setApiLogs] = useState([]);

    // Tambahkan log API call (dipakai oleh api.js)
    const addApiLog = useCallback((entry) => {
        if (!IS_DEV) return;
        setApiLogs(prev => [entry, ...prev].slice(0, 50)); // simpan max 50 log
    }, []);

    const clearApiLogs = useCallback(() => setApiLogs([]), []);

    const toggleDevPanel = useCallback(() => {
        setIsDevPanelOpen(prev => !prev);
    }, []);

    const value = {
        // App Info
        mode: APP_MODE,
        appName: APP_NAME,
        version: APP_VERSION,
        // Mode Flags
        isDevMode: IS_DEV,
        isProdMode: IS_PROD,
        // Feature Flags
        features: FEATURES,
        // Dev Panel
        isDevPanelOpen,
        toggleDevPanel,
        canShowDevPanel: IS_DEV && SHOW_DEV_PANEL,
        // API Logs
        apiLogs,
        addApiLog,
        clearApiLogs,
    };

    return (
        <AppContext.Provider value={value}>
            {children}
        </AppContext.Provider>
    );
}

/** Hook — gunakan di mana saja: const { isDevMode, features } = useApp(); */
export function useApp() {
    const ctx = useContext(AppContext);
    if (!ctx) throw new Error('useApp must be used inside <AppProvider>');
    return ctx;
}

export default AppContext;
