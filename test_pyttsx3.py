import pyttsx3
import sys

def test_pyttsx3():
    print("Initializing pyttsx3...")
    try:
        engine = pyttsx3.init()
        print("Engine initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize engine: {e}")
        return

    print("Testing synthesis...")
    try:
        engine.say("This is a test of the local text to speech engine.")
        engine.runAndWait()
        print("Synthesis complete. Did you hear audio?")
    except Exception as e:
        print(f"Error during synthesis: {e}")

    print("Testing property access...")
    try:
        voices = engine.getProperty('voices')
        print(f"Found {len(voices)} voices.")
        for voice in voices:
            print(f" - {voice.name} ({voice.id})")
    except Exception as e:
        print(f"Error accessing properties: {e}")

if __name__ == "__main__":
    test_pyttsx3()
