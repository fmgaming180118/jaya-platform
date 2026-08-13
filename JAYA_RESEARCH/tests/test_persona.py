
import sys
import os
import time
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.voice_agent.tts import JayaMouth

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')
logger = logging.getLogger("JayaPersonaTest")

def run_demo():
    print("\n=== JAYA V13: TES PERSONA (LAKI-LAKI & SANTAI) ===")
    
    # 1. Ignite Mouth
    mouth = JayaMouth()
    mouth.start()
    
    # Intro
    text = "Halo Bos. Kenalin, saya Jaya versi baru. Suara saya udah laki belum? Dan bahasanya udah santai kan?"
    print(f"[JAYA]: {text}")
    mouth.speak(text)
    time.sleep(8)
    
    # Logic
    text = "Analisis beres. Logika saya sih aman, Bos."
    print(f"[JAYA]: {text}")
    mouth.speak(text)
    time.sleep(5)

    # Risk
    text = "Waduh Bos, bahaya tuh. Yakin mau hapus semua data?"
    print(f"[JAYA]: {text}")
    mouth.speak(text)
    time.sleep(5)
    
    mouth.stop()
    print("\n=== TES SELESAI ===")

if __name__ == "__main__":
    run_demo()
