import os
import sys
import datetime

LOG_FILE = "diagnostic_log.txt"

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted_msg + "\n")
    print(formatted_msg) # Still print just in case

def test_elevenlabs():
    # Clear log file
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("--- Diagnostic Log Started ---\n")

    log("Starting test_elevenlabs diagnostic...")
    
    try:
        log("Importing dotenv...")
        from dotenv import load_dotenv
        load_dotenv()
        log("dotenv loaded.")
    except Exception as e:
        log(f"Failed to import/load dotenv: {e}")
        return

    try:
        log("Importing elevenlabs...")
        from elevenlabs import ElevenLabs
        log("elevenlabs imported.")
    except Exception as e:
        log(f"Failed to import elevenlabs: {e}")
        return

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if api_key:
        log(f"API Key found (length: {len(api_key)})")
    else:
        log("ERROR: API Key NOT found in environment.")
        return

    try:
        log("Initializing client...")
        client = ElevenLabs(api_key=api_key)
        log("Client initialized.")
    except Exception as e:
        log(f"Failed to initialize client: {e}")
        return

    try:
        log("Attempting synthesis...")
        generator = client.text_to_speech.convert(
            voice_id="JBFqnCBsd6RMkjVDRZzb",
            text="Hello."
        )
        audio = b"".join(generator)
        log(f"Synthesis successful! {len(audio)} bytes received.")
    except Exception as e:
        log(f"Synthesis FAILED: {e}")
        if hasattr(e, 'body'):
            log(f"Error body: {e.body}")

    log("Diagnostics complete.")

if __name__ == "__main__":
    try:
        test_elevenlabs()
    except Exception as e:
        log(f"CRITICAL SCRIPT FAILURE: {e}")
