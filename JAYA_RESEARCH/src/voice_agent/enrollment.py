
import os
import time
import argparse
import random
import logging
import threading
import queue
import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write
from pathlib import Path
from src.voice_agent.profile_manager import ProfileManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Enrollment")

class EnrollmentCLI:
    def __init__(self, sample_rate=16000, channels=1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.profile_manager = ProfileManager()
        self.q = queue.Queue()
        self.recording = False
        
        # Sentences for training (mix of wake word and general speech)
        self.sentences = [
            "Jaya, open the research dashboard.",
            "Jaya, what is the latest on the NVIDIA stack?",
            "Jaya, start a new experiment regarding quantum computing.",
            "Hey Jaya, can you analyze this document?",
            "Jaya, stop the current task.",
            "The quick brown fox jumps over the lazy dog.",
            "I need to verify the integrity of the data.",
            "Please initialize the evolution engine.",
            "Jaya, enable silent mode.",
            "Connecting to the neural interface.",
            "Jaya, tell me a joke about AI.",
            "Run the diagnostic sequence immediately.",
            "Jaya, who are you?",
            "Authorize the request.",
            "System status report, Jaya."
        ]

    def record_audio(self, duration=3.0, filename=None):
        """Records audio for a fixed duration."""
        print(f"Recording for {duration} seconds... (Speak Now)")
        try:
            recording = sd.rec(int(duration * self.sample_rate), 
                               samplerate=self.sample_rate, 
                               channels=self.channels, 
                               dtype='int16') # Use int16 for compatibility
            sd.wait()  # Wait until recording is finished
            print("Recording finished.")
            
            if filename:
                write(filename, self.sample_rate, recording)
                return filename, recording
            return None, recording
        except Exception as e:
            logger.error(f"Recording failed: {e}")
            return None, None

    def run(self, num_sentences=10, name="User"):
        print("\n" + "="*50)
        print(f"Starting Voice Enrollment for: {name}")
        print("This process will create a unique voice profile for you.")
        print(f"You will need to read {num_sentences} sentences.")
        print("="*50 + "\n")

        input("Press Enter to begin setup (ensure microphone is ready)...")
        
        # 1. Wake Word Specific Training
        print("\n--- Phase 1: Wake Word Training ---")
        print("Please say 'Jaya' clearly when prompted.")
        
        wake_word_samples = []
        for i in range(3):
            print(f"\nSample {i+1}/3: Say 'Jaya'")
            time.sleep(1) 
            # visual cue
            print(">> LISTEN <<")
            fname = self.profile_manager.sample_dir / "raw" / f"jaya_wake_{int(time.time())}_{i}.wav"
            path, _ = self.record_audio(duration=2.0, filename=str(fname))
            if path:
                wake_word_samples.append(path)
            time.sleep(1)

        # 2. General Sentence Training
        print("\n--- Phase 2: General Voice Verification ---")
        print("Please read the following sentences clearly.")
        
        selected_sentences = random.sample(self.sentences, min(num_sentences, len(self.sentences)))
        general_samples = []
        
        for idx, text in enumerate(selected_sentences):
            print(f"\n({idx+1}/{len(selected_sentences)}) Read this aloud:")
            print(f"--> \"{text}\"")
            
            input("[Press Enter to Record] ")
            fname = self.profile_manager.sample_dir / "raw" / f"jaya_general_{int(time.time())}_{idx}.wav"
            path, _ = self.record_audio(duration=4.0, filename=str(fname))
            if path:
                general_samples.append(path)
            time.sleep(0.5)

        # 3. Generate Profile
        print("\n--- Phase 3: Generating Profile ---")
        all_samples = wake_word_samples + general_samples
        if not all_samples:
            logger.error("No audio samples recorded. Aborting.")
            return

        success = self.profile_manager.enroll_user(name, all_samples)
        
        if success:
            print("\n" + "="*50)
            print("SUCCESS: Voice Profile Created!")
            print(f"Master profile saved at: {self.profile_manager.master_profile_path}")
            print("You can perfectly use 'Jaya' now.")
            print("="*50 + "\n")
        else:
            print("\nFAILED to create profile. Check logs.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jaya Voice Enrollment")
    parser.add_argument("--sentences", type=int, default=10, help="Number of sentences to read")
    parser.add_argument("--name", type=str, default="User", help="Name of the user")
    
    args = parser.parse_args()
    
    cli = EnrollmentCLI()
    cli.run(num_sentences=args.sentences, name=args.name)
