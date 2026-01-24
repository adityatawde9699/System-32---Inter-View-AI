import os
import sys
from dotenv import load_dotenv
from elevenlabs import ElevenLabs

# Force unbuffered stdout
sys.stdout.reconfigure(line_buffering=True)

def test_elevenlabs():
    print("--- Starting ElevenLabs Diagnostic ---")
    
    # Load environment variables
    load_dotenv()
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    print(f"API Key present: {bool(api_key)}")
    if api_key:
        print(f"API Key length: {len(api_key)}")
        print(f"API Key prefix: {api_key[:4]}...")

    if not api_key:
        print("ERROR: No API key found in environment.")
        return

    print("Initializing ElevenLabs client...")
    try:
        client = ElevenLabs(api_key=api_key)
        print("Client initialized.")
    except Exception as e:
        print(f"FATAL: Failed to initialize client: {e}")
        return

    print("Attempting synthesis (lightweight, 1 char)...")
    try:
        # Saving audio to avoid playing it, just want to test API
        generator = client.text_to_speech.convert(
            voice_id="JBFqnCBsd6RMkjVDRZzb", # Default 'George'
            text="."
        )
        # Consume generator to ensure request is made
        audio_bytes = b"".join(generator)
        print(f"Synthesis successful! Received {len(audio_bytes)} bytes.")
    except Exception as e:
        print(f"FATAL: Synthesis failed: {e}")
        # Print full error details if available
        if hasattr(e, 'body'):
            print(f"Error body: {e.body}")

    print("--- Diagnostic Complete ---")

if __name__ == "__main__":
    test_elevenlabs()
