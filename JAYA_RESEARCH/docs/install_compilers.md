
# Panduan Instalasi Compiler C/C++ (Windows)

Untuk menjalankan Micro-AGI (Sandbox), kita membutuhkan compiler yang bisa mengubah kode C/LLVM IR menjadi program yang bisa dijalankan.
Kita akan menginstall **LLVM (Clang)** dan **GCC**.

### Metode 1: Menggunakan Winget (Paling Mudah)
Buka **PowerShell** atau **Command Prompt** sebagai Administrator, lalu jalankan perintah berikut satu per satu:

1.  **Install LLVM (Clang):**
    ```powershell
    winget install -e --id LLVM.LLVM
    ```
    *Selama instalasi, pastikan mencentang opsi **"Add LLVM to the system PATH for all users"** agar perintah `clang` bisa dikenali.*

2.  **Install MinGW (GCC):**
    ```powershell
    winget install -e --id OH-My-Posh.Mingw-w64
    ```
    *(Atau gunakan installer lain seperti MSYS2 jika gagal)*

### Metode 2: Download Manual

1.  **LLVM (Clang):**
    -   Download installer dari: [LLVM Releases (GitHub)](https://github.com/llvm/llvm-project/releases)
    -   Pilih file `LLVM-xx.x.x-win64.exe`.
    -   **PENTING:** Saat instalasi, pilih **"Add LLVM to the system PATH for all users"**.

2.  **MinGW-w64 (GCC):**
    -   Download dari: [WinLibs](https://winlibs.com/)
    -   Download versi "UCRT runtime".
    -   Ekstrak file `.7z` atau `.zip` ke `C:\mingw64`.
    -   Tambahkan `C:\mingw64\bin` ke **Environment Variables (Path)** Windows Anda.

### Verifikasi Instalasi
Setelah instalasi selesai, **tutup terminal lama dan buka terminal baru**, lalu ketik:

```powershell
clang --version

```

Jika muncul versi (misal `clang version 18.x.x`), maka Anda siap lanjut!
