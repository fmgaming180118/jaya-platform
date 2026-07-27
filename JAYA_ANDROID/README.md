# JAYA Android

JAYA Android adalah klien mobile untuk berinteraksi dengan JAYA, menyimpan cache
lokal yang aman, dan menyinkronkan pekerjaan melalui kontrak API yang stabil.

**Kematangan:** prototipe. Keberadaan proyek Gradle belum membuktikan runtime
model/JNI dan sinkronisasi end-to-end pada perangkat nyata.

Dokumentasi kanonis:

- [Arsitektur ekosistem](../docs/ARCHITECTURE.md)
- [Status aktual](../docs/STATUS.md)
- [Roadmap perangkat](../docs/ROADMAP.md)
- [Panduan pengembangan](../docs/DEVELOPMENT.md)

## Build terarah

Dari root repository:

```powershell
Set-Location JAYA_ANDROID
.\gradlew.bat test
.\gradlew.bat assembleDebug
```

Jangan membuat dokumentasi aktif di dalam modul ini.
