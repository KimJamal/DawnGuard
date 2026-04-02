from datetime import datetime, timedelta
import json
import os
from config import CONFIG_FILE

class Alarm:
    def __init__(self, alarm_dict=None):
        if alarm_dict:
            self.__dict__.update(alarm_dict)
        else:
            self.id = 0
            self.time = "07:00"
            self.label = "Wake up"
            self.repeat = []
            self.enabled = True
            self.sound = None
            self.volume = 80
            self.fade_in = True
            self.vibrate = False

    def to_dict(self):
        return self.__dict__

    def next_trigger(self):
        now = datetime.now()
        try:
            h, m = map(int, str(self.time).split(':'))
        except (ValueError, AttributeError):
            h, m = 7, 0

        # Build candidate for TODAY first
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        
        # Handle non-repeating alarm (empty list or None)
        if not self.repeat:
            # If time already passed today, move to tomorrow
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate

        # For repeating alarms - normalize repeat days
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        repeat_norm = set()
        for d in self.repeat:
            if not d:
                continue
            d_clean = str(d).strip()
            short = d_clean[:3].title()
            if short in days:
                repeat_norm.add(short)

        # If no valid repeat days after normalization, treat as non-repeating
        if not repeat_norm:
            if candidate <= now:
                candidate += timedelta(days=1)
            return candidate

        today_idx = now.weekday()
        today_name = days[today_idx]
        
        # Check if today is in repeat days and time hasn't passed
        if today_name in repeat_norm:
            if candidate > now:
                return candidate  # Ring later today!

        # Find next occurrence
        for i in range(1, 8):
            check_idx = (today_idx + i) % 7
            check_name = days[check_idx]
            if check_name in repeat_norm:
                next_date = now + timedelta(days=i)
                return next_date.replace(hour=h, minute=m, second=0, microsecond=0)

        # Should never reach here, but fallback
        return candidate + timedelta(days=7)


def load_alarms():
    if not os.path.exists(CONFIG_FILE):
        return []
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
        return [Alarm(d) for d in data]
    except:
        return []


def save_alarms(alarms):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump([a.to_dict() for a in alarms], f, indent=2)
    except Exception as e:
        print(f"Save error: {e}")