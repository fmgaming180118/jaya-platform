import { useApp } from '../context/AppContext';

/**
 * EnvironmentBadge — Tampilkan di sidebar footer
 * DEV  → badge oranye amber
 * PROD → badge hijau emerald
 */
export default function EnvironmentBadge() {
    const { mode, version } = useApp();
    const isDev = mode === 'development';

    return (
        <div className={`
            inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest
            ${isDev
                ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
            }
        `}>
            <span className={`
                w-1.5 h-1.5 rounded-full
                ${isDev ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'}
            `} />
            {isDev ? 'DEV' : 'PROD'} · v{version}
        </div>
    );
}
