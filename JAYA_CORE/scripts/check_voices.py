
import pyttsx3

def list_voices():
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    print("--- AVAILABLE VOICES ---")
    for v in voices:
        print(f"Name: {v.name}")
        print(f"ID: {v.id}")
        print("-" * 20)
    
    engine.setProperty('rate', 130)
    engine.say("Halo, nama saya Jaya. Apakah ini lebih jelas?")
    engine.runAndWait()

if __name__ == "__main__":
    list_voices()
