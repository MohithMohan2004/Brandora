import os
import tempfile
import pyttsx3


def generate_speech(text, rate=165):
    if not text or not text.strip():
        raise ValueError("Ad text cannot be empty.")

    fd, audio_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    engine = pyttsx3.init()
    engine.setProperty("rate", rate)
    engine.setProperty("volume", 1.0)

    try:
        engine.save_to_file(text.strip(), audio_path)
        engine.runAndWait()
    finally:
        engine.stop()

    if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
        raise RuntimeError("Speech audio could not be generated.")

    return audio_path
