import os
import tempfile
import threading

import pyttsx3

# pyttsx3 drivers are not thread-safe; FastAPI runs sync endpoints in a thread
# pool, so requests are serialised here.
_tts_lock = threading.Lock()


def build_ad_script(headline, copy, cta):
    """Join the approved headline, copy and CTA into one natural voice-over script."""
    parts = [p.strip().rstrip(".") for p in (headline, copy, cta) if p and p.strip()]
    return ". ".join(parts) + ("." if parts else "")


def generate_speech(text, rate=165):
    if not text or not text.strip():
        raise ValueError("Ad text cannot be empty.")

    fd, audio_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    with _tts_lock:
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


def remove_audio(path):
    """Delete a temp audio file once it has been sent to the browser."""
    try:
        os.remove(path)
    except OSError:
        pass
