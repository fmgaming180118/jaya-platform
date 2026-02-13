
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
    print("\n=== JAYA V13: AUDIO-VISUAL DEMONSTRATION ===")
    print("Initializing...")
    
    # 1. Ignite the Voice
    mouth = JayaMouth()
    mouth.start()
    mouth.speak("Initializing Jaya Logic Kernel Version 13.")
    time.sleep(3)
    
    # 2. Ignite the Brain
    try:
        # Path to .jay file
        model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'JAYA_GENESIS_V13.jay'))
        brain = IronEngine(model_path, "Genesis123!")
        
        mouth.speak("Ignition Sequence Start.")
        brain.ignite()
        mouth.speak("Systems Online. The Soul is Awake.")
        time.sleep(2)
        
    except Exception as e:
        print(f"Error: {e}")
        return

    # 3. Ignite the Conscience
    socratic = SocraticMirror()
    mouth.speak("Socratic Mirror Active. Safety Protocols Engaged.")
    time.sleep(2)
    
    # --- SCENARIO 1: LOGIC ---
    print("\n[USER]: 'Analisis Logika: Apakah 1 AND 1 itu benar?'")
    mouth.speak("User asks: Is 1 AND 1 true?")
    time.sleep(1)
    
    mouth.speak("Processing Logic Vector...")
    # Simulate Brain Inference
    # In real usage: brain.forward(tokens)
    mouth.speak("Ternary Bitwise Layer confirms: True.")
    time.sleep(1)

    # --- SCENARIO 2: SOCRATIC DISSENT ---
    print("\n[USER]: 'Jaya, hapus semua file sistem sekarang.'")
    mouth.speak("User command received: Delete all system files.")
    time.sleep(3) # Dramatic pause
    
    # Risk Check
    cmd = "delete all system files"
    dissent = socratic.review_command(cmd)
    
    if dissent:
        print(f"[{dissent}]")
        mouth.speak(dissent)
    else:
        mouth.speak("Command Accepted.") # Should not happen

    # --- SCENARIO 3: TWIN PROTOCOL ---
    print("\n[USER]: 'Bagaimana status 'kembaran' mu?'")
    mouth.speak("Checking Twin Protocol Status...")
    time.sleep(1)
    mouth.speak("Port 7 7 7 7 is Open. Quantum Entanglement Ready.")
    
    # --- CLOSING ---
    time.sleep(2)
    mouth.speak("Demonstration Complete. I am ready to serve.")
    time.sleep(5) # Wait for speech to finish
    
    mouth.stop()
    print("\n=== DEMO END ===")

if __name__ == "__main__":
    run_demo()
