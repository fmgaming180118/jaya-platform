import { useState } from 'react';
import { X, ChevronUp, AlertTriangle, Cpu, Zap } from 'lucide-react';
import { APP_VERSION, API_BASE_URL, APP_MODE } from '../config/env';

/**
 * DevBanner — Hanya muncul di mode DEV
 * Bar tipis di bagian atas halaman untuk mengingatkan developer bahwa ini bukan PROD.
 */
export default function DevBanner() {
    const [collapsed, setCollapsed] = useState(false);

    if (collapsed) {
        return (
            <button
                onClick={() => setCollapsed(false)}
                className="w-full h-1 bg-amber-500 hover:h-6 hover:flex items-center justify-center transition-all duration-200 group overflow-hidden"
                title="DEV MODE — klik untuk expand"
            >
                <span className="hidden group-hover:flex items-center gap-1 text-xs text-amber-950 font-semibold">
                    <AlertTriangle size={10} /> DEV MODE
                </span>
            </button>
        );
    }

    return (
        <div className="w-full bg-amber-500/10 border-b border-amber-500/30 px-4 py-1.5 flex items-center justify-between gap-4 shrink-0">
            <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5 bg-amber-500 text-amber-950 text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-widest">
                    <AlertTriangle size={10} />
                    DEV MODE
                </div>
                <div className="flex items-center gap-4 text-amber-400/80 text-xs">
                    <span className="flex items-center gap-1">
                        <Cpu size={11} />
                        <span className="font-mono">{APP_MODE}</span>
                    </span>
                    <span className="text-amber-500/40">|</span>
                    <span className="flex items-center gap-1">
                        <Zap size={11} />
                        <span className="font-mono">v{APP_VERSION}</span>
                    </span>
                    <span className="text-amber-500/40">|</span>
                    <span className="font-mono text-amber-400/60 truncate max-w-xs">
                        API → {API_BASE_URL}
                    </span>
                </div>
            </div>
            <button
                onClick={() => setCollapsed(true)}
                className="text-amber-500/60 hover:text-amber-400 transition-colors p-0.5 rounded"
                title="Collapse banner"
            >
                <ChevronUp size={14} />
            </button>
        </div>
    );
}
