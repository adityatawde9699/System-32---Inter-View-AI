import sys

print("1. Python started")
sys.stdout.flush()

try:
    import dotenv
    print("2. dotenv imported")
except ImportError as e:
    print(f"2. dotenv FAILED: {e}")
sys.stdout.flush()

try:
    import elevenlabs
    print("3. elevenlabs imported")
except ImportError as e:
    print(f"3. elevenlabs FAILED: {e}")
sys.stdout.flush()

try:
    from elevenlabs import ElevenLabs
    print("4. ElevenLabs class imported")
except ImportError as e:
    print(f"4. ElevenLabs class FAILED: {e}")

print("5. Done")
