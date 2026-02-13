
import sys
import os
import time
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.voice_agent.tts import JayaMouth
from src.brain_v2.engine.agentic_search import AgenticSearchEngine

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(message)s')
logger = logging.getLogger("JayaRagDemo")

def run_demo():
    print("\n=== JAYA V13: DEMONSTRASI AGENTIC RAG ===")
    print("Menginisialisasi...")
    
    # 1. Ignite Mouth
    mouth = JayaMouth()
    mouth.start()
    
    # 2. Ignite Agentic Brain
    try:
        engine = AgenticSearchEngine()
        mouth.speak("Mesin Pencari Agentic Siap.")
        time.sleep(2)
    except Exception as e:
        print(f"Error: {e}")
        return

    # --- SCENARIO: GENERAL KNOWLEDGE ---
    question = "Siapa presiden Indonesia saat ini?"
    print(f"\n[USER]: '{question}'")
    mouth.speak(f"Pertanyaan: {question}")
    time.sleep(1)
    
    mouth.speak("Saya sedang mencari informasi di internet...")
    
    # Execute Think Loop
    response = engine.think_and_answer(question)
    
    print(f"\n[JAYA]: {response}")
    mouth.speak(response)
    
    # --- CLOSING ---
    time.sleep(5) 
    mouth.stop()
    print("\n=== DEMO SELESAI ===")

if __name__ == "__main__":
    run_demo()
