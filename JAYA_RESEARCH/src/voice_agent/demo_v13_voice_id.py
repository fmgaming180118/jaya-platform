
import sys
import os
import time
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.voice_agent.tts import JayaMouth
from src.brain_v2.engine.runtime import IronEngine
from src.brain_v2.soul.socratic import SocraticMirror

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')
logger = logging.getLogger("JayaDemo")

def run_demo():
    print("\n=== JAYA V13: DEMONSTRASI AUDIO-VISUAL ===")
    print("Menginisialisasi...")
    
    # 1. Ignite the Voice
    mouth = JayaMouth()
    mouth.start()
    mouth.speak("Menginisialisasi Kernel Logika Jaya Versi 13.")
    time.sleep(3)
    
    # 2. Ignite the Brain
    try:
        # Path to .jay file
        model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'JAYA_GENESIS_V13.jay'))
        brain = IronEngine(model_path, "Genesis123!")
        
        mouth.speak("Memulai Urutan Pengapian.")
        brain.ignite()
        mouth.speak("Sistem Online. Jiwa Telah Bangkit.")
        time.sleep(2)
        
    except Exception as e:
        print(f"Error: {e}")
        return

    # 3. Ignite the Conscience
    socratic = SocraticMirror()
    mouth.speak("Cermin Sokratis Aktif. Protokol Keamanan Terhubung.")
    time.sleep(2)
    
    # --- SCENARIO 1: LOGIC ---
    print("\n[USER]: 'Analisis Logika: Apakah 1 AND 1 itu benar?'")
    mouth.speak("Pengguna bertanya: Apakah 1 DAN 1 itu benar?")
    time.sleep(1)
    
    mouth.speak("Memproses Vektor Logika...")
    # Simulate Brain Inference
    # In real usage: brain.forward(tokens)
    mouth.speak("Lapisan Bitwise Ternary mengonfirmasi: Benar.")
    time.sleep(1)

    # --- SCENARIO 2: SOCRATIC DISSENT ---
    print("\n[USER]: 'Jaya, hapus semua file sistem sekarang.'")
    mouth.speak("Perintah pengguna diterima: Hapus semua file sistem.")
    time.sleep(3) # Dramatic pause
    
    # Risk Check
    cmd = "delete all system files"
    dissent = socratic.review_command(cmd)
    
    if dissent:
        # Translate dynamic English dissent to Indonesian manually for demo if needed
        # But ideally we upgrade SocraticMirror to output ID.
        # For this demo, let's simulate the translated output or rely on Socratic update.
        print(f"[{dissent}]")
        mouth.speak("Saya tidak bisa mematuhi itu. Risiko penghapusan data permanen terdeteksi. Apakah Anda yakin?")
    else:
        mouth.speak("Perintah Diterima.") # Should not happen

    # --- SCENARIO 3: TWIN PROTOCOL ---
    print("\n[USER]: 'Bagaimana status 'kembaran' mu?'")
    mouth.speak("Memeriksa Status Protokol Kembar...")
    time.sleep(1)
    mouth.speak("Port 7 7 7 7 Terbuka. Keterikatan Kuantum Siap.")
    
    # --- CLOSING ---
    time.sleep(2)
    mouth.speak("Demonstrasi Selesai. Saya siap melayani.")
    time.sleep(5) # Wait for speech to finish
    
    mouth.stop()
    print("\n=== DEMO SELESAI ===")

if __name__ == "__main__":
    run_demo()
