# Desain Pipeline Penemuan Ilmiah dan Rekayasa Multimodal (Scientific & Engineering Discovery Pipeline)

**Status:** IDEA → PROTOTYPE  
**Berlaku mulai:** 2 Agustus 2026  
**ADR terkait:** ADR-011  

---

## 1. Visi dan Konsep Utama: Dual-Track JAYA Research

JAYA Research tidak hanya berfungsi sebagai "guru" bagi JAYA Core yang meneliti peningkatan kognitif internal. JAYA Research dirancang sebagai **Laboratorium Ilmiah dan Rekayasa Multimodal** berdaulat yang menggunakan kemampuan JAYA Core untuk menghasilkan, menguji, dan memvalidasi penemuan ilmiah di dunia nyata.

```text
JAYA Research (Dual-Track Architecture)
├── Track 1: Cognitive Evolution Research (Internal)
│   ├── Meneliti cara memperbaiki JAYA (reasoning, memory, model adapters, tools)
│   └── Output: Candidate Cognitive Artifact → Promotion Gate → JAYA Core
│
└── Track 2: Scientific and Engineering Discovery (External / Physical AI / 3D)
    ├── Meneliti fenomena fisika, energi, material, rekayasa, 3D CAD, dan digital twin
    └── Output: Discovery Candidate Artifact, Engineering Design, Digital Twin, REJECTED_HYPOTHESIS
```

---

## 2. Pipeline Penemuan 16-Langkah (16-Step Discovery Pipeline)

Untuk meneliti hal baru di dunia fisik (misalnya konsep energi portabel berdaya tinggi), JAYA Research menggunakan alur kerja 16 langkah yang terstruktur:

```text
 1. Fiction-to-Requirement Translation  ──► Mengubah gagasan fiksi/abstrak menjadi spesifikasi rekayasa terukur
 2. Known-Physics Constraint Analysis   ──► Menganalisis batas hukum fisika terverifikasi
 3. Evidence & Prior-Art Search        ──► Mencari literatur, paten, dan data eksperimen terdahulu
 4. Research Gap Map                    ──► Memetakan komponen yang belum memiliki solusi ilmiah
 5. Hypothesis Generation               ──► Membentuk keluarga hipotesis kerja
 6. Mathematical Modeling               ──► Menyusun persamaan fisika, asumsi, dan boundary condition
 7. System Architecture                 ──► Membagi sistem ke modul (sumber energi, containment, cooling, shielding)
 8. Parametric 3D Generation            ──► Membuat geometri kandidat (CAD / OpenUSD)
 9. Multiphysics Simulation             ──► Menjalankan solver domain (EM, thermal, CFD, structural, plasma)
10. Falsification                       ──► Menguji dan mengeliminasi hipotesis yang gagal (Falsification Gate)
11. Design Optimization                 ──► Melakukan iterasi dan pengkondisian parameter
12. Digital Twin Assembly               ──► Memvisualisasikan bentuk dan data solver di Omniverse / OpenUSD
13. Uncertainty Analysis                ──► Mengukur sensitivitas, batas toleransi, dan margin error
14. Prototype Plan                      ──► Menyusun rencana eksperimen fisik yang aman dan terukur
15. Empirical Feedback Integration       ──► Memasukkan hasil uji laboratorium ke model kognitif
16. Discovery Artifact Export           ──► Mempublikasikan Discovery Candidate / REJECTED_HYPOTHESIS
```

---

## 3. Integrasi Solver Adapters dan Omniverse

### 3.1 Peran Omniverse dan OpenUSD

NVIDIA Omniverse dan OpenUSD berperan sebagai **ruang visualisasi terpadu dan digital twin**, bukan mesin penemu otomatis atau universal solver fisika. 

- **OpenUSD**: Format standar untuk menyatukan geometri 3D, material, animasi, dan data simulasi.
- **Omniverse Kit-CAE**: Membawa data solver fisika, sensor, dan AI surrogate ke tampilan visual digital twin.
- **PhysX**: Menyediakan simulasi dinamika rigid-body, collision, joint, dan vehicle.

### 3.2 Stack Solver berdasarkan Domain Fisika

| Domain Fisika | Solver / Engine | Peran dalam JAYA Research |
|---|---|---|
| Dinamika & Collision | PhysX | Rigid body, joint, artikulasi mekanik |
| Struktural & Tegangan | FEA Solver (OpenFOAM/Code_Aster/Elmer) | Analisis beban, deformasi, tegangan material |
| Fluida & Pendinginan | CFD Solver (OpenFOAM/SU2) | Aliran udara, konveksi panas, aerodinamika |
| Elektromagnetik | EM Solver (MEEP/Elmer) | Medan magnet, induksi, confinement plasma |
| Termal | Thermal Solver | Perpindahan panas mikrokanal, konduksi |
| Plasma / Fusion | Plasma / MHD Solver | Confinement plasma, temperatur, stabilitas |
| AI Physics Surrogate | NVIDIA Modulus / PhysicsNeMo | Accelerating physics prediction dengan Neural Operator |
| Visualisasi & Digital Twin | NVIDIA Omniverse / OpenUSD | Agregasi visual 3D, sensor overlay, perbandingan iterasi |

Seluruh solver adapter bersifat **opsional / remote capability providers**. Tidak ada dependency GPU/CUDA/Omniverse yang diwajibkan dalam base installation JAYA Core.

---

## 4. Contoh Kasus: Analisis Rekayasa "Arc Reactor"

### 4.1 Formulasi Masalah dan Penerjemahan Syarat Rekayasa

Gagasan fiksi "Arc Reactor" diterjemahkan oleh `FictionToRequirementTranslator` menjadi spesifikasi rekayasa terukur:

```json
{
  "fictional_concept": "Arc Reactor (Tony Stark)",
  "translated_goal": "Sumber energi portabel dengan kepadatan daya sangat tinggi (GW/m³)",
  "engineering_requirements": {
    "max_diameter_cm": 12.0,
    "max_depth_cm": 15.0,
    "max_mass_kg": 3.0,
    "continuous_power_mw": 10.0,
    "peak_power_mw": 100.0,
    "max_surface_temp_c": 45.0,
    "radiation_shielding": "zero_leakage_external"
  },
  "current_physics_feasibility": "UNFEASIBLE_WITH_KNOWN_TECHNOLOGY",
  "primary_blockers": [
    "Magnetic confinement scaling laws (plasma requires ~840m³ volume in ITER)",
    "Microchannel heat rejection limits at 100MW scale",
    "Neutron damage to compact superconducting magnets",
    "Direct energy conversion efficiency limits"
  ],
  "researchable_subproblems": [
    "High-field compact HTS (High-Temperature Superconductor) magnet geometry",
    "Neutron-resistant ceramic matrix composite materials",
    "Micro-gap magnetohydrodynamic (MHD) direct energy harvesting",
    "Surrogate plasma stability modeling using PINNs"
  ]
}
```

### 4.2 Eliminasi dan Uji Falsifikasi (Falsification Engine)

Hipotesis reaktor portabel diuji terhadap hukum fisika yang diketahui:

1. **Hipotesis Tokamak Mini (D-T Fusion)**: Ditolak karena hukum scaling confinement magnetik membutuhkan volume plasma minimal beberapa meter kubik untuk mempertahankan ignition net-gain.
2. **Hasil Uji**: Menghasilkan **`REJECTED_HYPOTHESIS`** beserta bukti penurunan numerik.
3. **Sub-Problem Terisolasi**: JAYA Research mengalihkan fokus ke riset material dan geometri magnet HTS kompak sebagai candidate discovery terpisah.

---

## 5. Jenis Artefak Baru

Di luar artefak evolusi kognitif internal Core, JAYA Research menerbitkan kategori **Discovery Artifacts**:

| Jenis Artefak | Deskripsi |
|---|---|
| `SCIENTIFIC_HYPOTHESIS` | Formulasi hipotesis ilmiah dengan asumsi dan rumusan matematika |
| `ENGINEERING_REQUIREMENTS` | Hasil penerjemahan ide fiksi/abstrak menjadi spesifikasi rekayasa terukur |
| `PARAMETRIC_GEOMETRY` | Definisi geometri 3D dalam CAD/OpenUSD script |
| `SIMULATION_RESULT` | Output terverifikasi dari solver fisika (FEA, CFD, EM, Thermal) |
| `DIGITAL_TWIN` | Bundle OpenUSD berisi bentuk 3D, material, dan data overlay simulasi |
| `REJECTED_HYPOTHESIS` | Laporan falsifikasi ilmiah yang menguraikan alasan desain/teori gagal |
| `DISCOVERY_CANDIDATE` | Kandidat penemuan ilmiah/rekayasa baru yang siap dievaluasi manusia |

Semua artefak berstatus awal `CANDIDATE` dan tidak pernah secara otomatis mengklaim keberhasilan eksperimen fisik tanpa bukti empiris laboratorium nyata.
