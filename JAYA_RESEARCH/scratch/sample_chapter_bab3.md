# Bab III: Analisis dan Perancangan Sistem

## 3.1 Deskripsi Umum Sistem
Topik Penelitian: Sistem Monitoring Scrap Product PT SKF Indonesia

Spesifikasi Kebutuhan Sistem:

Sistem monitoring scrap product memiliki aktor:
1. Mahasiswa (sebagai analis) yang dapat login, melihat grafik scrap product, dan mencetak laporan scrap.
2. Dosen Pembimbing yang dapat login, memantau kemajuan bimbingan, dan memberikan persetujuan.
Sistem ini didefinisikan sebagai SistemAkademik.


## 3.2 Use Case Diagram
Berikut adalah diagram Use Case Diagram untuk rancangan sistem:

![Use Case Diagram](http://www.plantuml.com/plantuml/svg/~1JP4zRiCm38LtdO9ZE-G2dfAcG8V6G80WtHcRjLLRFw2ePWXozygMvLhG83r-3tgaza6G9PfHLJNs67IuOmKOeEw3gjvT80jdCZUTjktcoYmgnTG8scuakEWWP0u3jcJq00y5QRsSNAVjwsIu7kTpbciQTOy27upV2RuqZ1xExDhOo49_QRgdik-BmpOaEC09lMEqsREmnwbIE8DMCC9dElp41Bxbr5XYrCvgSRpYDs8zuDGW1v8uUHRou3sxNr9FfT8WOBTRcrYl_obNAOV9GzjODa99i97AKtkoRVg7Fm)

### 3.2.1 Penjelasan Use Case Diagram
Diagram Use Case yang ditunjukkan menggambarkan interaksi antara dua aktor utama, yaitu **Mahasiswa** (berperan sebagai analis) dan **Dosen Pembimbing**, dengan sistem yang didefinisikan sebagai **SistemAkademik**. Dalam diagram ini, sistem dibatasi oleh persegi panjang yang mencakup lima use case inti: (Login), (Melihat Grafik Scrap Product), (Mencetak Laporan Scrap), (Memantau Kemajuan Bimbingan), dan (Memberikan Persetujuan). Setiap aktor terhubung langsung ke use case yang relevan melalui asosiasi garis lurus, yang menunjukkan bahwa aktor tersebut berhak memulai atau melaksanakan use case tersebut tanpa adanya mediator lain. Mahasiswa memiliki akses ke use case login untuk masuk ke sistem, kemudian dapat melanjutkan ke use case melihat grafik scrap product dan mencetak laporan scrap, yang secara bersama-sama mendukung aktivitas analisis data scrap product. Sebaliknya, Dosen Pembimbing juga melakukan use case login sebagai titik masuk sistem, lalu beralih ke use case memantau kemajuan bimbingan dan memberikan persetujuan, yang merupakan tanggung jawabnya dalam proses bimbingan akademik dan penelitian. 

Secara struktural, diagram ini memenuhi prinsip dasar penulisan use case diagram sesuai standar Tugas Akhir: (1) aktor ditunjukkan sebagai stick figure dengan label jelas, (2) use case direpresentasikan oleh elips dengan nama yang menjelaskan fungsi sistem dari perspektif pengguna, (3) batas sistem (SistemAkademik) ditandai dengan persegi panjang yang memisahkan aktor dari fungsionalitas internal, dan (4) hubungan asosiasi antara aktor dan use case menggambarkan hak akses tanpa adanya hubungan inklusi, ekstensisi, atau generalisasi yang lebih kompleks karena setiap use case bersifat independen dan langsung terkait dengan tanggung jawab masing‑masing aktor. Dengan demikian, diagram ini secara jelas menggambarkan alur kerja sistem: setelah proses login yang bersama-sama, masing‑masing aktor menjalankan use case yang sesuai dengan perannya dalam monitoring dan evaluasi scrap product, sehingga mendukung kebutuhan informasiMahasiswa sebagai analis dan ruolo supervisif Dosen Pembimbing dalam proses bimbingan akademis.

<!-- Raw PlantUML Source:
@startuml
:Mahasiswa: as Mhs
:Dosen Pembimbing: as Dosen

rectangle SistemAkademik {
    (Login) as UCLogin
    (Melihat Grafik Scrap Product) as UCViewGraph
    (Mencetak Laporan Scrap) as UCCetak
    (Memantau Kemajuan Bimbingan) as UCMonitor
    (Memberikan Persetujuan) as UCApprove
}

Mhs -- UCLogin
Mhs -- UCViewGraph
Mhs -- UCCetak
Dosen -- UCLogin
Dosen -- UCMonitor
Dosen -- UCApprove
@enduml
-->

