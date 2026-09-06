"""Manual network/audio smoke check; excluded from the offline unit suite."""
from gtts import gTTS
import soundfile as sf
import sounddevice as sd
import os
import tempfile

def test_gtts():
    print("Testing gTTS...")
    try:
        # Create audio
        tts = gTTS(text="Halo, ini adalah suara Google Bahasa Indonesia. Apakah ini lebih jelas?", lang='id')
        fd, path = tempfile.mkstemp(suffix='.mp3')
        os.close(fd)
        
        print("Saving MP3...")
        tts.save(path)
        
        print("Playing...")
        data, fs = sf.read(path)
        sd.play(data, fs)
        sd.wait()
        
        print("Success.")
        os.remove(path)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_gtts()
