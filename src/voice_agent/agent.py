"""
Jaya Voice Agent using Nimble Pipecat Framework
"""
import os
import sys
import threading
import time
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JayaVoice")


# Ensure we can import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from research.enhanced_rag import EnhancedRAGClient
except ImportError:
    logger.warning("[Voice] Could not import EnhancedRAGClient. RAG features disabled.")
    EnhancedRAGClient = None

from src.voice_agent.wake_word import WakeWordDetector
from src.voice_agent.profile_manager import ProfileManager

class JayaVoiceAgent(threading.Thread):
    def __init__(self, api_key=None, rag_client=None):
        super().__init__()
        self.running = False
        self.loop = None
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self._stop_event = threading.Event()
        
        # Initialize RAG Client
        self.rag_client = rag_client
        if self.rag_client is None and EnhancedRAGClient:
            try:
                self.rag_client = EnhancedRAGClient()
                logger.info("[Voice] RAG Client initialized successfully.")
            except Exception as e:
                logger.error(f"[Voice] Failed to init RAG Client: {e}")
        
        # Initialize Voice Components
        try:
            self.wake_word = WakeWordDetector()
            self.profile_manager = ProfileManager()
            logger.info("[Voice] Wake Word & Profile Manager initialized.")
        except Exception as e:
            logger.error(f"[Voice] COMPONENT FAILURE: {e}")
            self.wake_word = None

    def run(self):
        """Thread main loop"""
        self.running = True
        logger.info("[Voice] Agent Process Started")
        
        try:
            self._run_voice_loop()
        except Exception as e:
            logger.error(f"[Voice] Error in voice loop: {e}")
        finally:
            self.running = False
            logger.info("[Voice] Agent Stopped")

    def stop(self):
        """Signal the agent to stop"""
        self._stop_event.set()
        self.running = False

    def _run_voice_loop(self):
        """
        Native Audio Loop using sounddevice.
        """
        import sounddevice as sd
        import numpy as np

        SAMPLE_RATE = 16000
        CHUNK_SIZE = 1280 # 80ms window for openwakeword

        if not self.wake_word:
            logger.error("[Voice] Wake Word detector not available. Aborting loop.")
            return

        logger.info("[Voice] Listening for 'Jaya' (Active Speaker Verification Enabled)...")
        
        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, blocksize=CHUNK_SIZE, dtype='int16') as stream:
                while not self._stop_event.is_set():
                    if not stream.active:
                        break
                    
                    # Read Chunk
                    data, overflowed = stream.read(CHUNK_SIZE)
                    if overflowed:
                        # logger.warning("Audio buffer overflow")
                        pass
                    
                    # Flatten for processing
                    audio_data = data.flatten()
                    
                    # 1. Wake Word Check
                    prediction = self.wake_word.detect(audio_data)
                    
                    if prediction:
                        ww_label, score = prediction
                        logger.info(f"[Voice] Wake Word Detected: '{ww_label}' (Score: {score:.2f})")
                        
                        # 2. Speaker Verification
                        is_verified, v_score = self.profile_manager.verify_speaker(audio_data)
                        
                        if is_verified:
                            logger.info(f"[Voice] SPEAKER VERIFIED (Score: {v_score:.2f}). Access Granted.")
                            print(f"\n>> JAYA: Yes, I am listening to you. (Verification Score: {v_score:.2f})")
                            
                            # Save the sample for future training
                            try:
                                from scipy.io.wavfile import write
                                timestamp = int(time.time())
                                save_dir = os.path.join("data", "voice_samples", "raw")
                                if not os.path.exists(save_dir):
                                    os.makedirs(save_dir)
                                save_path = os.path.join(save_dir, f"verified_wake_{timestamp}.wav")
                                write(save_path, SAMPLE_RATE, audio_data)
                                logger.info(f"[Voice] Saved verified sample to {save_path}")
                            except Exception as e:
                                logger.error(f"[Voice] Failed to save sample: {e}")

                            # TODO: Enter Active Command Loop (STT)
                            # For now, we simulate a brief "active" window or just acknowledge
                            # In full implementation, this would trigger the speech recognition
                            
                        else:
                            logger.warning(f"[Voice] Access Denied. Speaker Verification Failed (Score: {v_score:.2f}).")
                            print(f"\n>> JAYA: [Ignored Voice] (Verification Failed)")

        except Exception as e:
            logger.error(f"[Voice] Critical Audio Error: {e}")
            if "PortAudio" in str(e):
                logger.error("Please ensure a microphone is connected and configured.")

    def process_query(self, text):
        """
        Process a text query using RAG and LLM (Simulation helper).
        """
        logger.info(f"[Voice] Processing query: '{text}'")
        
        context = ""
        if self.rag_client:
            # Query RAG
            results = self.rag_client.query(text)
            # Assuming query returns a string or list of docs
            if isinstance(results, dict) and "answer" in results:
                 context = results["answer"] # If RAG returns a generated answer
            elif isinstance(results, list): # If returns chunks
                 context = "\n".join([doc.get('content', '') for doc in results[:2]])
            
            logger.info(f"[Voice] Retrieved Context: {context[:100]}...")
        
        # Here we would send (System Prompt + Context + User Query) to LLM
        return f"Response based on context: {context[:500]}..."

if __name__ == "__main__":
    # Test stub
    agent = JayaVoiceAgent()
    agent.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
        agent.join()
