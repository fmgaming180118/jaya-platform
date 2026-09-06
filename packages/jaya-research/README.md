# JAYA Research

JAYA Research adalah lapisan riset dan pengetahuan ekosistem JAYA. Modul ini
mengelola ingestion, RAG bercitation, analisis tesis, pencarian literatur,
knowledge graph, dan pipeline discovery.

**Kematangan:** prototipe terintegrasi. Beberapa jalur utama sudah implemented,
tetapi persistence job, QA RAG, discovery empiris, dan promosi aman belum
memenuhi gate produksi.

Dokumentasi kanonis:

- [Pusat dokumentasi](../../docs/README.md)
- [Alur Research](../../docs/WORKFLOWS.md)
- [Status aktual](../../docs/STATUS.md)
- [Roadmap](../../docs/ROADMAP.md)
- [Panduan pengembangan](../../docs/DEVELOPMENT.md)

## Mulai cepat

Dari root repository:

```powershell
python -m pip install -r packages\jaya-research\requirements.txt
Copy-Item packages\jaya-research\.env.example .env
$env:PYTHONPATH='packages/jaya-research/src'
python -m jaya_research.network.research_api
```

UI:

```powershell
Set-Location packages\jaya-research\ui
npm install
npm run dev
```

Kontribusi mengikuti [panduan root](../../CONTRIBUTING.md). Jangan menambahkan
folder dokumentasi baru di modul ini.
