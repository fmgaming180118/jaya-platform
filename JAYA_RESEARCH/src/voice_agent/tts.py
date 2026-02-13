
import pyttsx3
import threading
import queue
import logging

logger = logging.getLogger("JayaMouth")

class JayaMouth(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.engine = None
        self.queue = queue.Queue()
        self.is_running = True
        self.lock = threading.Lock()

    def run(self):
        """
        Dedicated TTS Loop.
        """
        try:
            self.engine = pyttsx3.init()
            # Check for Indonesian Voice
            voices = self.engine.getProperty('voices')
            has_id_voice = False
            for voice in voices:
                v_name = voice.name.lower()
                if "indonesia" in v_name or " id " in v_name or "andika" in v_name or "gadis" in v_name:
                    self.engine.setProperty('voice', voice.id)
                    has_id_voice = True
                    break
            
            if not has_id_voice:
                # Fallback to English but warn
                logger.warning("[Mouth] No Indonesian Offline Voice found. Switching to Online (gTTS) if possible.")
                # We will handle this in the speak loop
            
            self.engine.setProperty('rate', 130) # Slower for clarity
            logger.info("[Mouth] TTS Engine Online.")
            
            while self.is_running:
                try:
                    text_payload = self.queue.get(timeout=1)
                    if text_payload is None: break 
                    
                    text = text_payload
                    
                    # DECISION: Online vs Offline
                    # If we don't have an ID voice and text looks Indonesian, try gTTS
                    use_online = not has_id_voice
                    
                    if use_online:
                        try:
                            import soundfile as sf
                            import sounddevice as sd
                            import os
                            import tempfile
                            import subprocess
                            
                            # Create temp file
                            fd, path = tempfile.mkstemp(suffix='.mp3')
                            os.close(fd)
                            
                            logger.info(f"[Mouth] Speaking Online (Male/ID): {text[:30]}...")
                            
                            # Use Edge TTS CLI (Ardi is Male Indonesian)
                            # edge-tts --text "Hello" --write-media hello.mp3 --voice id-ID-ArdiNeural
                            cmd = [
                                "edge-tts",
                                "--text", text,
                                "--write-media", path,
                                "--voice", "id-ID-ArdiNeural"
                            ]
                            
                            # Run synchronously
                            subprocess.run(cmd, check=True, capture_output=True)
                            
                            # Play it
                            data, fs = sf.read(path)
                            sd.play(data, fs)
                            sd.wait()
                            
                            # Cleanup
                            try:
                                os.remove(path)
                            except: pass
                            
                            continue # Skip pyttsx3
                        except Exception as e:
                            logger.error(f"[Mouth] Online TTS Failed: {e}. Falling back to offline.")
                    
                    # Offline Fallback
                    self.engine.say(text)
                    self.engine.runAndWait()
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"[Mouth] Speaking Error: {e}")
                    
        except Exception as e:
            logger.error(f"[Mouth] Initialization Error: {e}")

    def speak(self, text: str):
        """
        Enqueue text to be spoken.
        """
        logger.info(f"JAYA says: {text}")
        if self.is_running:
            self.queue.put(text)

    def stop(self):
        self.is_running = False
        self.queue.put(None)
        if self.engine:
            self.engine.stop()
