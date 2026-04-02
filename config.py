import os
import json

# === Original variables (backward compatible) ===
APP_NAME = "DawnGuard Alarm"
APP_VERSION = "1.0.0"
GITHUB_REPO = "KimJamal/DawnGuard" # Updated to your actual repo
CONFIG_FILE = "alarms.json"
DEFAULT_VOLUME = 70
FADE_IN_DURATION = 30

# === New settings system ===
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

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