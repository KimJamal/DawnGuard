import os
import json
import sys

def get_base_dir():
    """Get the correct base directory whether running as script or bundled EXE."""
    if getattr(sys, 'frozen', False):
        # Running as a bundled EXE
        # For AlarmSounds, settings.json, alarms.json, we want them next to the EXE
        return os.path.dirname(sys.executable)
    # Running as a script
    return os.path.dirname(os.path.abspath(__file__))

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# === Original variables (backward compatible) ===
APP_NAME = "DawnGuard Alarm"
APP_VERSION = "1.0.1"
GITHUB_REPO = "KimJamal/DawnGuard" # Updated to your actual repo
CONFIG_FILE = os.path.join(get_base_dir(), "alarms.json")
DEFAULT_VOLUME = 70
FADE_IN_DURATION = 30

# === New settings system ===
SETTINGS_FILE = os.path.join(get_base_dir(), "settings.json")

DEFAULT_SETTINGS = {
    "user_name": "",
    "tts_enabled": True,
    "tts_rate": 160,
    "voice_id": "",
    "default_volume": 80,
    "default_fade_in": True,
    "default_sound": "",
    "snooze_duration": 9,
    "math_difficulty": "medium",
    # Add these to your DEFAULT_SETTINGS dict:
    "tts_escalation_speed": 10,       # Seconds between TTS loops
    "max_aggression_level": "unhinged",# "polite", "firm", "unhinged"
    "snooze_penalty": True,            # Skip polite phase if snoozed
    "pre_alarm_enabled": False,        # Heads up warning
    "pre_alarm_time": 1,               # Minutes before alarm
    "auto_stop_minutes": 15,           # Save relationships timer
    "puzzle_type": "math",             # "math", "word", "simon"
    "use_24h_format": True,            # Clock format
    "dynamic_tts_volume": True,        # TTS gets louder, sound gets quieter
}


def load_settings():
    """Load settings from JSON file, falling back to defaults."""
    settings = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                settings.update(loaded)
        except Exception as e:
            print(f"[Config] Error loading settings: {e}")
    return settings


def save_settings(settings):
    """Save settings dict to JSON file."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        print("[Config] Settings saved.")
    except Exception as e:
        print(f"[Config] Error saving settings: {e}")