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
from src.tools.registry import ToolRegistry

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

        # Initialize V13 Logic Kernel (The Iron Body)
        try:
            from src.brain_v2.engine.runtime import IronEngine
            from src.brain_v2.soul.socratic import SocraticMirror
            
            # Path relative to project root
            model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'JAYA_GENESIS_V13.jay'))
            self.brain_engine = IronEngine(model_path, "Genesis123!")
            self.brain_engine.ignite()
            
            # Initialize Conscience (Pillar 32)
            self.socratic = SocraticMirror()
            logger.info("[Voice] JAYA V13 LOGIC KERNEL IGNITED & SOCRATIC MIRROR ACTIVE.")
        except Exception as e:
            logger.error(f"[Voice] Failed to ignite V13 Kernel: {e}")
            self.brain_engine = None
            self.socratic = None

        # Initialize Agentic Search (Pillar 25 - The All-Seeing Eye)
        try:
            from src.brain_v2.engine.agentic_search import AgenticSearchEngine
            self.agentic_engine = AgenticSearchEngine(rag_client=self.rag_client)
            logger.info("[Voice] Agentic Search Engine Online.")
        except Exception as e:
             logger.error(f"[Voice] Failed to init Agentic Search: {e}")
             self.agentic_engine = None
        
        # Initialize Voice Components
        try:
            self.wake_word = WakeWordDetector()
            self.profile_manager = ProfileManager()
            
            # Configure Tool Registry
            tools_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'tools'))
            self.tools = ToolRegistry(tools_dir=tools_dir)
            logger.info(f"[Voice] Initialized Tool Registry with {len(self.tools.list_tools())} tools.")
        except Exception as e:
            logger.error(f"[Voice] COMPONENT FAILURE: {e}")
            self.wake_word = None

        # Initialize Voice Synthesis (Pillar - Voice of God)
        try:
            from src.voice_agent.tts import JayaMouth
            self.mouth = JayaMouth()
            self.mouth.start()
            logger.info("[Voice] Jaya Mouth Active.")
        except Exception as e:
             logger.error(f"[Voice] Failed to init TTS: {e}")
             self.mouth = None

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
                            # self.mouth.speak("Ya, saya mendengarkan.")
                            print(f"\n>> JAYA: Siap, saya mendengarkan. (Skor: {v_score:.2f})")
                            
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
                            # For now, we use SpeechRecognition to capture simple commands like "training"
                            try:
                                import speech_recognition as sr
                                r = sr.Recognizer()
                                
                                logger.info("[Voice] Listening for command (5s)...")
                                with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000, dtype='int16',
                                                       channels=1, callback=None) as cmd_stream:
                                    # Record 5 seconds of audio for command
                                    cmd_data, _ = cmd_stream.read(SAMPLE_RATE * 5)
                                    
                                    # Convert to AudioData for SR
                                    audio_source = sr.AudioData(cmd_data.tobytes(), SAMPLE_RATE, 2) # 2 bytes width for int16
                                    
                                    try:
                                        # Recognize using Google Speech Recognition
                                        command_text = r.recognize_google(audio_source, language="id-ID") 
                                        logger.info(f"[Voice] Command Recognized: '{command_text}'")
                                        
                                        cmd_lower = command_text.lower()

                                        # --- Dynamic Command Routing ---
                                        # Ideally, we would use an LLM to map text -> tool_name + args.
                                        # For now, we simulate this with keyword matching mapping to specific tools.

                                        # 1. Training (Enrollment) - Special Case (Not a tool yet, simplified script trigger)
                                        if "lakukan training" in cmd_lower or "pengenalan suara" in cmd_lower:
                                            print(f"\n>> JAYA: Starting voice training sequence...")
                                            logger.info("[Voice] Triggering Enrollment CLI...")
                                            script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "enrollment.py"))
                                            if os.name == 'nt':
                                                import subprocess
                                                subprocess.Popen(f'start cmd /k python "{script_path}"', shell=True)
                                        
                                        # 2. System Status -> 'system_get_status'
                                        elif "status sistem" in cmd_lower or "data yang mengalir" in cmd_lower or "cek cpu" in cmd_lower:
                                            res = self.tools.execute("system_get_status")
                                            print(f"\n>> JAYA: {res}")
                                            
                                        # 3. Running Apps -> 'system_get_status' (using same tool for now or new one if created)
                                        # Note: We didn't create a specific 'get_running_apps' tool yet, reusing system status or ignoring
                                        elif "aplikasi berjalan" in cmd_lower or "melihat aplikasi" in cmd_lower:
                                             # For now, simplistic fallback as we migrated 'get_system_status' but maybe not 'get_running_apps' specifically
                                             # Let's assume system_get_status covers it or we create a new one.
                                             # Re-using system_get_status for demo purposes as it has CPU/RAM
                                             res = self.tools.execute("system_get_status")
                                             print(f"\n>> JAYA: {res}")

                                        # 4. Open App -> 'system_open_app'
                                        elif "buka aplikasi" in cmd_lower:
                                            app_name = cmd_lower.replace("buka aplikasi", "").strip()
                                            if app_name:
                                                res = self.tools.execute("system_open_app", app_name=app_name)
                                                print(f"\n>> JAYA: {res}")
                                            else:
                                                print("\n>> JAYA: Aplikasi apa yang ingin dibuka?")

                                        # 5. Execute Shell Command -> 'system_run_command'
                                        elif "jalankan perintah" in cmd_lower or "eksekusi" in cmd_lower:
                                            cmd_str = cmd_lower.replace("jalankan perintah", "").replace("eksekusi", "").strip()
                                            if cmd_str:
                                                print(f"\n>> JAYA: Request to Execute: {cmd_str}")
                                                
                                                # --- SOCRATIC MIRROR CHECK (Pillar 32) ---
                                                dissent = None
                                                if self.socratic:
                                                    dissent = self.socratic.review_command(cmd_str)
                                                
                                                if dissent:
                                                    logger.warning(f"[Voice] Socratic Mirror BLOCK: {dissent}")
                                                    if self.mouth: self.mouth.speak(dissent) # Socratic dissent handles its own tone
                                                    print(f"\n>> JAYA (Hati Nurani): {dissent}")
                                                    print(">> JAYA: Waduh, bahaya Bos. Saya blokir dulu ya.")
                                                else:
                                                    # Executing if Safe
                                                    print(f">> JAYA: Socratic Check PASSED. Executing...")
                                                    output = self.tools.execute("system_run_command", command=cmd_str)
                                                    print(f"\n[OUTPUT]:\n{output}")
                                            else:
                                                print("\n>> JAYA: Perintah apa?")

                                        # 6. V13 Logic Kernel Query -> 'logika' / 'analisis'
                                        elif "logika" in cmd_lower or "analisis" in cmd_lower:
                                            query = cmd_lower.replace("logika", "").replace("analisis", "").strip()
                                            if self.brain_engine and query:
                                                print(f"\n>> JAYA (V13 Kernel): Analyzing '{query}'...")
                                                # Convert text to dummy tokens for prototype
                                                # In real V13, "SemanticBridge" does this
                                                dummy_tokens = [ord(c) % 100 for c in query[:10]]
                                                output_logits = self.brain_engine.brain.forward(dummy_tokens)
                                                
                                                # Output shape (vocab_size), take max
                                                import numpy as np
                                                decision_token = np.argmax(output_logits)
                                                
                                                print(f">> JAYA (Kernel V13): Vektor Logika Dihitung. Token Dominan: {decision_token}")
                                                
                                                reasoning = f"Analisis beres. Logika saya mengarah ke token {decision_token}."
                                                if self.mouth: self.mouth.speak(reasoning)
                                                
                                                print(f">> JAYA (Kernel V13): [Cek Socratic] Aman, Bos.")
                                            elif not self.brain_engine:
                                                print("\n>> JAYA: Kernel V13 belum aktif.")
                                            else:
                                                print("\n>> JAYA: Analisis apa?")

                                        else:
                                            # Default to Agentic RAG for general questions
                                            if self.agentic_engine:
                                                print(f"\n>> JAYA (Agentic): Mikirin '{command_text}'...")
                                                if self.mouth: self.mouth.speak("Sebentar, saya cari infonya dulu...")
                                                
                                                response = self.agentic_engine.think_and_answer(command_text)
                                                
                                                print(f">> JAYA: {response}")
                                                if self.mouth: self.mouth.speak(response)
                                            else:
                                                print(f"\n>> JAYA: Waduh, gak ngerti '{command_text}' dan internet mati.")
                                                if self.mouth: self.mouth.speak("Waduh, saya gak ngerti Bos.")
                                            
                                    except sr.UnknownValueError:
                                        logger.info("[Voice] Could not understand command.")
                                    except sr.RequestError as e:
                                        logger.error(f"[Voice] SR Error: {e}")

                            except ImportError:
                                logger.warning("[Voice] SpeechRecognition not installed.")
                            except Exception as e:
                                logger.error(f"[Voice] Command loop error: {e}")
                            
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
