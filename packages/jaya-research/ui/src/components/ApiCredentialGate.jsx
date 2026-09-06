import { useState } from 'react';
import { AlertCircle, KeyRound, LoaderCircle, ShieldCheck } from 'lucide-react';

import { API_AUTH_MODE, APP_NAME } from '../config/env';
import api, {
    clearApiAccessToken,
    setApiAccessToken,
} from '../services/api';

export default function ApiCredentialGate({ children }) {
    const [token, setToken] = useState('');
    const [isReady, setIsReady] = useState(API_AUTH_MODE === 'test');
    const [isVerifying, setIsVerifying] = useState(false);
    const [error, setError] = useState('');

    if (isReady) return children;

    const verifyCredential = async (event) => {
        event.preventDefault();
        if (token.length < 32 || token.length > 4_096 || /\s/u.test(token)) {
            setError('API key harus berisi 32â€“4096 karakter tanpa spasi.');
            return;
        }

        setIsVerifying(true);
        setError('');
        try {
            setApiAccessToken(token);
            await api.listWorkspaces();
            setToken('');
            setIsReady(true);
        } catch (credentialError) {
            clearApiAccessToken();
            const code = credentialError?.code ? `[${credentialError.code}] ` : '';
            setError(`${code}${credentialError?.message || 'Kredensial tidak dapat diverifikasi.'}`);
        } finally {
            setIsVerifying(false);
        }
    };

    return (
        <main className="min-h-screen bg-[#080a0f] text-slate-100 flex items-center justify-center p-5">
            <section className="w-full max-w-md rounded-3xl border border-white/10 bg-[#111520] shadow-2xl overflow-hidden">
                <div className="p-6 border-b border-white/[0.07] bg-white/[0.02]">
                    <div className="w-11 h-11 rounded-2xl bg-sky-500/10 border border-sky-500/25 text-sky-300 flex items-center justify-center mb-4">
                        <ShieldCheck size={22} />
                    </div>
                    <p className="text-[10px] uppercase tracking-[0.22em] text-sky-400 font-bold">Fail-closed access</p>
                    <h1 className="text-xl font-bold mt-1">Hubungkan ke {APP_NAME}</h1>
                    <p className="text-xs text-slate-400 leading-relaxed mt-3">
                        Masukkan API key Research yang dikonfigurasi pada backend. Key hanya disimpan di memori tab ini dan hilang saat halaman dimuat ulang.
                    </p>
                </div>

                <form onSubmit={verifyCredential} className="p-6 space-y-4">
                    <label htmlFor="research-api-key" className="block">
                        <span className="text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1.5 mb-2">
                            <KeyRound size={11} /> Research API key
                        </span>
                        <input
                            id="research-api-key"
                            type="password"
                            value={token}
                            onChange={(event) => setToken(event.target.value)}
                            minLength={32}
                            maxLength={4_096}
                            autoComplete="off"
                            autoFocus
                            disabled={isVerifying}
                            className="w-full rounded-xl border border-white/10 bg-black/20 px-4 py-3 font-mono text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/30 disabled:opacity-60"
                        />
                    </label>

                    {error && (
                        <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-red-200 flex items-start gap-2">
                            <AlertCircle size={15} className="mt-0.5 shrink-0" />
                            <p className="text-[11px] leading-relaxed break-words">{error}</p>
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={isVerifying || token.length < 32}
                        className="w-full rounded-xl border border-sky-500/35 bg-sky-500/15 px-4 py-3 text-sm font-bold text-sky-200 hover:bg-sky-500/25 transition-colors disabled:opacity-45 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                        {isVerifying ? (
                            <><LoaderCircle size={15} className="animate-spin" /> Memverifikasi...</>
                        ) : (
                            <><ShieldCheck size={15} /> Verifikasi dan lanjutkan</>
                        )}
                    </button>

                    <p className="text-[10px] text-slate-600 leading-relaxed">
                        Verifikasi memakai operasi baca workspace. Key memerlukan scope <code>research:admin</code>; nilai secret tidak ditulis ke storage maupun log UI.
                    </p>
                </form>
            </section>
        </main>
    );
}
