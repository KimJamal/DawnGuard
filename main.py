import os
import random
import threading
import time
import tkinter as tk
import requests
import webbrowser
import subprocess # For running batch script
import sys # For sys.executable
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from distutils.version import LooseVersion # For robust version comparison

import pygame
import pystray
from PIL import Image, ImageDraw

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

from alarm import Alarm, load_alarms, save_alarms
from config import APP_NAME, APP_VERSION, GITHUB_REPO, load_settings
from config import save_settings as save_settings_to_file
from plugins import load_sound_plugins
from sounds import play_alarm
from ui import ModernUI


class AlarmManager:
    def __init__(self):
        self.settings = load_settings()
        self.alarms = load_alarms()
        self.next_id = max((a.id for a in self.alarms), default=0) + 1
        self.running = True
        self.volume_var = None
        self.stop_event = threading.Event()
        self._worker_stop_events = {}

        load_sound_plugins()

        self.root = None
        self.tray_icon = None
        self.ring_window = None
        self.create_tray()

        for alarm in self.alarms:
            if getattr(alarm, "enabled", True):
                self._start_worker(alarm)

        # Check for updates in background
        threading.Thread(target=self.check_for_updates, daemon=True).start()

    def check_for_updates(self):
        """Checks GitHub API for a newer release tag."""
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                latest_version_str = data.get("tag_name", "").replace("v", "")
                
                if latest_version_str:
                    current_version = LooseVersion(APP_VERSION)
                    latest_version = LooseVersion(latest_version_str)

                    if latest_version > current_version:
                        download_url = None
                        for asset in data.get("assets", []):
                            if asset.get("name") == "DawnGuard.exe": # Assuming the EXE name
                                download_url = asset.get("browser_download_url")
                                break
                        
                        if download_url:
                            print(f"[Update] New version available: {latest_version_str}")
                            if self.root:
                                self.root.after(5000, lambda: self._prompt_update(latest_version_str, download_url))
                        else:
                            print(f"[Update] New version {latest_version_str} found, but no DawnGuard.exe asset.")
                    else:
                        print(f"[Update] Current version {APP_VERSION} is up to date.")
            else:
                print(f"[Update] Failed to fetch latest release. Status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[Update] Network error checking for updates: {e}")
        except Exception as e:
            print(f"[Update] Error checking for updates: {e}")

    def _prompt_update(self, version, download_url):
        """Show a modern-styled update prompt and handle in-app download."""
        if messagebox.askyesno(
            "Update Available", 
            f"A new version of {APP_NAME} (v{version}) is available!\n\nWould you like to download and install it now?"
        ):
            self._download_and_install_update(version, download_url)

    def _download_and_install_update(self, version, download_url):
        """Handles downloading the update and preparing for installation."""
        dialog = DownloadProgressDialog(self.root, self, version)
        # Start download in a new thread to keep UI responsive
        threading.Thread(target=self._execute_download, args=(dialog, download_url), daemon=True).start()

    def _execute_download(self, dialog, download_url):
        try:
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            block_size = 1024 # 1 KB
            downloaded_size = 0
            
            # Determine where to save the new EXE
            from config import get_base_dir
            temp_dir = os.path.join(get_base_dir(), "temp_update")
            os.makedirs(temp_dir, exist_ok=True)
            new_exe_path = os.path.join(temp_dir, "DawnGuard_new.exe")

            with open(new_exe_path, "wb") as f:
                for data in response.iter_content(block_size):
                    downloaded_size += len(data)
                    f.write(data)
                    progress = (downloaded_size / total_size) * 100 if total_size else 0
                    self.root.after(0, dialog.update_progress, progress, f"Downloading... {int(progress)}%")
            
            self.root.after(0, dialog.update_progress, 100, "Download Complete. Preparing for restart...")
            self.root.after(1000, dialog.destroy) # Close dialog after a short delay

            # Trigger the replacement and restart logic
            self.root.after(1500, lambda: self._initiate_restart_for_update(new_exe_path))

        except requests.exceptions.RequestException as e:
            self.root.after(0, dialog.destroy)
            messagebox.showerror("Download Error", f"Failed to download update: {e}")
        except Exception as e:
            self.root.after(0, dialog.destroy)
            messagebox.showerror("Update Error", f"An unexpected error occurred: {e}")

    def _initiate_restart_for_update(self, new_exe_path):
        """Creates a batch script to replace the EXE and restarts the app."""
        if not getattr(sys, 'frozen', False):
            messagebox.showinfo("Update Info", "Update downloaded. Please restart the application manually.")
            self.exit_app()
            return

        current_exe = sys.executable
        update_script_path = os.path.join(os.path.dirname(current_exe), "update_DawnGuard.bat")
        
        # Create a simple batch script
        script_content = f"""
@echo off
timeout /t 2 /nobreak > NUL
del "{current_exe}"
move "{new_exe_path}" "{current_exe}"
start "" "{current_exe}"
del "{update_script_path}"
"""
        with open(update_script_path, "w") as f:
            f.write(script_content)
        
        # Execute the batch script and exit the current app
        subprocess.Popen([update_script_path], shell=True, creationflags=subprocess.DETACHED_PROCESS)
        self.exit_app()

    def center_window(self, window, width, height):
        window.update_idletasks()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _start_worker(self, alarm):
        if alarm.id in self._worker_stop_events:
            print(f"[Manager] Stopping existing worker for alarm {alarm.id}")
            self._worker_stop_events[alarm.id].set()
            time.sleep(0.2)

        stop_event = threading.Event()
        self._worker_stop_events[alarm.id] = stop_event

        print(
            f"[Manager] Starting worker for alarm {alarm.id}: '{alarm.label}' at {alarm.time}"
        )
        t = threading.Thread(
            target=self.alarm_worker, args=(alarm, stop_event), daemon=True
        )
        t.start()

    def create_tray(self):
        from config import get_resource_path
        img_path = get_resource_path("assets/DawnGuardImg.png")

        try:
            if os.path.exists(img_path):
                image = Image.open(img_path)
            else:
                image = Image.new("RGB", (64, 64), color="#0f172a")
                draw = ImageDraw.Draw(image)
                draw.ellipse((8, 8, 56, 56), fill="#67e8f9")
        except Exception:
            image = Image.new("RGB", (64, 64), color="#0f172a")

        def on_tray_click(icon, item):
            label = str(item)
            if label == "Show/Hide":
                if self.root and self.root.winfo_viewable():
                    self.hide_to_tray()
                else:
                    self.show_window()
            elif label == "Dismiss Alarm":
                self.stop_event.set()
                pygame.mixer.music.stop()
                if self.ring_window:
                    self.root.after(0, self.ring_window.destroy)
                    self.ring_window = None
                self.notify_toast("Alarm Dismissed", "The alarm has been stopped from the tray.")
            elif label == "Snooze":
                # Find the first active ringing alarm
                # (Simple implementation: snooze whatever is ringing)
                if self.ring_window:
                    # We can't easily get the 'alarm' object here without tracking it
                    # but we can trigger the snooze button logic
                    pass 
            elif label == "Settings":
                self.show_window()
                if self.ui:
                    self.root.after(100, self.ui.open_settings_dialog)
            elif label == "Add New Alarm":
                self.show_window()
                if self.ui:
                    # Select the Add Alarm tab (index 1)
                    self.root.after(100, lambda: self.ui.notebook.select(1))
            elif label == "Exit":
                self.exit_app()

        def get_next_alarm_text(item):
            # Dynamic text for next alarm info
            active = [a for a in self.alarms if getattr(a, "enabled", True)]
            if not active:
                return "No active alarms"
            try:
                next_t = min(a.next_trigger() for a in active)
                return f"Next: {next_t.strftime('%H:%M')} ({next_t.strftime('%A')})"
            except Exception:
                return "Calculating..."

        def is_alarm_ringing(item):
            return self.ring_window is not None and self.ring_window.winfo_exists()

        def is_not_ringing(item):
            return not is_alarm_ringing(item)

        menu = pystray.Menu(
            pystray.MenuItem("Show/Hide", on_tray_click, default=True),
            pystray.MenuItem(get_next_alarm_text, lambda: None, enabled=False),
            pystray.MenuItem("Dismiss Alarm", on_tray_click, visible=is_alarm_ringing),
            pystray.MenuItem("Add New Alarm", on_tray_click, enabled=is_not_ringing),
            pystray.MenuItem("Settings", on_tray_click, enabled=is_not_ringing),
            pystray.MenuItem("Exit", on_tray_click),
        )

        self.tray_icon = pystray.Icon(
            APP_NAME,
            image,
            APP_NAME,
            menu=menu,
        )

        # Run tray icon in its own thread so it doesn't block
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon=None, item=None):
        def _create():
            self.root = tk.Tk()
            self.root.title("DawnGuard")

            # Set Window Icon
            from config import get_resource_path
            ico_path = get_resource_path("assets/DawnGuardIco.ico")
            img_path = get_resource_path("assets/DawnGuardImg.png")

            if os.path.exists(ico_path):
                try:
                    self.root.iconbitmap(ico_path)
                except Exception:
                    pass

            if os.path.exists(img_path):
                try:
                    from PIL import Image, ImageTk

                    pil_img = Image.open(img_path)
                    self.main_icon_photo = ImageTk.PhotoImage(pil_img)
                    self.root.iconphoto(True, self.main_icon_photo)
                except Exception:
                    pass

            self.volume_var = tk.IntVar(value=80, master=self.root)
            self.ui = ModernUI(self.root, self)
            self.root.mainloop()

        if self.root is None:
            _create()
        else:
            try:
                self.root.after(0, self.root.deiconify)
                self.root.after(0, self.root.lift)
                self.root.after(0, self.root.focus_force)
            except Exception:
                # If root was destroyed but not set to None
                _create()

    def hide_to_tray(self):
        if self.root:
            self.root.withdraw()

    def exit_app(self, icon=None, item=None):
        self.running = False
        self.stop_event.set()
        for ev in self._worker_stop_events.values():
            ev.set()
        pygame.mixer.music.stop()
        save_alarms(self.alarms)
        save_settings_to_file(self.settings)
        if self.tray_icon:
            self.tray_icon.stop()
        if self.root:
            self.root.quit()

    def add_alarm(
        self,
        time,
        label,
        repeat=None,
        fade_in=True,
        volume=80,
        vibrate=False,
        sound=None,
        use_tts=True,
    ):
        print(
            f"\n[ADD] Creating new alarm: time='{time}', label='{label}', repeat={repeat}"
        )

        alarm = Alarm()
        alarm.id = self.next_id
        alarm.time = time
        alarm.label = label
        alarm.repeat = repeat or []
        alarm.enabled = True
        alarm.volume = volume
        alarm.fade_in = fade_in
        alarm.vibrate = vibrate
        alarm.sound = sound or self.settings.get("default_sound", "")
        alarm.use_tts = use_tts

        self.next_id += 1
        self.alarms.append(alarm)
        save_alarms(self.alarms)

        if hasattr(self, "ui") and self.ui:
            self.ui.refresh_alarm_cards()

        self._start_worker(alarm)

        print(f"[ADD] Alarm {alarm.id} added successfully\n")
        return alarm

    def delete_alarm(self, alarm):
        print(f"[DELETE] Removing alarm {alarm.id}: '{alarm.label}'")
        if alarm.id in self._worker_stop_events:
            self._worker_stop_events[alarm.id].set()
            del self._worker_stop_events[alarm.id]
        self.alarms = [a for a in self.alarms if a.id != alarm.id]
        save_alarms(self.alarms)
        if hasattr(self, "ui") and self.ui:
            self.ui.refresh_alarm_cards()

    def restart_alarm_worker(self, alarm):
        print(
            f"\n[RESTART] Restarting worker for alarm {alarm.id}: '{alarm.label}' at {alarm.time}"
        )
        self._start_worker(alarm)

    def alarm_worker(self, alarm, stop_event):
        thread_id = threading.current_thread().ident
        print(
            f"[Worker {alarm.id}:{thread_id}] STARTED for '{alarm.label}' at {alarm.time}"
        )
        pre_alarm_triggered = False
        pre_time = self.settings.get("pre_alarm_time", 1) * 60

        while self.running and alarm.enabled and not stop_event.is_set():
            try:
                next_time = alarm.next_trigger()
                now = datetime.now()
                wait_seconds = (next_time - now).total_seconds()

                print(
                    f"[Worker {alarm.id}:{thread_id}] Next: {next_time} (in {wait_seconds:.0f}s)"
                )

                if wait_seconds < -60:
                    print(
                        f"[Worker {alarm.id}:{thread_id}] Time way in past, recalculating..."
                    )
                    time.sleep(1)
                    continue

            except Exception as e:
                print(f"[Worker {alarm.id}:{thread_id}] Error: {e}")
                time.sleep(5)
                continue

            while self.running and alarm.enabled and not stop_event.is_set():
                now = datetime.now()
                remaining = (next_time - now).total_seconds()

                # PRE-ALARM LOGIC
                if (
                    remaining <= pre_time
                    and not pre_alarm_triggered
                    and self.settings.get("pre_alarm_enabled")
                ):
                    pre_alarm_triggered = True
                    if self.root:
                        self.root.after(0, lambda: self._trigger_pre_alarm(alarm))

                if remaining <= 0:
                    break

                sleep_time = min(0.5, max(0.1, remaining))
                time.sleep(sleep_time)

            if stop_event.is_set() or not self.running or not alarm.enabled:
                print(
                    f"[Worker {alarm.id}:{thread_id}] Stopping (stop_event={stop_event.is_set()})"
                )
                break

            print(f"[Worker {alarm.id}:{thread_id}] *** TRIGGERING '{alarm.label}' ***")
            self.trigger_alarm(alarm)

            if not alarm.repeat:
                print(f"[Worker {alarm.id}:{thread_id}] One-time alarm done")
                break
            else:
                print(f"[Worker {alarm.id}:{thread_id}] Repeating, waiting for next...")
                for _ in range(70):
                    if stop_event.is_set() or not self.running:
                        break
                    time.sleep(1)

        print(f"[Worker {alarm.id}:{thread_id}] ENDED")

    def _trigger_pre_alarm(self, alarm):
        """Plays a gentle TTS warning without opening the main puzzle window."""
        if pyttsx3 is None:
            return

        def task():
            try:
                engine = pyttsx3.init()
                engine.setProperty("volume", 0.3)
                engine.say(
                    f"Heads up. Your alarm for {alarm.label} is in {self.settings.get('pre_alarm_time', 1)} minute."
                )
                engine.runAndWait()
                engine.stop()
            except:
                pass

        threading.Thread(target=task, daemon=True).start()

    def notify_toast(self, title, message):
        """Sends a native Windows toast notification."""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            from config import get_resource_path
            # Ensure absolute path for the icon
            ico_path = os.path.abspath(get_resource_path("assets/DawnGuardIco.ico"))
            
            # Use threaded notification to avoid blocking the main app
            # and increase duration slightly for visibility
            threading.Thread(
                target=toaster.show_toast,
                args=(title, message),
                kwargs={
                    "icon_path": ico_path if os.path.exists(ico_path) else None,
                    "duration": 7,
                    "threaded": False
                },
                daemon=True
            ).start()
        except ImportError:
            # Fallback for development if win10toast is missing
            print(f"[TOAST] {title}: {message}")
        except Exception as e:
            print(f"[Notify] Toast Error: {e}")

    def trigger_alarm(self, alarm):
        self.notify_toast("Alarm Triggered!", f"Time for: {alarm.label}")
        self.stop_event.clear()
        use_tts = getattr(alarm, "use_tts", True)
        tts_ran = False

        if use_tts and self.settings.get("tts_enabled", True):
            self.speak_alarm_label(alarm)
            tts_ran = True

        # BACKGROUND SOUND LOGIC
        bg_sound_mode = self.settings.get("bg_sound_mode", "default")
        sound_to_play = alarm.sound
        
        if bg_sound_mode == "random":
            # Try to pick a random sound from the AlarmSounds folder
            from config import get_base_dir
            sounds_dir = os.path.join(get_base_dir(), "AlarmSounds")
            if os.path.exists(sounds_dir):
                files = [f for f in os.listdir(sounds_dir) if f.lower().endswith((".mp3", ".wav", ".ogg"))]
                if files:
                    sound_to_play = os.path.join(sounds_dir, random.choice(files))

        if not tts_ran:
            threading.Thread(
                target=play_alarm,
                args=(sound_to_play, alarm.volume, alarm.fade_in, self.stop_event),
                daemon=True,
            ).start()
        else:
            # Play sound in background at lower volume while TTS is speaking
            # We use 30% of the alarm's volume for the background
            threading.Thread(
                target=play_alarm,
                args=(sound_to_play, alarm.volume * 0.3, False, self.stop_event),
                daemon=True,
            ).start()

        if self.root:
            try:
                self.root.after(0, lambda: self.show_ring_window(alarm))
            except Exception as e:
                print(f"Error showing window: {e}")

        if alarm.vibrate:
            print("Vibrating...")

    def speak_alarm_label(self, alarm):
        if pyttsx3 is None:
            print("[TTS] pyttsx3 not installed")
            return

        if not self.settings.get("tts_enabled", True):
            print("[TTS] Disabled in settings, skipping speech")
            return

        label = (getattr(alarm, "label", "") or "").strip()

        # Strip " (snoozed)" suffix so TTS doesn't read it aloud
        if label.lower().endswith(" (snoozed)"):
            label = label[:-10].strip()

        if not label:
            label = "Alarm"

        print(f"[TTS] Starting dynamic repeating speech for: '{label}'")

        t = threading.Thread(
            target=self._speak_text_worker, args=(label, self.stop_event), daemon=True
        )

        skip_polite = getattr(alarm, "_snooze_penalty_active", False)
        vol_penalty = getattr(alarm, "_volume_penalty", alarm.volume)

        t = threading.Thread(
            target=self._speak_text_worker,
            args=(label, self.stop_event, skip_polite, vol_penalty),
            daemon=True,
        )

        t.start()

    def get_tts_voices(self):
        """Get available TTS voices. Returns list of (id, name) tuples."""
        if pyttsx3 is None:
            return []
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            engine.stop()
            del engine
            return [(v.id, v.name) for v in voices]
        except Exception as e:
            print(f"[TTS] Error getting voices: {e}")
            return []

    def _is_action_phrase(self, label):
        """Detect if the label is an action/command rather than a simple event name."""
        action_starters = [
            "go ",
            "do ",
            "wake ",
            "get ",
            "call ",
            "check ",
            "finish ",
            "start ",
            "stop ",
            "make ",
            "take ",
            "submit ",
            "send ",
            "write ",
            "read ",
            "prepare ",
            "attend ",
            "complete ",
            "review ",
            "update ",
            "clean ",
            "buy ",
            "pick ",
            "drop ",
            "schedule ",
            "remember ",
            "don't forget",
            "please ",
            "time to ",
            "hurry ",
            "move ",
            "leave ",
            "come ",
        ]
        lower = label.lower()
        return any(lower.startswith(s) for s in action_starters)

    def _format_tts_text(self, name_part, label, phrase):
        """Smart formatting based on whether label is an action or event name."""
        words = label.split()
        is_action = self._is_action_phrase(label)

        if len(words) <= 4 and not is_action:
            return f"{phrase}{name_part}. It is time for {label}."
        else:
            return f"{phrase}{name_part}. {label}."

    def _speak_text_worker(
        self, label, stop_event, skip_polite=False, volume_penalty=1.0
    ):
        try:
            loop_count = 0
            from config import get_base_dir
            suggest_file = os.path.join(get_base_dir(), "suggest.text")
            name = self.settings.get("user_name", "").strip()
            name_part = f" {name}" if name else ""
            rate = self.settings.get("tts_rate", 160)
            saved_voice_id = self.settings.get("voice_id", "")
            esc_speed = self.settings.get("tts_escalation_speed", 10)
            max_aggression = self.settings.get("max_aggression_level", "unhinged")
            dynamic_vol = self.settings.get("dynamic_tts_volume", True)

            # Calculate max loops based on setting
            max_loops = {"polite": 5, "firm": 10, "unhinged": 999}.get(
                max_aggression, 999
            )

            # Pre-load custom phrases to ensure variety
            custom_phrases = []
            if os.path.exists(suggest_file):
                try:
                    with open(suggest_file, "r", encoding="utf-8") as f:
                        custom_phrases = [line.strip() for line in f if line.strip()]
                except:
                    pass

            while not stop_event.is_set() and loop_count < max_loops:
                # Adjust loop count if snooze penalty is active
                effective_loop = loop_count + (5 if skip_polite else 0)

                # 1. Determine Phrase (Progressive variety)
                if effective_loop == 0:
                    phrase = f"Attention. It is time for {label}."
                elif effective_loop == 1:
                    phrase = f"Wake up! Your {label} alarm is ringing."
                elif effective_loop <= 4:
                    phrase = random.choice([
                        f"Hey there! Please, it is time for {label}. Let's get moving.",
                        f"Time to wake up! Don't forget about {label}.",
                        f"Good morning! {label} is waiting for you."
                    ])
                elif effective_loop <= 9:
                    phrase = random.choice([
                        f"Excuse me! You really need to wake up now. It is time for {label}!",
                        f"Are you still sleeping? It's {label} time!",
                        f"Rise and shine! {label} won't wait!"
                    ])
                elif effective_loop <= 15:
                    phrase = random.choice([
                        f"Wake up! Wake up! You are going to be late for {label}!",
                        f"Stop ignoring me! It is time for {label} right now!",
                        f"This is not a drill! Get up for {label}!"
                    ])
                else:
                    if custom_phrases:
                        phrase = random.choice(custom_phrases)
                    else:
                        phrase = f"I cannot believe this. We had a deal about {label}."

                text = f"{phrase}{name_part}."

                # 2. Dynamic Volume Logic
                tts_vol = 1.0
                sound_vol = volume_penalty
                if dynamic_vol:
                    if effective_loop <= 4:
                        tts_vol, sound_vol = 1.0, volume_penalty * 0.3
                    elif effective_loop <= 15:
                        tts_vol, sound_vol = 1.0, volume_penalty * 0.5
                    else:
                        tts_vol, sound_vol = 1.0, volume_penalty * 0.7

                # Adjust background sound volume dynamically
                try:
                    pygame.mixer.music.set_volume(max(0.0, min(1.0, sound_vol / 100.0)))
                except:
                    pass

                # 3. Speak
                engine = pyttsx3.init()
                voices = engine.getProperty("voices")
                if saved_voice_id:
                    for voice in voices:
                        if voice.id == saved_voice_id:
                            engine.setProperty("voice", voice.id)
                            break
                    else:
                        for voice in voices:
                            if "Zira" in voice.name:
                                engine.setProperty("voice", voice.id)
                                break
                            elif voices:
                                engine.setProperty("voice", voices[0].id)
                else:
                    for voice in voices:
                        if "Zira" in voice.name:
                            engine.setProperty("voice", voice.id)
                            break
                        elif voices:
                            engine.setProperty("voice", voices[0].id)

                engine.setProperty("rate", rate)
                engine.setProperty("volume", tts_vol)
                engine.say(text)
                engine.runAndWait()
                engine.stop()
                del engine

                loop_count += 1

                # 4. Wait using Escalation Speed setting
                # While waiting, we keep the background music playing
                for _ in range(int(esc_speed * 10)):
                    if stop_event.is_set():
                        break
                    time.sleep(0.1)

            print("[TTS] Repeating speech stopped")
        except Exception as e:
            print(f"[TTS] Error: {e}")

    def center_window(self, window, width, height):
        window.update_idletasks()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def show_ring_window(self, alarm):
        try:
            if self.ring_window and self.ring_window.winfo_exists():
                self.ring_window.lift()
                return

            win = tk.Toplevel(self.root)
            self.ring_window = win
            win.title("Wake Up!")
            self.center_window(win, 420, 580)

            # Set Window Icon
            from config import get_resource_path
            ico_path = get_resource_path("assets/DawnGuardIco.ico")
            img_path = get_resource_path("assets/DawnGuardImg.png")

            if os.path.exists(ico_path):
                try:
                    win.iconbitmap(ico_path)
                except Exception:
                    pass

            if os.path.exists(img_path):
                try:
                    from PIL import Image, ImageTk

                    pil_img = Image.open(img_path)
                    self.ring_icon_photo = ImageTk.PhotoImage(pil_img)
                    win.iconphoto(True, self.ring_icon_photo)
                except Exception:
                    pass

            win.configure(bg="#0f172a")
            win.transient(self.root)
            win.grab_set()
            win.focus_force()

            # Scrolling label
            scroll_container = tk.Frame(
                win, bg="#1e2937", height=80, bd=1, relief="flat"
            )
            scroll_container.pack(fill="x", pady=(30, 10), padx=20)
            scroll_container.pack_propagate(False)
            canvas = tk.Canvas(
                scroll_container, bg="#1e2937", highlightthickness=0, height=80
            )
            canvas.pack(fill="both", expand=True)
            display_text = f"  {alarm.label}  •  " * 10
            text_id = canvas.create_text(
                10,
                40,
                text=display_text,
                font=("Segoe UI", 22, "bold"),
                fill="#67e8f9",
                anchor="w",
            )
            text_bbox = canvas.bbox(text_id)
            text_width = text_bbox[2] - text_bbox[0]

            def auto_scroll():
                if not win.winfo_exists():
                    return
                canvas.move(text_id, -1, 0)
                x1, y1, x2, y2 = canvas.bbox(text_id)
                if x2 < 400:
                    canvas.move(text_id, text_width // 2, 0)
                win.after(30, auto_scroll)

            win.after(100, auto_scroll)

            # --- AUTO STOP TIMER (Save Relationships) ---
            start_time = time.time()
            auto_stop_min = self.settings.get("auto_stop_minutes", 15)

            def auto_stop_check():
                if not win.winfo_exists():
                    return
                if time.time() - start_time > (auto_stop_min * 60):
                    print("[ALARM] Auto-stop triggered. Saving relationships.")
                    self.stop_event.set()
                    pygame.mixer.music.stop()
                    win.destroy()
                    self.ring_window = None
                    return
                win.after(5000, auto_stop_check)

            win.after(5000, auto_stop_check)

            # --- PUZZLE SELECTION ---
            puzzle_type = self.settings.get("puzzle_type", "math")
            puzzle_frame = tk.Frame(win, bg="#0f172a")
            puzzle_frame.pack(fill="x", padx=20)

            def dismiss():
                self.stop_event.set()
                pygame.mixer.music.stop()
                win.destroy()
                self.ring_window = None

            if puzzle_type == "math":
                # MATH PUZZLE
                difficulty = self.settings.get("math_difficulty", "medium")
                if difficulty == "easy":
                    num1, num2, op, answer = (
                        random.randint(1, 10),
                        random.randint(1, 9),
                        "+",
                        random.randint(1, 10) + random.randint(1, 9),
                    )
                elif difficulty == "hard":
                    if random.random() < 0.5:
                        num1, num2, op, answer = (
                            random.randint(2, 12),
                            random.randint(2, 12),
                            "×",
                            random.randint(2, 12) * random.randint(2, 12),
                        )
                    else:
                        num1, num2, op, answer = (
                            random.randint(10, 50),
                            random.randint(10, 50),
                            "+",
                            random.randint(10, 50) + random.randint(10, 50),
                        )
                else:
                    num1, num2, op, answer = (
                        random.randint(1, 25),
                        random.randint(1, 24),
                        "+",
                        random.randint(1, 25) + random.randint(1, 24),
                    )

                tk.Label(
                    puzzle_frame,
                    text=f"What is {num1} {op} {num2}?",
                    font=("Segoe UI", 16),
                    bg="#0f172a",
                    fg="white",
                ).pack(pady=20)
                entry = ttk.Entry(puzzle_frame, font=("Segoe UI", 14))
                entry.pack(pady=10, ipadx=20)
                entry.focus_set()

                def check_math():
                    try:
                        if int(entry.get()) == answer:
                            dismiss()
                        else:
                            messagebox.showwarning("Wrong", "Try again!")
                    except:
                        messagebox.showwarning("Invalid", "Enter a number")

                win.bind("<Return>", lambda e: check_math())
                ttk.Button(
                    puzzle_frame, text="Dismiss (Solve Math)", command=check_math
                ).pack(pady=10)

            elif puzzle_type == "word":
                # TYPING WORD PUZZLE
                words = [
                    "Algorithms",
                    "Symphony",
                    "Phenomenon",
                    "Encryption",
                    "Galaxies",
                    "Mysterious",
                    "Complicated",
                    "Discipline",
                    "Awakening",
                    "Chemistry",
                ]
                word = random.choice(words)
                tk.Label(
                    puzzle_frame,
                    text="Type this word to dismiss:",
                    font=("Segoe UI", 12),
                    bg="#0f172a",
                    fg="#94a3b8",
                ).pack(pady=(20, 5))
                tk.Label(
                    puzzle_frame,
                    text=word,
                    font=("Segoe UI", 24, "bold"),
                    bg="#0f172a",
                    fg="#67e8f9",
                ).pack()

                entry = ttk.Entry(puzzle_frame, font=("Segoe UI", 18), justify="center")
                entry.pack(pady=15, ipadx=20, ipady=5)
                entry.focus_set()

                def check_word(e=None):
                    if entry.get().lower().strip() == word.lower():
                        dismiss()

                entry.bind("<KeyRelease>", check_word)
                tk.Label(
                    puzzle_frame,
                    text="(Typing auto-dismisses when correct)",
                    font=("Segoe UI", 9),
                    bg="#0f172a",
                    fg="#475569",
                ).pack()

            elif puzzle_type == "simon":
                # SIMON SAYS PUZZLE
                difficulty = self.settings.get("math_difficulty", "medium")
                seq_len = {"easy": 3, "medium": 4, "hard": 6}.get(difficulty, 4)
                colors = ["#ef4444", "#22c55e", "#3b82f6", "#eab308"]
                sequence = [random.randint(0, 3) for _ in range(seq_len)]
                user_sequence = []

                tk.Label(
                    puzzle_frame,
                    text="Watch the sequence, then repeat it!",
                    font=("Segoe UI", 12),
                    bg="#0f172a",
                    fg="white",
                ).pack(pady=10)

                simon_grid = tk.Frame(puzzle_frame, bg="#0f172a")
                simon_grid.pack(pady=10)
                btns = []
                for i in range(4):
                    b = tk.Button(
                        simon_grid,
                        bg=colors[i],
                        width=6,
                        height=3,
                        bd=0,
                        state="disabled",
                    )
                    b.grid(row=i // 2, column=i % 2, padx=5, pady=5)
                    btns.append(b)

                status_lbl = tk.Label(
                    puzzle_frame,
                    text="Showing sequence...",
                    font=("Segoe UI", 11, "bold"),
                    bg="#0f172a",
                    fg="#eab308",
                )
                status_lbl.pack()

                def flash_sequence(idx=0):
                    if idx >= len(sequence):
                        for b in btns:
                            b.config(state="normal")
                        status_lbl.config(text="Your turn! Click the colors.")
                        return
                    c = sequence[idx]
                    btns[c].config(bg="white")
                    win.after(500, lambda: btns[c].config(bg=colors[c]))
                    win.after(900, lambda: flash_sequence(idx + 1))

                win.after(1000, flash_sequence)

                def on_click(c):
                    if status_lbl.cget("text") == "Showing sequence...":
                        return
                    user_sequence.append(c)
                    btns[c].config(bg="white")
                    win.after(200, lambda: btns[c].config(bg=colors[c]))

                    if user_sequence[-1] != sequence[len(user_sequence) - 1]:
                        status_lbl.config(text="Wrong! Restarting sequence...")
                        user_sequence.clear()
                        for b in btns:
                            b.config(state="disabled")
                        win.after(1500, lambda: flash_sequence(0))
                        return

                    if len(user_sequence) == len(sequence):
                        status_lbl.config(text="Correct! Dismissing...")
                        win.after(500, dismiss)

                for i, b in enumerate(btns):
                    b.config(command=lambda idx=i: on_click(idx))

            # Snooze Section
            snooze_frame = tk.Frame(win, bg="#0f172a")
            snooze_frame.pack(pady=20)
            snooze_min = self.settings.get("snooze_duration", 9)
            snooze_btn = ttk.Button(
                snooze_frame,
                text=f"Snooze {snooze_min} min",
                command=lambda: self.snooze(alarm, win),
            )
            snooze_btn.pack(side="left", padx=(0, 8))
            snooze_gear = tk.Label(
                snooze_frame,
                text="⚙",
                font=("Segoe UI", 13),
                bg="#0f172a",
                fg="#94a3b8",
                cursor="hand2",
            )
            snooze_gear.pack(side="left")
            snooze_gear.bind(
                "<Button-1>", lambda e: self._open_snooze_settings(alarm, win)
            )

        except Exception as e:
            print(f"Error in ring window: {e}")

    def _open_snooze_settings(self, alarm, ring_win):
        """Small modal to adjust snooze time, save it, then snooze."""
        dialog = tk.Toplevel(ring_win)
        dialog.title("Snooze Settings")
        dialog.geometry("300x210")

        # Set Window Icon
        from config import get_resource_path
        ico_path = get_resource_path("assets/DawnGuardIco.ico")
        if os.path.exists(ico_path):
            try:
                dialog.iconbitmap(ico_path)
            except Exception:
                pass

        dialog.configure(bg="#0f172a")
        dialog.resizable(False, False)
        dialog.transient(ring_win)
        try:
            dialog.grab_set()
        except Exception:
            pass

        default_min = self.settings.get("snooze_duration", 9)

        tk.Label(
            dialog,
            text="Snooze for how many minutes?",
            bg="#0f172a",
            fg="white",
            font=("Segoe UI", 11),
        ).pack(pady=(20, 10))

        var = tk.IntVar(value=default_min)
        spin = tk.Spinbox(
            dialog,
            from_=1,
            to=60,
            textvariable=var,
            width=5,
            font=("Segoe UI", 18, "bold"),
            bg="#1e2937",
            fg="#67e8f9",
            buttonbackground="#1e2937",
            bd=0,
            highlightthickness=0,
            justify="center",
        )
        spin.pack(pady=5)
        spin.focus_set()
        spin.selection_range(0, "end")

        def do_snooze():
            try:
                minutes = max(1, int(var.get()))
            except Exception:
                minutes = default_min
            self.settings["snooze_duration"] = minutes
            save_settings_to_file(self.settings)
            dialog.destroy()
            self.snooze(alarm, ring_win, duration=minutes)

        def on_enter(e):
            do_snooze()

        dialog.bind("<Return>", on_enter)

        btn_row = tk.Frame(dialog, bg="#0f172a")
        btn_row.pack(pady=15)

        tk.Button(
            btn_row,
            text="SNOOZE",
            font=("Segoe UI", 11, "bold"),
            bg="#22c55e",
            fg="white",
            bd=0,
            cursor="hand2",
            command=do_snooze,
        ).pack(side="left", padx=6, ipadx=16, ipady=4)

        def just_close():
            dialog.destroy()

        tk.Button(
            btn_row,
            text="Cancel",
            font=("Segoe UI", 11),
            bg="#1e2937",
            fg="#94a3b8",
            bd=0,
            cursor="hand2",
            command=just_close,
        ).pack(side="left", padx=6, ipadx=16, ipady=4)

    def snooze(self, alarm, win, duration=None):
        self.stop_event.set()
        pygame.mixer.music.stop()
        win.destroy()
        self.ring_window = None

        snooze_duration = (
            duration
            if duration is not None
            else self.settings.get("snooze_duration", 9)
        )
        self.notify_toast("Alarm Snoozed", f"I'll wake you up in {snooze_duration} minutes.")
        snooze_alarm = Alarm()
        snooze_alarm.id = self.next_id
        snooze_alarm.time = (
            datetime.now() + timedelta(minutes=snooze_duration)
        ).strftime("%H:%M")
        snooze_alarm.label = alarm.label + " (snoozed)"
        snooze_alarm.repeat = []
        snooze_alarm.volume = alarm.volume

        # SNOOZE PENALTIES
        if self.settings.get("snooze_penalty", False):
            snooze_alarm._snooze_penalty_active = True
            snooze_alarm._volume_penalty = min(
                100, alarm.volume + 10
            )  # Increase base vol by 10%

        self.next_id += 1
        self.alarms.append(snooze_alarm)
        save_alarms(self.alarms)
        self._start_worker(snooze_alarm)


class DownloadProgressDialog(tk.Toplevel):
    def __init__(self, parent, manager, version):
        super().__init__(parent)
        self.manager = manager
        self.version = version
        self.title("Downloading Update")
        self.geometry("350x150")
        self.resizable(False, False)
        self.configure(bg="#0f172a")
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_closing) # Handle window close

        self.manager.center_window(self, 350, 150)

        tk.Label(
            self,
            text=f"Downloading DawnGuard v{version}...",
            bg="#0f172a",
            fg="white",
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=15)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
            length=300,
        )
        self.progress_bar.pack(pady=5)

        self.status_label = tk.Label(
            self,
            text="Connecting...",
            bg="#0f172a",
            fg="#cbd5e1",
            font=("Segoe UI", 9),
        )
        self.status_label.pack()

    def update_progress(self, value, status_text=""):
        self.progress_var.set(value)
        if status_text:
            self.status_label.config(text=status_text)
        self.update_idletasks()

    def _on_closing(self):
        messagebox.showwarning("Download in Progress", "Please wait for the download to complete.")
        # Optionally, add logic to cancel download if user insists


if __name__ == "__main__":
    # Fix for custom taskbar icon on Windows
    try:
        import ctypes
        myappid = 'com.dawnguard.alarm.v1' # arbitrary string
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    manager = AlarmManager()
    manager.show_window()
