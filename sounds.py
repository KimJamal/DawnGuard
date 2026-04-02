import pygame
import time
import threading
import os
from config import DEFAULT_VOLUME, FADE_IN_DURATION

pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

def play_alarm(sound_path=None, volume_percent=80, fade_in=True, stop_event=None):
    """
    Plays the alarm sound. If no sound_path is provided, it will remain silent
    to allow the TTS to be the primary alarm sound.
    """
    try:
        if not sound_path or not os.path.exists(sound_path):
            print("[Sound] No sound file provided or file not found. Operating in silent mode (TTS only).")
            # Just wait for the stop event if no sound is playing
            while stop_event and not stop_event.is_set():
                time.sleep(0.5)
            return

        vol = volume_percent / 100.0
        pygame.mixer.music.load(sound_path)

        if fade_in:
            current_vol = 0.0
            step = vol / (FADE_IN_DURATION * 10)
            pygame.mixer.music.set_volume(current_vol)
            pygame.mixer.music.play(-1)
            while stop_event and not stop_event.is_set() and current_vol < vol:
                current_vol = min(current_vol + step, vol)
                pygame.mixer.music.set_volume(current_vol)
                time.sleep(0.1)
        else:
            pygame.mixer.music.set_volume(vol)
            pygame.mixer.music.play(-1)

        while stop_event and not stop_event.is_set() and pygame.mixer.music.get_busy():
            time.sleep(0.2)

    except Exception as e:
        print(f"Sound error: {e}")
        # Removed fallback_beep to ensure no beeps are played
        while stop_event and not stop_event.is_set():
            time.sleep(0.5)

def generate_default_beep():
    # Kept for compatibility but no longer used by play_alarm
    import numpy as np
    import tempfile
    import wave
    sample_rate = 44100
    duration = 1.0
    freq = 600
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio = (np.sin(2 * np.pi * freq * t) * 0.5 * 32767).astype(np.int16)

    fd, path = tempfile.mkstemp(suffix=".wav")
    with wave.open(path, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    os.close(fd)
    return path

def fallback_beep(stop_event):
    # Kept for compatibility but no longer used
    while stop_event and not stop_event.is_set():
        time.sleep(1)
