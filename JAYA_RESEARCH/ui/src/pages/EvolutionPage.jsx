import {
    AlertTriangle,
    CheckCircle2,
    FlaskConical,
    LockKeyhole,
    Shield,
} from 'lucide-react';

const LOCAL_BOUNDARIES = [
    'Research hanya menghasilkan candidate/evidence artifact.',
    'Tidak ada source JAYA_CORE yang dimutasi dari UI Research.',
    'Simulasi, output provider, dan draft tidak dianggap approval.',
];

const OPEN_GATES = [
    'Artifact contract Research â†’ Core yang versioned dan signed.',
    'Human approval, compatibility check, canary, audit, dan rollback.',
    'Deployment drill pada environment target dengan receipt yang dapat diverifikasi.',
];

function GateList({ icon: Icon, items, tone, title }) {
    return (
        <section className={`rounded-2xl border p-5 ${tone}`}>
            <h2 className="text-sm font-bold flex items-center gap-2">
                <Icon size={16} /> {title}
            </h2>
            <ul className="mt-4 space-y-3">
                {items.map((item) => (
                    <li key={item} className="flex items-start gap-2 text-xs leading-relaxed">
                        <span className="mt-1 w-1.5 h-1.5 rounded-full bg-current shrink-0" />
                        {item}
                    </li>
                ))}
            </ul>
        </section>
    );
}

export default function EvolutionPage() {
    return (
        <main className="min-h-full overflow-y-auto bg-[#0b0c10] text-slate-100 p-6 lg:p-8">
            <div className="max-w-4xl mx-auto space-y-6">
                <header className="rounded-3xl border border-amber-500/25 bg-amber-500/[0.06] p-6">
                    <div className="flex items-start gap-4">
                        <span className="p-3 rounded-2xl bg-amber-500/10 border border-amber-500/25 text-amber-300">
                            <LockKeyhole size={22} />
                        </span>
                        <div>
                            <p className="text-[10px] uppercase tracking-[0.22em] text-amber-400 font-bold">Promotion boundary</p>
                            <h1 className="text-xl font-bold mt-1">Autonomous evolution belum diaktifkan</h1>
                            <p className="text-xs text-slate-400 leading-relaxed mt-3">
                                Phase A membuktikan pembuatan candidate secara lokal, bukan pemasangan otomatis ke Core.
                                Tombol mutasi dan loop legacy sengaja tidak tersedia sampai seluruh gate Phase E lulus.
                            </p>
                        </div>
                    </div>
                </header>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <GateList
                        icon={CheckCircle2}
                        title="Boundary lokal yang aktif"
                        items={LOCAL_BOUNDARIES}
                        tone="border-emerald-500/20 bg-emerald-500/[0.04] text-emerald-200"
                    />
                    <GateList
                        icon={AlertTriangle}
                        title="Gate yang masih terbuka"
                        items={OPEN_GATES}
                        tone="border-amber-500/20 bg-amber-500/[0.04] text-amber-200"
                    />
                </div>

                <section className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-5 flex items-start gap-3">
                    <Shield size={17} className="text-sky-300 mt-0.5 shrink-0" />
                    <div>
                        <h2 className="text-sm font-bold">Status: BLOCKED</h2>
                        <p className="text-xs text-slate-400 leading-relaxed mt-2">
                            Gunakan halaman Deep Research untuk menghasilkan artefak evidence-bound. Promosi ke JAYA_CORE
                            tetap merupakan workflow terpisah dengan persetujuan manusia dan receipt yang tervalidasi.
                        </p>
                        <p className="text-[10px] text-slate-600 mt-3 flex items-center gap-1.5">
                            <FlaskConical size={11} /> Tidak ada request evolusi yang dikirim dari halaman ini.
                        </p>
                    </div>
                </section>
            </div>
        </main>
    );
}
