import json
import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote, unquote

import pygame
import requests


class ToolTip:
    """Lightweight tooltip that appears on hover and disappears on leave."""

    def __init__(
        self,
        widget,
        text,
        bg="#334155",
        fg="#f1f5f9",
        font=("Segoe UI", 9),
        padx=8,
        pady=4,
        offset_x=0,
        offset_y=24,
    ):
        self.widget = widget
        self.text = text
        self.bg = bg
        self.fg = fg
        self.font = font
        self.padx = padx
        self.pady = pady
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.tw = None
        self._scheduled = None

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress-1>", self._on_leave, add="+")

    def _on_enter(self, event=None):
        self._scheduled = self.widget.after(300, self._show)

    def _on_leave(self, event=None):
        if self._scheduled:
            self.widget.after_cancel(self._scheduled)
            self._scheduled = None
        self._hide()

    def _show(self):
        self._scheduled = None
        if self.tw:
            return
        x = self.widget.winfo_rootx() + self.offset_x
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + self.offset_y
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        self.tw.attributes("-topmost", True)
        try:
            self.tw.attributes("-alpha", 0.95)
        except Exception:
            pass
        label = tk.Label(
            self.tw,
            text=self.text,
            bg=self.bg,
            fg=self.fg,
            font=self.font,
            padx=self.padx,
            pady=self.pady,
            highlightthickness=1,
            highlightbackground="#475569",
            relief="flat",
        )
        label.pack()

    def _hide(self):
        if self.tw:
            self.tw.destroy()
            self.tw = None


class OnlineSoundBrowser(tk.Toplevel):
    """A window to browse, preview, and download sounds from GitHub."""

    def __init__(self, parent, colors, sound_dir, callback):
        super().__init__(parent)
        self.title("Online Sound Browser")
        self.geometry("500x600")
        self.colors = colors
        self.sound_dir = sound_dir
        self.on_select_callback = callback
        self.configure(bg=colors["bg"])

        # --- FIX: ACT LIKE A PROPER MODAL DIALOG ---
        self.transient(parent)  # Ties this window strictly to the Settings dialog
        self.attributes("-topmost", True)
        self.grab_set()  # FREEZES the Settings window until this one is closed
        self.focus_force()  # Steals focus immediately

        # GitHub details for DawnGuard
        self.repo_owner = "KimJamal"
        self.repo_name = "DawnGuard"
        self.sounds_path = "Sounds"
        self.branch = "main"

        self.sounds = []
        self._playing_index = -1
        self._temp_file = None
        self._preview_check_id = None
        self._dots_after_id = None
        self.use_canvases = {}

        self._setup_ui()
        self._fetch_sounds()

    def _setup_ui(self):
        header = tk.Frame(self, bg=self.colors["card"], padx=20, pady=15)
        header.pack(fill="x")

        tk.Label(
            header,
            text="🌐 GitHub Sound Browser",
            bg=self.colors["card"],
            fg=self.colors["primary"],
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        tk.Label(
            header,
            text=f"{self.repo_owner}/{self.repo_name}",
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 10),
        ).pack(side="right")

        self.content_frame = tk.Frame(self, bg=self.colors["bg"], padx=20, pady=10)
        self.content_frame.pack(fill="both", expand=True)

        self.status_label = tk.Label(
            self.content_frame,
            text="Fetching sounds from GitHub...",
            bg=self.colors["bg"],
            fg=self.colors["text"],
            font=("Segoe UI", 11),
        )
        self.status_label.pack(pady=50)

        self.list_container = tk.Frame(self.content_frame, bg=self.colors["bg"])

        self.canvas = tk.Canvas(
            self.list_container, bg=self.colors["bg"], highlightthickness=0, bd=0
        )
        self.scrollbar = ttk.Scrollbar(
            self.list_container, orient="vertical", command=self.canvas.yview
        )
        self.scrollable_frame = tk.Frame(self.canvas, bg=self.colors["bg"])

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        # --- FIX: SAFE SCROLLING (NO bind_all which breaks other windows) ---
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _on_mousewheel_linux_up(event):
            self.canvas.yview_scroll(-1, "units")

        def _on_mousewheel_linux_down(event):
            self.canvas.yview_scroll(1, "units")

        self.canvas.bind("<MouseWheel>", _on_mousewheel)
        self.canvas.bind("<Button-4>", _on_mousewheel_linux_up)
        self.canvas.bind("<Button-5>", _on_mousewheel_linux_down)

    def _fetch_sounds(self):
        def task():
            try:
                url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/contents/{self.sounds_path}?ref={self.branch}"
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                files = response.json()

                audio_files = []
                for f in files:
                    if f["type"] == "file" and f["name"].lower().endswith(
                        (".mp3", ".wav", ".ogg")
                    ):
                        audio_files.append(
                            {
                                "name": f["name"],
                                "download_url": f["download_url"],
                                "size": f["size"],
                            }
                        )

                if self.winfo_exists():
                    self.after(0, lambda: self._on_sounds_fetched(audio_files))
            except Exception as e:
                error_msg = str(e)
                if self.winfo_exists():
                    self.after(0, lambda: self._on_fetch_error(error_msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_sounds_fetched(self, sounds):
        self.sounds = sounds
        self.status_label.pack_forget()

        if not sounds:
            self.status_label.config(
                text="No audio files found in the 'Sounds' folder."
            )
            self.status_label.pack(pady=50)
            return

        self.list_container.pack(fill="both", expand=True)

        # Scroll functions for rows
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _up(event):
            self.canvas.yview_scroll(-1, "units")

        def _down(event):
            self.canvas.yview_scroll(1, "units")

        for i, sound in enumerate(sounds):
            row = self._build_sound_row(i, sound)
            # Bind scrolling directly to the row widgets (safe!)
            for widget in row.winfo_children():
                widget.bind("<MouseWheel>", _on_mousewheel)
                widget.bind("<Button-4>", _up)
                widget.bind("<Button-5>", _down)

        # Bottom padding
        tk.Frame(self.scrollable_frame, bg=self.colors["bg"], height=60).pack()

    def _on_fetch_error(self, error):
        self.status_label.config(
            text=f"Error connecting to GitHub:\n{error}", fg=self.colors["danger"]
        )

    def _build_sound_row(self, index, sound):
        row = tk.Frame(self.scrollable_frame, bg=self.colors["card"], pady=10, padx=15)
        row.pack(fill="x", pady=5)

        btn_frame = tk.Frame(row, bg=self.colors["card"])
        btn_frame.pack(side="right", padx=(10, 0))

        preview_btn = tk.Button(
            btn_frame,
            text="▶ Preview",
            bg=self.colors["primary"],
            fg=self.colors["bg"],
            font=("Segoe UI", 9),
            bd=0,
            padx=10,
            cursor="hand2",
            command=lambda: self._preview_sound(index, preview_btn),
        )
        preview_btn.pack(side="left", padx=(0, 5))

        use_canvas = tk.Canvas(
            btn_frame,
            width=85,
            height=32,
            bg="#22c55e",
            highlightthickness=0,
            cursor="hand2",
        )
        use_canvas.pack(side="left")
        use_canvas.create_rectangle(0, 0, 85, 32, fill="#22c55e", outline="")
        use_canvas.create_text(
            42, 16, text="Use This", fill="white", font=("Segoe UI", 9, "bold")
        )

        self.use_canvases[index] = use_canvas
        use_canvas.bind("<Button-1>", lambda e: self._download_and_use(index))

        name_frame = tk.Frame(row, bg=self.colors["card"])
        name_frame.pack(side="left", fill="both", expand=True)

        name = sound["name"]
        display_name = name if len(name) <= 35 else name[:32] + "..."
        name_label = tk.Label(
            name_frame,
            text=display_name,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        name_label.pack(fill="x")
        ToolTip(name_label, name)

        size_kb = sound["size"] / 1024
        tk.Label(
            name_frame,
            text=f"{size_kb:.1f} KB",
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill="x")

        return row

    def _preview_sound(self, index, btn_widget=None):
        if self._playing_index == index:
            pygame.mixer.music.stop()
            self._stop_dots(btn_widget)
            if btn_widget and btn_widget.winfo_exists():
                btn_widget.config(text="▶ Preview", bg=self.colors["primary"])
            self._playing_index = -1
            if self._preview_check_id:
                self.after_cancel(self._preview_check_id)
            return

        self._start_dots(btn_widget)
        sound = self.sounds[index]
        url = sound["download_url"]

        def task():
            try:
                response = requests.get(url, stream=True)
                response.raise_for_status()
                import tempfile

                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=os.path.splitext(sound["name"])[1]
                ) as tmp:
                    for chunk in response.iter_content(chunk_size=8192):
                        tmp.write(chunk)
                    self._temp_file = tmp.name
                if self.winfo_exists():
                    self.after(0, lambda: self._play_temp_file(index, btn_widget))
            except Exception as e:
                print(f"Preview error: {e}")
                if self.winfo_exists() and btn_widget and btn_widget.winfo_exists():
                    self.after(0, lambda: self._stop_dots(btn_widget))

        threading.Thread(target=task, daemon=True).start()

    def _start_dots(self, btn_widget):
        if not btn_widget or not btn_widget.winfo_exists():
            return
        self._stop_dots(btn_widget)
        btn_widget.config(text="▶ .", bg=self.colors["card_hover"])
        self._animate_dots(btn_widget, 1)

    def _animate_dots(self, btn_widget, count):
        if not btn_widget.winfo_exists():
            return
        count = count % 3 + 1
        btn_widget.config(text="▶ " + "." * count)
        self._dots_after_id = self.after(
            400, lambda: self._animate_dots(btn_widget, count)
        )

    def _stop_dots(self, btn_widget):
        if self._dots_after_id:
            try:
                self.after_cancel(self._dots_after_id)
            except:
                pass
            self._dots_after_id = None

    def _play_temp_file(self, index, btn_widget=None):
        try:
            pygame.mixer.music.load(self._temp_file)
            pygame.mixer.music.play()
            self._playing_index = index
            self._stop_dots(btn_widget)
            if btn_widget and btn_widget.winfo_exists():
                btn_widget.config(text="⏸ Pause", bg=self.colors["primary"])
            self._check_preview_end(btn_widget)
        except Exception as e:
            messagebox.showerror("Preview Error", f"Could not play preview: {e}")
            self._stop_dots(btn_widget)

    def _check_preview_end(self, btn_widget):
        try:
            if not pygame.mixer.music.get_busy() and self._playing_index != -1:
                if btn_widget and btn_widget.winfo_exists():
                    btn_widget.config(text="▶ Preview", bg=self.colors["primary"])
                self._playing_index = -1
            elif self._playing_index != -1:
                if self.winfo_exists():
                    self._preview_check_id = self.after(
                        250, lambda: self._check_preview_end(btn_widget)
                    )
        except:
            pass

    def _download_and_use(self, index):
        sound = self.sounds[index]
        target_path = os.path.join(self.sound_dir, sound["name"])

        if os.path.exists(target_path):
            if not messagebox.askyesno(
                "File Exists", f"'{sound['name']}' already exists. Overwrite?"
            ):
                self.on_select_callback(target_path)
                self.destroy()
                return

        def task():
            try:
                response = requests.get(sound["download_url"], stream=True)
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(target_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            ratio = downloaded / total_size
                            if self.winfo_exists():
                                self.after(
                                    0,
                                    lambda r=ratio, idx=index: (
                                        self._update_download_progress(idx, r)
                                    ),
                                )

                # CRASH FIX: Ensure BOTH this window AND the Settings window are still open
                if self.winfo_exists():
                    try:
                        if not self.master.winfo_exists():
                            self.destroy()
                            return
                    except:
                        self.destroy()
                        return
                    self.after(0, lambda: self._on_download_complete(target_path))
            except Exception as e:
                error_msg = str(e)
                if self.winfo_exists():
                    self.after(
                        0,
                        lambda: messagebox.showerror(
                            "Download Error", f"Failed to download: {error_msg}"
                        ),
                    )

        threading.Thread(target=task, daemon=True).start()

    def _update_download_progress(self, index, ratio):
        use_canvas = self.use_canvases.get(index)
        if not use_canvas or not use_canvas.winfo_exists():
            return
        use_canvas.delete("all")
        w, h = 85, 32
        fill_w = max(1, int(w * ratio))
        use_canvas.create_rectangle(0, 0, w, h, fill="#16a34a", outline="")
        use_canvas.create_rectangle(0, 0, fill_w, h, fill="#ffffff", outline="")
        percentage = int(ratio * 100)
        text_color = "#22c55e" if ratio > 0.4 else "white"
        use_canvas.create_text(
            w / 2,
            h / 2,
            text=f"{percentage}%",
            fill=text_color,
            font=("Segoe UI", 9, "bold"),
        )

    def _on_download_complete(self, path):
        if not self.winfo_exists():
            return
        # CRASH FIX: Did user close Settings while download was finishing?
        try:
            if not self.master.winfo_exists():
                self.destroy()
                return
        except:
            self.destroy()
            return

        messagebox.showinfo("Success", "Sound downloaded and selected!")

        if not self.winfo_exists():
            return
        try:
            if not self.master.winfo_exists():
                self.destroy()
                return
        except:
            self.destroy()
            return

        self.on_select_callback(path)
        if not self.winfo_exists():
            return
        self.destroy()

    def destroy(self):
        if self._dots_after_id:
            try:
                self.after_cancel(self._dots_after_id)
            except:
                pass
        if self._preview_check_id:
            try:
                self.after_cancel(self._preview_check_id)
            except:
                pass

        pygame.mixer.music.stop()
        if self._temp_file and os.path.exists(self._temp_file):
            try:
                os.remove(self._temp_file)
            except:
                pass

        # NO unbind_all here! It destroys scrolling in the rest of your app.
        super().destroy()


class SoundSelector(tk.Frame):
    """Custom dropdown with play/pause preview, progress bars, and browse for more."""

    def __init__(
        self,
        parent,
        bg="#1e2937",
        fg="#f1f5f9",
        accent="#67e8f9",
        text_muted="#94a3b8",
        item_bg="#1e2937",
        item_hover="#334155",
        font=("Segoe UI", 10),
        **kwargs,
    ):
        super().__init__(
            parent,
            bg=bg,
            highlightthickness=1,
            highlightbackground="#475569",
            **kwargs,
        )
        self.bg = bg
        self.fg = fg
        self.accent = accent
        self.text_muted = text_muted
        self.item_bg = item_bg
        self.item_hover = item_hover
        self.font = font

        self.sound_names = []
        self.sound_paths = []
        self.current_index = -1

        # Preview state
        self._playing_index = -1
        self._is_paused = False
        self._progress_after_id = None

        # Dropdown state
        self._dropdown = None
        self._dropdown_canvas = None
        self._dropdown_inner = None
        self._row_widgets = {}

        # External callbacks
        self._browse_callback = None
        self._online_browse_callback = None

        # Main display
        self.display_label = tk.Label(
            self,
            text="No sound selected",
            bg=self.bg,
            fg=self.fg,
            font=self.font,
            anchor="w",
        )
        self.display_label.pack(side="left", fill="x", expand=True, padx=10, pady=8)

        self.chevron = tk.Label(
            self, text="▼", bg=self.bg, fg=self.text_muted, font=("Segoe UI", 8)
        )
        self.chevron.pack(side="right", padx=(0, 8))

        self.bind("<Button-1>", self._toggle_dropdown)
        self.display_label.bind("<Button-1>", self._toggle_dropdown)
        self.chevron.bind("<Button-1>", self._toggle_dropdown)

    def load_sounds(self, sound_paths):
        if not self.winfo_exists():
            return  # <--- ADD THIS
        self.sound_paths = list(sound_paths)
        self.sound_names = []
        for p in self.sound_paths:
            name = os.path.splitext(os.path.basename(p))[0]
            self.sound_names.append(name if len(name) <= 40 else name[:37] + "...")
        if self.current_index < 0 and self.sound_names:
            self.current_index = 0
        self._update_display()

    def set_by_path(self, path):
        if not self.winfo_exists():
            return  # <--- ADD THIS
        if path in self.sound_paths:
            self.current_index = self.sound_paths.index(path)
        elif self.sound_paths:
            self.current_index = 0
        else:
            self.current_index = -1
        self._update_display()

    def get_path(self):
        if 0 <= self.current_index < len(self.sound_paths):
            return self.sound_paths[self.current_index]
        return ""

    def current(self):
        return self.current_index if self.current_index >= 0 else 0

    def config_state(self, state):
        if state == "disabled":
            self.config(highlightbackground="#1a1f2e")
            self.display_label.config(fg="#475569")
            self.chevron.config(fg="#475569")
            self.unbind("<Button-1>")
            self.display_label.unbind("<Button-1>")
            self.chevron.unbind("<Button-1>")
        else:
            self.config(highlightbackground="#475569")
            self.display_label.config(fg=self.fg)
            self.chevron.config(fg=self.text_muted)
            self.bind("<Button-1>", self._toggle_dropdown)
            self.display_label.bind("<Button-1>", self._toggle_dropdown)
            self.chevron.bind("<Button-1>", self._toggle_dropdown)

    def _update_display(self):
        # <--- ADD THIS ENTIRE SAFETY CHECK
        if not self.winfo_exists() or not self.display_label.winfo_exists():
            return
        if 0 <= self.current_index < len(self.sound_names):
            self.display_label.config(text=self.sound_names[self.current_index])
        else:
            self.display_label.config(text="No sound selected")

    def _toggle_dropdown(self, event=None):
        if self._dropdown and self._dropdown.winfo_exists():
            self._close_dropdown()
        else:
            self._open_dropdown()

    # ===================== Dropdown =====================
    def _open_dropdown(self):
        if not self.sound_names:
            return
        self._stop_preview()

        self._dropdown = tk.Toplevel(self)
        self._dropdown.wm_overrideredirect(True)
        self._dropdown.attributes("-topmost", True)
        try:
            self._dropdown.attributes("-alpha", 0.97)
        except Exception:
            pass

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 2
        self._dropdown.wm_geometry(f"+{x}+{y}")

        container = tk.Frame(
            self._dropdown,
            bg=self.bg,
            highlightthickness=1,
            highlightbackground="#475569",
        )
        container.pack()

        item_height = 36
        visible_items = min(5, len(self.sound_names))
        list_height = visible_items * item_height

        self.update_idletasks()
        dropdown_width = max(self.winfo_reqwidth(), 300)

        canvas = tk.Canvas(
            container,
            width=dropdown_width,
            height=list_height,
            bg=self.bg,
            highlightthickness=0,
            bd=0,
        )
        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=canvas.yview,
            bg="#475569",
            troughcolor=self.bg,
            activebackground="#94a3b8",
            width=12,
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        self._dropdown_canvas = canvas

        inner = tk.Frame(canvas, bg=self.bg)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        self._dropdown_inner = inner

        for i in range(len(self.sound_names)):
            self._build_row(inner, i)

        # "Browse for more" row
        if self._browse_callback:
            browse_row = tk.Frame(inner, bg=self.bg, height=34)
            browse_row.pack(fill="x")
            browse_row.pack_propagate(False)
            browse_btn = tk.Label(
                browse_row,
                text="📁  Browse Local...",
                bg=self.bg,
                fg="#22c55e",
                font=("Segoe UI", 10, "underline"),
                cursor="hand2",
            )
            browse_btn.pack(fill="x", padx=12, pady=4)
            browse_btn.bind("<Button-1>", lambda e: self._on_browse())

        # "Browse Online" row
        if self._online_browse_callback:
            online_row = tk.Frame(inner, bg=self.bg, height=34)
            online_row.pack(fill="x")
            online_row.pack_propagate(False)
            online_btn = tk.Label(
                online_row,
                text="🌐  Browse More Online...",
                bg=self.bg,
                fg=self.accent,
                font=("Segoe UI", 10, "underline"),
                cursor="hand2",
            )
            online_btn.pack(fill="x", padx=12, pady=4)
            online_btn.bind("<Button-1>", lambda e: self._on_online_browse())

        self._update_all_indicators()
        for idx in self._row_widgets:
            self._update_play_button(idx)

        inner.update_idletasks()
        try:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas.find_withtag("all")[0], width=dropdown_width)
        except Exception:
            pass

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 if event.delta > 0 else 1), "units")

        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)
        for child in inner.winfo_children():
            self._bind_wheel(child, on_mousewheel)

        self._dropdown.bind("<FocusOut>", lambda e: self._close_dropdown())
        self._dropdown.after(100, lambda: self._dropdown.focus_set())

    def _build_row(self, inner, index):
        """Build a sound row: [indicator] [name] [progress] [▶/⏸]."""
        name = self.sound_names[index]
        row = tk.Frame(inner, bg=self.item_bg, height=36)
        row.pack(fill="x")
        row.pack_propagate(False)

        is_selected = index == self.current_index
        is_playing = index == self._playing_index and not self._is_paused

        # Progress bar canvas (2px, at bottom of row)
        progress_canvas = tk.Canvas(
            row, bg=self.item_bg, highlightthickness=0, height=2
        )
        progress_canvas.pack(side="bottom", fill="x")

        # Name label
        name_label = tk.Label(
            row,
            text=name,
            bg=self.item_bg,
            fg=self.accent if is_selected else self.fg,
            font=self.font,
            anchor="w",
        )
        name_label.pack(side="left", fill="x", expand=True, padx=(10, 4), pady=(6, 4))

        # Play / Pause button
        play_text = "⏸" if is_playing else "▶"
        play_color = self.accent if is_playing else self.text_muted

        play_btn = tk.Label(
            row,
            text=play_text,
            bg=self.item_bg,
            fg=play_color,
            font=("Segoe UI", 10),
            cursor="hand2",
        )
        play_btn.pack(side="right", padx=(0, 10), pady=6)

        # Selected indicator
        indicator = None
        if is_selected:
            indicator = tk.Frame(row, bg=self.accent, width=3)
            indicator.place(anchor="nw", x=0, y=4, width=3, height=20)

        # Store references
        self._row_widgets[index] = {
            "row": row,
            "name_label": name_label,
            "play_btn": play_btn,
            "progress": progress_canvas,
            "indicator": indicator,
        }

        # --- Hover effects ---
        def on_enter(e, r=row, l=name_label, b=play_btn):
            if index != self.current_index:
                bg = self.item_hover
                r.config(bg=bg)
                l.config(bg=bg)
                b.config(bg=bg)

        def on_leave(e, r=row, l=name_label, b=play_btn):
            bg = self.item_bg
            r.config(bg=bg)
            l.config(bg=bg)
            b.config(bg=bg)

        def on_play_enter(e, b=play_btn):
            if index != self._playing_index:
                b.config(fg=self.accent)

        def on_play_leave(e, b=play_btn):
            if index != self._playing_index:
                b.config(fg=self.text_muted)

        # Select on name click
        for w in [row, name_label]:
            w.bind("<Button-1>", lambda e, idx=index: self._select(idx))
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

        # Play / Pause on button click
        play_btn.bind("<Button-1>", lambda e, idx=index: self._toggle_play(idx))
        play_btn.bind("<Enter>", on_play_enter)
        play_btn.bind("<Leave>", on_play_leave)

    # ===================== Play / Pause / Progress =====================
    def _toggle_play(self, index):
        """Toggle play/pause for a sound."""
        if self._playing_index == index:
            if self._is_paused:
                self._resume_preview(index)
            else:
                self._pause_preview(index)
        else:
            self._play_preview(index)

    def _play_preview(self, index):
        """Start playing a sound with fade-in, clearing any previous preview."""

        self._stop_preview()  # stops old sound, clears old progress

        self._playing_index = index
        self._is_paused = False

        if 0 <= index < len(self.sound_paths):
            path = self.sound_paths[index]
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(0.8)
                pygame.mixer.music.play(start=0.0, fade_ms=200)
                self._update_play_button(index)
                self.after(250, lambda: self._animate_progress(index))
            except Exception as e:
                print(f"[SoundSelector] Error playing {path}: {e}")
                self._playing_index = -1
                self._update_play_button(index)

    def _pause_preview(self, index):
        """Pause the currently playing sound."""
        self._is_paused = True
        self._cancel_progress_animation()
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
        except Exception:
            pass
        self._update_play_button(index)

    def _resume_preview(self, index):
        """Resume a paused sound."""
        self._is_paused = False
        try:
            pygame.mixer.music.unpause()
        except Exception:
            pass
        self._update_play_button(index)
        self._animate_progress(index)

    def _cancel_progress_animation(self):
        """Cancel any scheduled progress animation."""
        if self._progress_after_id:
            try:
                self.after_cancel(self._progress_after_id)
            except Exception:
                pass
            self._progress_after_id = None

    def _stop_preview(self):
        """Stop any playing/paused sound and clean up UI state."""
        self._cancel_progress_animation()

        old_index = self._playing_index
        self._playing_index = -1
        self._is_paused = False

        try:
            if pygame.mixer.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass

        if old_index >= 0 and old_index in self._row_widgets:
            self._update_play_button(old_index)
            self._clear_progress_bar(old_index)

    def _animate_progress(self, index):
        """Animate the progress bar for the currently playing sound."""
        if self._playing_index != index or self._is_paused:
            return

        widgets = self._row_widgets.get(index)
        if not widgets:
            return

        progress_canvas = widgets["progress"]
        if not progress_canvas.winfo_exists():
            return

        try:
            busy = pygame.mixer.music.get_busy()
            if not busy:
                self._on_playback_finished(index)
                return

            length = pygame.mixer.music.get_length()
            if length <= 0:
                self._on_playback_finished(index)
                return

            pos = pygame.mixer.music.get_pos()
            ratio = pos / length
            canvas_width = progress_canvas.winfo_width()
            if canvas_width > 1:
                bar_width = max(1, int(canvas_width * ratio))
                progress_canvas.delete("all")
                progress_canvas.create_rectangle(
                    0, 0, bar_width, 2, fill=self.accent, outline=""
                )

        except Exception:
            pass

        self._progress_after_id = self.after(60, lambda: self._animate_progress(index))

    def _on_playback_finished(self, index):
        """Called when music finishes playing naturally."""
        self._cancel_progress_animation()

        old_index = self._playing_index
        self._playing_index = -1
        self._is_paused = False

        try:
            if pygame.mixer.get_busy():
                pygame.mixer.music.stop()
        except Exception:
            pass

        if old_index >= 0 and old_index in self._row_widgets:
            self._update_play_button(old_index)
            self._clear_progress_bar(old_index)

        if self._dropdown and self._dropdown.winfo_exists():
            self._update_all_indicators()

    def _clear_progress_bar(self, index):
        """Clear the progress bar for a specific row."""
        widgets = self._row_widgets.get(index)
        if not widgets:
            return
        canvas = widgets["progress"]
        if canvas.winfo_exists():
            try:
                canvas.delete("all")
            except Exception:
                pass

    def _update_play_button(self, index):
        """Update a single play/pause button to reflect current state."""
        widgets = self._row_widgets.get(index)
        if not widgets:
            return
        btn = widgets["play_btn"]
        if not btn.winfo_exists():
            return

        if index == self._playing_index and not self._is_paused:
            btn.config(text="⏸", fg=self.accent)
        else:
            btn.config(text="▶", fg=self.text_muted)

    def _update_all_indicators(self):
        """Update the selected-item indicator for all rows."""
        if not self._dropdown or not self._dropdown.winfo_exists():
            return

        for idx, w in list(self._row_widgets.items()):
            if "indicator" in w:
                try:
                    w["indicator"].destroy()
                except Exception:
                    pass

        if 0 <= self.current_index < len(self.sound_names):
            w = self._row_widgets.get(self.current_index)
            if w and w["row"].winfo_exists():
                indicator = tk.Frame(w["row"], bg=self.accent, width=3)
                indicator.place(anchor="nw", x=0, y=4, width=3, height=20)
                w["indicator"] = indicator

    # ===================== Browse for More =====================
    def _on_browse(self):
        """Open file dialog to add a custom sound."""
        if not self._browse_callback:
            return

        path = filedialog.askopenfilename(
            title="Select Alarm Sound",
            filetypes=[("Audio Files", "*.mp3 *.wav *.ogg"), ("All Files", "*.*")],
        )
        if not path:
            return

        self._close_dropdown()
        self._browse_callback(path)

    def _on_online_browse(self):
        """Open the online sound browser."""
        if not self._online_browse_callback:
            return

        self._close_dropdown()
        self._online_browse_callback()

    def set_online_browse_callback(self, callback):
        self._online_browse_callback = callback

    def _select_internal(self, index):
        """Internal select logic used by _select."""
        self.current_index = index
        self._update_display()
        self._update_all_indicators()

        if self._dropdown:
            self.after(200, self._close_dropdown)

        if hasattr(self, "_on_change_callback") and self._on_change_callback:
            self._on_change_callback(self.get_path())

    def set_on_change(self, callback):
        self._on_change_callback = callback

    # ===================== Select & Close =====================
    def _select(self, index):
        """Select a sound and close dropdown."""
        if self._playing_index == index:
            self._stop_preview()
        self._select_internal(index)

    def _close_dropdown(self):
        """Close the dropdown, stopping any preview."""
        self._stop_preview()
        self._playing_index = -1
        self._is_paused = False
        self._row_widgets = {}
        if self._dropdown:
            try:
                self._dropdown.destroy()
            except Exception:
                pass
            self._dropdown = None
            self._dropdown_canvas = None
            self._dropdown_inner = None

    # ===================== Helpers =====================
    def _bind_wheel(self, widget, callback):
        widget.bind("<MouseWheel>", callback, add="+")
        widget.bind("<Button-4>", callback, add="+")
        widget.bind("<Button-5>", callback, add="+")
        for child in widget.winfo_children():
            self._bind_wheel(child, callback)

    def destroy(self):
        self._stop_preview()
        self._close_dropdown()
        super().destroy()


class ModernUI:
    def __init__(self, root, alarm_manager):
        self.root = root
        self.alarm_manager = alarm_manager
        settings = self.alarm_manager.settings

        self.hour_var = tk.StringVar(value="07")
        self.min_var = tk.StringVar(value="00")
        self.label_var = tk.StringVar(value="Morning Routine")
        self.repeat_vars = {
            d: tk.BooleanVar()
            for d in [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
        }
        self.volume_var = tk.IntVar(value=settings.get("default_volume", 80))
        self.fade_var = tk.BooleanVar(value=settings.get("default_fade_in", True))
        self.vibrate_var = tk.BooleanVar(value=False)
        self.sound_path = None
        self.use_tts_var = tk.BooleanVar(value=True)

        self._countdown_labels = {}
        self._edit_dialog = None
        self._settings_dialog = None

        self.setup_styles()
        self.build_ui()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        colors = {
            "bg": "#0f172a",
            "card": "#1e2937",
            "card_hover": "#334155",
            "text": "#f1f5f9",
            "text_muted": "#94a3b8",
            "accent": "#22c55e",
            "accent_hover": "#16a34a",
            "danger": "#ef4444",
            "danger_hover": "#dc2626",
            "primary": "#67e8f9",
            "scrollbar_bg": "#475569",
            "scrollbar_trough": "#0f172a",
            "scrollbar_active": "#94a3b8",
            "disabled_bg": "#1a1f2e",
            "disabled_fg": "#475569",
        }
        self.colors = colors

        style.configure(".", background=colors["bg"])
        style.configure("TFrame", background=colors["bg"])
        style.configure("TLabel", background=colors["bg"], foreground=colors["text"])
        style.configure(
            "TButton",
            background=colors["card"],
            foreground=colors["text"],
            borderwidth=0,
            padding=8,
        )
        style.map("TButton", background=[("active", colors["card_hover"])])
        style.configure(
            "Accent.TButton",
            background=colors["accent"],
            foreground="white",
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Accent.TButton", background=[("active", colors["accent_hover"])])
        style.configure(
            "Danger.TButton", background=colors["danger"], foreground="white"
        )

        style.configure(
            "Vertical.TScrollbar",
            background=colors["scrollbar_bg"],
            troughcolor=colors["scrollbar_trough"],
            borderwidth=0,
            thickness=16,
            arrowsize=0,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[
                ("active", colors["scrollbar_active"]),
                ("pressed", colors["card_hover"]),
            ],
            troughcolor=[
                ("active", colors["scrollbar_trough"]),
                ("pressed", colors["scrollbar_trough"]),
            ],
        )

        # Voice combobox styling
        style.configure(
            "Voice.TCombobox",
            fieldbackground=colors["card"],
            background=colors["card"],
            foreground=colors["text"],
            arrowcolor=colors["primary"],
            selectbackground=colors["primary"],
            selectforeground=colors["bg"],
            borderwidth=0,
        )
        style.map(
            "Voice.TCombobox",
            fieldbackground=[("readonly", colors["card"])],
            foreground=[("readonly", colors["text"])],
            selectbackground=[("focus", colors["primary"])],
            selectforeground=[("focus", colors["bg"])],
        )

    def _create_visible_scrollbar(self, parent, orient="vertical", command=None):
        c = self.colors
        sb = tk.Scrollbar(
            parent,
            orient=orient,
            command=command,
            bg=c["scrollbar_bg"],
            troughcolor=c["scrollbar_trough"],
            activebackground=c["scrollbar_active"],
            width=16,
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            elementborderwidth=0,
            bd=0,
        )
        return sb

    def _bind_mousewheel_recursive(self, widget, callback):
        widget.bind("<MouseWheel>", callback, add="+")
        widget.bind("<Button-4>", callback, add="+")
        widget.bind("<Button-5>", callback, add="+")
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child, callback)

    def center_window(self, window, width, height):
        window.update_idletasks()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def build_ui(self):
        self.root.title("DawnGuard")
        # Increase height slightly to 720 to ensure everything fits comfortably
        self.center_window(self.root, 420, 720)
        self.root.configure(bg=self.colors["bg"])
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.alarm_manager.hide_to_tray)

        self.main_container = tk.Frame(self.root, bg=self.colors["bg"])
        self.main_container.pack(fill="both", expand=True, padx=12, pady=12)

        self.create_header()
        self.create_clock()
        self.create_tabs()

    def create_header(self):
        header = tk.Frame(self.main_container, bg=self.colors["bg"])
        header.pack(fill="x", pady=(0, 8))
        self.header_frame = header

        # Brand Image and Label
        brand_frame = tk.Frame(header, bg=self.colors["bg"])
        brand_frame.pack(side="left")

        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        img_path = os.path.join(assets_dir, "DawnGuardImg.png")
        if os.path.exists(img_path):
            try:
                from PIL import Image, ImageTk

                pil_img = Image.open(img_path).resize((32, 32), Image.LANCZOS)
                self.brand_photo = ImageTk.PhotoImage(pil_img)
                tk.Label(brand_frame, image=self.brand_photo, bg=self.colors["bg"]).pack(
                    side="left", padx=(0, 8)
                )
            except Exception:
                pass

        title_frame = tk.Frame(brand_frame, bg=self.colors["bg"])
        title_frame.pack(side="left")

        tk.Label(
            title_frame,
            text="DawnGuard",
            font=("Segoe UI", 18, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["primary"],
        ).pack(side="top", anchor="w")

        from config import APP_VERSION
        tk.Label(
            title_frame,
            text=f"v{APP_VERSION}",
            font=("Segoe UI", 8),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(side="top", anchor="w", pady=(0, 0))

        settings_btn = tk.Label(
            header,
            text="⚙",
            font=("Segoe UI", 20),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
            cursor="hand2",
        )
        settings_btn.pack(side="right", padx=(0, 4))
        settings_btn.bind("<Button-1>", lambda e: self.open_settings_dialog())
        ToolTip(settings_btn, "Settings")

        self.header_name_label = tk.Label(
            header,
            text="",
            font=("Segoe UI", 11),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        )
        self.header_name_label.pack(side="right")
        self._update_header_name()

    def _update_header_name(self):
        tts_enabled = self.alarm_manager.settings.get("tts_enabled", True)
        name = self.alarm_manager.settings.get("user_name", "").strip()
        if name and tts_enabled:
            self.header_name_label.config(text=name)
        else:
            self.header_name_label.config(text="")

    def create_clock(self):
        clock_frame = tk.Frame(self.main_container, bg=self.colors["bg"])
        clock_frame.pack(fill="x", pady=(0, 8))

        self.time_var = tk.StringVar()
        tk.Label(
            clock_frame,
            textvariable=self.time_var,
            font=("Segoe UI", 36, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text"],
        ).pack()

        self.date_var = tk.StringVar()
        tk.Label(
            clock_frame,
            textvariable=self.date_var,
            font=("Segoe UI", 10),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack()

        # This kicks off the timer loop
        self.update_clock()

    def update_clock(self):
        if not hasattr(self, "root") or not self.root.winfo_exists():
            return
        try:
            now = datetime.now()
            # 12H / 24H FORMAT TOGGLE
            if self.alarm_manager.settings.get("use_24h_format", True):
                self.time_var.set(now.strftime("%H:%M:%S"))
            else:
                self.time_var.set(now.strftime("%I:%M:%S %p"))

            self.date_var.set(now.strftime("%A, %B %d").upper())
            self.update_countdowns()
        except Exception:
            pass
        self.root.after(200, self.update_clock)

    def update_clock(self):
        if not hasattr(self, "root") or not self.root.winfo_exists():
            return
        try:
            now = datetime.now()
            # 12H / 24H FORMAT TOGGLE
            if self.alarm_manager.settings.get("use_24h_format", True):
                self.time_var.set(now.strftime("%H:%M:%S"))
            else:
                self.time_var.set(now.strftime("%I:%M:%S %p"))

            self.date_var.set(now.strftime("%A, %B %d").upper())
            self.update_countdowns()
        except Exception:
            pass
        self.root.after(200, self.update_clock)

    def create_tabs(self):
        self.notebook = ttk.Notebook(self.main_container)
        self.notebook.pack(fill="both", expand=True)

        self.view_tab = tk.Frame(self.notebook, bg=self.colors["bg"])
        self.add_tab = tk.Frame(self.notebook, bg=self.colors["bg"])

        self.notebook.add(self.view_tab, text="  Alarms  ")
        self.notebook.add(self.add_tab, text="  New Alarm  ")

        self.create_alarm_list()
        self.create_add_form()

    # ===================== Icons =====================
    def draw_edit_icon(self, canvas, color):
        canvas.delete("all")
        canvas.create_polygon(4, 14, 14, 4, 16, 6, 6, 16, fill=color, outline=color)
        canvas.create_polygon(2, 18, 4, 14, 6, 16, fill=color, outline=color)
        canvas.create_rectangle(14, 4, 18, 8, fill=color, outline=color)

    def draw_delete_icon(self, canvas, color):
        canvas.delete("all")
        canvas.create_rectangle(5, 7, 15, 17, outline=color, width=2)
        canvas.create_line(3, 5, 17, 5, fill=color, width=2)
        canvas.create_rectangle(8, 3, 12, 5, outline=color, width=1)
        canvas.create_line(8, 9, 8, 15, fill=color)
        canvas.create_line(12, 9, 12, 15, fill=color)

    def draw_toggle_icon(self, canvas, enabled):
        canvas.delete("all")
        if enabled:
            canvas.create_rectangle(
                2,
                6,
                28,
                18,
                fill=self.colors["accent"],
                outline=self.colors["accent"],
                width=0,
            )
            canvas.create_oval(16, 4, 30, 20, fill="white", outline="white")
        else:
            canvas.create_rectangle(
                2,
                6,
                28,
                18,
                fill=self.colors["card_hover"],
                outline=self.colors["text_muted"],
                width=1,
            )
            canvas.create_oval(
                0,
                4,
                14,
                20,
                fill=self.colors["text_muted"],
                outline=self.colors["text_muted"],
            )

    # ===================== Alarm List =====================
    def create_alarm_list(self):
        list_frame = tk.Frame(self.view_tab, bg=self.colors["bg"])
        list_frame.pack(fill="both", expand=True, padx=4, pady=4)

        header = tk.Frame(list_frame, bg=self.colors["bg"])
        header.pack(fill="x", pady=(0, 8))
        tk.Label(
            header,
            text="Your Alarms",
            font=("Segoe UI", 12, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text"],
        ).pack(side="left")

        self.alarm_count_label = tk.Label(
            header,
            text="",
            font=("Segoe UI", 9),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        )
        self.alarm_count_label.pack(side="right")

        outer = tk.Frame(list_frame, bg=self.colors["scrollbar_bg"], bd=0)
        outer.pack(fill="both", expand=True)

        trough_strip = tk.Frame(outer, bg=self.colors["scrollbar_trough"], width=16)
        trough_strip.pack(side="right", fill="y")
        trough_strip.pack_propagate(False)

        self.alarm_canvas = tk.Canvas(
            outer, bg=self.colors["card"], highlightthickness=0, bd=0, relief="flat"
        )
        self.alarm_canvas.pack(side="left", fill="both", expand=True)

        scrollbar = self._create_visible_scrollbar(
            trough_strip, orient="vertical", command=self.alarm_canvas.yview
        )
        scrollbar.pack(side="right", fill="y", expand=True)
        self.alarm_canvas.configure(yscrollcommand=scrollbar.set)

        self.inner_frame = tk.Frame(self.alarm_canvas, bg=self.colors["card"])
        self.inner_id = self.alarm_canvas.create_window(
            (0, 0), window=self.inner_frame, anchor="nw"
        )

        self.inner_frame.bind(
            "<Configure>",
            lambda e: self.alarm_canvas.configure(
                scrollregion=self.alarm_canvas.bbox("all")
            ),
        )
        self.alarm_canvas.bind(
            "<Configure>",
            lambda e: self.alarm_canvas.itemconfig(self.inner_id, width=e.width),
        )

        def on_mousewheel_alarms(event):
            self.alarm_canvas.yview_scroll(int(-1 if event.delta > 0 else 1), "units")

        self.alarm_canvas.bind("<MouseWheel>", on_mousewheel_alarms)
        self.alarm_canvas.bind("<Button-4>", on_mousewheel_alarms)
        self.alarm_canvas.bind("<Button-5>", on_mousewheel_alarms)

        self.refresh_alarm_cards()

    def refresh_alarm_cards(self):
        for widget in self.inner_frame.winfo_children():
            widget.destroy()

        self._countdown_labels = {}
        alarms = list(self.alarm_manager.alarms)
        count = len(alarms)
        self.alarm_count_label.config(text=f"{count} alarm{'s' if count != 1 else ''}")

        if not alarms:
            empty_frame = tk.Frame(self.inner_frame, bg=self.colors["card"])
            empty_frame.pack(expand=True, fill="both", pady=100)

            # Try to load the brand image for the empty state
            assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
            img_path = os.path.join(assets_dir, "DawnGuardImg.png")
            if os.path.exists(img_path):
                try:
                    from PIL import Image, ImageTk
                    pil_img = Image.open(img_path).resize((80, 80), Image.LANCZOS)
                    # Need to keep a reference to avoid garbage collection
                    self.empty_photo = ImageTk.PhotoImage(pil_img)
                    tk.Label(empty_frame, image=self.empty_photo, bg=self.colors["card"]).pack()
                except:
                    pass

            tk.Label(
                empty_frame,
                text="No alarms set yet",
                font=("Segoe UI", 16, "bold"),
                bg=self.colors["card"],
                fg=self.colors["text"],
            ).pack(pady=(15, 5))
            
            tk.Label(
                empty_frame,
                text="Tap 'New Alarm' to start your morning",
                font=("Segoe UI", 10),
                bg=self.colors["card"],
                fg=self.colors["text_muted"],
            ).pack()

            self.inner_frame.update_idletasks()
            self.alarm_canvas.configure(scrollregion=self.alarm_canvas.bbox("all"))
            return

        def _sort_key(a):
            try:
                next_t = a.next_trigger()
            except Exception:
                next_t = datetime.max
            return (next_t, -getattr(a, "id", 0))

        alarms.sort(key=_sort_key)

        for alarm in alarms:
            self.create_alarm_card(alarm)

        # Spacer so last card doesn't stick to the bottom edge

        tk.Frame(self.inner_frame, bg=self.colors["card"], height=150).pack()
        self.inner_frame.update_idletasks()
        self.alarm_canvas.configure(scrollregion=self.alarm_canvas.bbox("all"))

        def on_mousewheel_alarms(event):
            self.alarm_canvas.yview_scroll(int(-1 if event.delta > 0 else 1), "units")

        self._bind_mousewheel_recursive(self.inner_frame, on_mousewheel_alarms)

    def format_repeat_text(self, repeat):
        days_full = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        if not repeat:
            return "Once"
        repeat_norm = [str(d).strip() for d in (repeat or []) if str(d).strip()]
        if not repeat_norm:
            return "Once"
        repeat_set = set(repeat_norm)
        if set(days_full).issubset(repeat_set):
            return "Every day"
        weekdays = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
        weekends = {"Saturday", "Sunday"}
        if weekdays.issubset(repeat_set) and not weekends.intersection(repeat_set):
            return "Weekdays"
        if weekends.issubset(repeat_set) and not weekdays.intersection(repeat_set):
            return "Weekends"
        return ", ".join([d[:3].title() for d in repeat_norm])

    def format_label_text(self, label, max_chars=32):
        text = (label or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"

    def create_alarm_card(self, alarm):
        card = tk.Frame(
            self.inner_frame, bg=self.colors["card"], bd=0, highlightthickness=0
        )
        card.pack(fill="x", pady=6, padx=8)

        def on_enter(e):
            card.config(bg=self.colors["card_hover"])

        def on_leave(e):
            card.config(bg=self.colors["card"])

        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

        left = tk.Frame(card, bg=self.colors["card"])
        left.pack(side="left", fill="both", expand=True, padx=12, pady=12)
        left.bind("<Enter>", on_enter)
        left.bind("<Leave>", on_leave)

        tk.Label(
            left,
            text=alarm.time,
            font=("Segoe UI", 26, "bold"),
            bg=self.colors["card"],
            fg=self.colors["primary"],
        ).pack(anchor="w")

        countdown = tk.Label(
            left,
            text="",
            font=("Segoe UI", 9),
            bg=self.colors["card"],
            fg=self.colors["accent"],
        )
        countdown.pack(anchor="w", pady=(2, 0))
        self._countdown_labels[getattr(alarm, "id", id(alarm))] = countdown

        label_text = self.format_label_text(getattr(alarm, "label", ""), max_chars=30)
        tk.Label(
            left,
            text=label_text,
            font=("Segoe UI", 11),
            bg=self.colors["card"],
            fg=self.colors["text"],
            wraplength=220,
            justify="left",
        ).pack(anchor="w", pady=2)

        repeat_text = self.format_repeat_text(getattr(alarm, "repeat", []))
        tk.Label(
            left,
            text=repeat_text,
            font=("Segoe UI", 9),
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            wraplength=220,
            justify="left",
        ).pack(anchor="w")

        right = tk.Frame(card, bg=self.colors["card"])
        right.pack(side="right", padx=12, pady=12)
        right.bind("<Enter>", on_enter)
        right.bind("<Leave>", on_leave)

        toggle_canvas = tk.Canvas(
            right,
            width=32,
            height=24,
            bg=self.colors["card"],
            highlightthickness=0,
            cursor="hand2",
        )
        toggle_canvas.pack(pady=(0, 12))
        self.draw_toggle_icon(toggle_canvas, getattr(alarm, "enabled", True))
        toggle_canvas.bind("<Button-1>", lambda e, a=alarm: self.toggle_alarm(a))
        ToolTip(toggle_canvas, "Enable / Disable alarm")

        btns = tk.Frame(right, bg=self.colors["card"])
        btns.pack()

        edit_btn = tk.Frame(
            btns, bg=self.colors["card_hover"], padx=6, pady=6, cursor="hand2"
        )
        edit_btn.pack(side="left", padx=4)
        edit_icon = tk.Canvas(
            edit_btn,
            width=20,
            height=20,
            bg=self.colors["card_hover"],
            highlightthickness=0,
        )
        edit_icon.pack()
        self.draw_edit_icon(edit_icon, self.colors["text"])
        edit_btn.bind("<Button-1>", lambda e, a=alarm: self.open_edit_dialog(a))
        edit_icon.bind("<Button-1>", lambda e, a=alarm: self.open_edit_dialog(a))
        ToolTip(edit_btn, "Edit alarm")
        ToolTip(edit_icon, "Edit alarm")

        del_btn = tk.Frame(
            btns, bg=self.colors["danger"], padx=6, pady=6, cursor="hand2"
        )
        del_btn.pack(side="left", padx=4)
        del_icon = tk.Canvas(
            del_btn, width=20, height=20, bg=self.colors["danger"], highlightthickness=0
        )
        del_icon.pack()
        self.draw_delete_icon(del_icon, "white")
        del_btn.bind("<Button-1>", lambda e, a=alarm: self.delete_alarm_with_confirm(a))
        del_icon.bind(
            "<Button-1>", lambda e, a=alarm: self.delete_alarm_with_confirm(a)
        )
        ToolTip(del_btn, "Delete alarm")
        ToolTip(del_icon, "Delete alarm")

        self.update_countdowns()

    def format_time_remaining(self, delta_seconds):
        if delta_seconds < 0:
            delta_seconds = 0
        hours = int(delta_seconds // 3600)
        minutes = int((delta_seconds % 3600) // 60)
        seconds = int(delta_seconds % 60)
        if hours > 0:
            return f"Rings in {hours}h {minutes}m"
        if minutes > 0:
            return f"Rings in {minutes}m {seconds}s"
        return f"Rings in {seconds}s"

    def update_countdowns(self):
        if not hasattr(self, "_countdown_labels"):
            return
        now = datetime.now()
        for alarm in getattr(self.alarm_manager, "alarms", []):
            key = getattr(alarm, "id", id(alarm))
            lbl = self._countdown_labels.get(key)
            if not lbl:
                continue
            try:
                if not lbl.winfo_exists():
                    continue
                if not getattr(alarm, "enabled", True):
                    lbl.config(text="Disabled", fg=self.colors["text_muted"])
                    continue
                next_t = alarm.next_trigger()
                remaining = (next_t - now).total_seconds()

                # Determine color and blinking
                color = self.colors["accent"]
                if remaining < 30:
                    color = "#fb923c"  # Orange (Tailwind orange-400)

                # Handle blinking for < 10 seconds
                is_visible = True
                if remaining < 10 and remaining > 0:
                    # Blink every 500ms (0.5s)
                    if int(now.timestamp() * 2) % 2 == 0:
                        is_visible = False

                if is_visible:
                    lbl.config(text=self.format_time_remaining(remaining), fg=color)
                else:
                    lbl.config(text="")  # Empty text for blinking effect

            except Exception:
                try:
                    lbl.config(text="", fg=self.colors["text_muted"])
                except Exception:
                    pass

    def toggle_alarm(self, alarm):
        alarm.enabled = not getattr(alarm, "enabled", True)
        from alarm import save_alarms

        save_alarms(self.alarm_manager.alarms)
        self.refresh_alarm_cards()

    def delete_alarm_with_confirm(self, alarm):
        if messagebox.askyesno("Delete Alarm", f"Delete '{alarm.label}'?"):
            self.alarm_manager.delete_alarm(alarm)
            self.refresh_alarm_cards()

    # ===================== Add New Alarm Form =====================
    def create_add_form(self):
        outer = tk.Frame(self.add_tab, bg=self.colors["scrollbar_trough"], bd=0)
        outer.pack(side="left", fill="both", expand=True)

        trough_strip = tk.Frame(outer, bg=self.colors["scrollbar_trough"], width=16)
        trough_strip.pack(side="right", fill="y")
        trough_strip.pack_propagate(False)

        canvas = tk.Canvas(outer, bg=self.colors["bg"], highlightthickness=0, bd=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = self._create_visible_scrollbar(
            trough_strip, orient="vertical", command=canvas.yview
        )
        scrollbar.pack(side="right", fill="y", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)

        container = tk.Frame(canvas, bg=self.colors["bg"])
        canvas.create_window((0, 0), window=container, anchor="nw")

        container.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(canvas.find_withtag("all")[0], width=e.width),
        )

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 if event.delta > 0 else 1), "units")

        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)

        container.bind(
            "<Map>", lambda e: self._bind_mousewheel_recursive(container, on_mousewheel)
        )

        self.create_time_section(container)
        self.create_label_section(container)
        self.create_repeat_section(container)
        self.create_volume_section(container)
        self.create_options_section(container)
        self.create_alarm_type_section(container, self.use_tts_var)
        self.create_sound_section(container, tts_var=self.use_tts_var)

        tk.Button(
            container,
            text="ADD ALARM",
            font=("Segoe UI", 12, "bold"),
            bg=self.colors["accent"],
            fg="white",
            bd=0,
            cursor="hand2",
            command=self.add_alarm,
        ).pack(fill="x", pady=(30, 60), padx=30, ipady=10)

    def _setup_time_validation(self, hour_sb, min_sb, hour_var, min_var, max_hour=23):
        def validate_input(P, max_val):
            if P == "":
                return True
            if not P.isdigit():
                return False
            if len(P) > 2:
                return False
            val = int(P)
            return val <= max_val

        v_hour = self.root.register(lambda P: validate_input(P, max_hour))
        v_min = self.root.register(lambda P: validate_input(P, 59))

        hour_sb.config(validate="key", validatecommand=(v_hour, "%P"))
        min_sb.config(validate="key", validatecommand=(v_min, "%P"))

        def on_hour_write(*args):
            val = hour_var.get()
            if len(val) == 2:
                min_sb.focus_set()
                min_sb.selection_range(0, "end")

        def on_min_write(*args):
            val = min_var.get()
            if len(val) > 2:
                min_var.set(val[:2])

        hour_var.trace_add("write", on_hour_write)
        min_var.trace_add("write", on_min_write)

    def create_time_section(self, parent):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=15, padx=20)
        tk.Label(
            frame,
            text="ALARM TIME",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")

        tframe = tk.Frame(frame, bg=self.colors["card"], padx=20, pady=15)
        tframe.pack(fill="x", pady=8)

        def create_styled_spinbox(parent, var, from_, to):
            sb = tk.Spinbox(
                parent,
                from_=from_,
                to=to,
                textvariable=var,
                width=3,
                font=("Segoe UI", 32, "bold"),
                bg=self.colors["card"],
                fg=self.colors["primary"],
                buttonbackground=self.colors["card"],
                bd=0,
                highlightthickness=0,
                justify="center",
                format="%02.0f",
            )
            return sb

        inner_t = tk.Frame(tframe, bg=self.colors["card"])
        inner_t.pack(expand=True)

        h_sb = create_styled_spinbox(inner_t, self.hour_var, 0, 23)
        h_sb.pack(side="left")
        tk.Label(
            inner_t,
            text=":",
            font=("Segoe UI", 32, "bold"),
            bg=self.colors["card"],
            fg=self.colors["text"],
        ).pack(side="left", padx=10)
        m_sb = create_styled_spinbox(inner_t, self.min_var, 0, 59)
        m_sb.pack(side="left")

        self._setup_time_validation(h_sb, m_sb, self.hour_var, self.min_var)

    def create_label_section(self, parent):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=10, padx=20)
        tk.Label(
            frame,
            text="LABEL",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")

        eframe = tk.Frame(frame, bg=self.colors["card"], padx=15, pady=10)
        eframe.pack(fill="x", pady=8)
        tk.Entry(
            eframe,
            textvariable=self.label_var,
            font=("Segoe UI", 12),
            bg=self.colors["card"],
            fg=self.colors["text"],
            bd=0,
            insertbackground="white",
        ).pack(fill="x")
        tk.Frame(eframe, height=1, bg=self.colors["primary"]).pack(
            fill="x", pady=(5, 0)
        )

    def create_repeat_section(self, parent):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=10, padx=20)
        tk.Label(
            frame,
            text="REPEAT",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")

        dframe = tk.Frame(frame, bg=self.colors["bg"])
        dframe.pack(fill="x", pady=10)

        for short, full in [
            ("M", "Monday"),
            ("T", "Tuesday"),
            ("W", "Wednesday"),
            ("T", "Thursday"),
            ("F", "Friday"),
            ("S", "Saturday"),
            ("S", "Sunday"),
        ]:
            self.create_day_chip(dframe, short, full, self.repeat_vars[full]).pack(
                side="left", expand=True
            )

    def create_day_chip(self, parent, text, full_name, var):
        chip = tk.Canvas(
            parent,
            width=36,
            height=36,
            bg=self.colors["bg"],
            highlightthickness=0,
            cursor="hand2",
        )

        def update_chip(v):
            chip.delete("all")
            color = self.colors["primary"] if v else self.colors["card"]
            text_color = self.colors["bg"] if v else self.colors["text"]
            chip.create_oval(2, 2, 34, 34, fill=color, outline=color)
            chip.create_text(
                18, 18, text=text, fill=text_color, font=("Segoe UI", 10, "bold")
            )

        def toggle(e):
            var.set(not var.get())
            update_chip(var.get())

        chip.bind("<Button-1>", toggle)
        update_chip(var.get())
        return chip

    def create_volume_section(self, parent):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=10, padx=20)
        tk.Label(
            frame,
            text="VOLUME",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")

        vframe = tk.Frame(frame, bg=self.colors["card"], padx=20, pady=15)
        vframe.pack(fill="x", pady=8)

        tk.Scale(
            vframe,
            from_=0,
            to=100,
            variable=self.volume_var,
            orient="horizontal",
            bg=self.colors["card"],
            fg=self.colors["primary"],
            highlightthickness=0,
            troughcolor=self.colors["bg"],
            activebackground=self.colors["primary"],
            showvalue=False,
        ).pack(fill="x")

    def create_options_section(self, parent):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=10, padx=20)
        tk.Label(
            frame,
            text="OPTIONS",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")

        inner = tk.Frame(frame, bg=self.colors["card"], padx=15, pady=10)
        inner.pack(fill="x", pady=8)

        self.create_option_row(inner, "Gradual wake (fade in)", self.fade_var).pack(
            fill="x", pady=5
        )
        self.create_option_row(inner, "Vibrate", self.vibrate_var).pack(
            fill="x", pady=5
        )

    def create_option_row(self, parent, text, var):
        row = tk.Frame(parent, bg=self.colors["card"])
        tk.Label(
            row,
            text=text,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 11),
        ).pack(side="left")

        toggle = tk.Canvas(
            row,
            width=32,
            height=24,
            bg=self.colors["card"],
            highlightthickness=0,
            cursor="hand2",
        )
        toggle.pack(side="right")

        def update_toggle():
            self.draw_toggle_icon(toggle, var.get())

        def on_click(e):
            var.set(not var.get())
            update_toggle()

        toggle.bind("<Button-1>", on_click)
        update_toggle()
        return row

    def create_alarm_type_section(self, parent, tts_var):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=10, padx=20)
        tk.Label(
            frame,
            text="ALERT TYPE",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")

        inner = tk.Frame(frame, bg=self.colors["card"], padx=15, pady=10)
        inner.pack(fill="x", pady=8)
        self.create_option_row(inner, "Voice alert (TTS)", tts_var).pack(fill="x")

    def create_sound_section(self, parent, tts_var=None):
        default_sound = self.alarm_manager.settings.get("default_sound", "")
        display_name = (
            os.path.basename(default_sound) if default_sound else "Default Alarm"
        )

        wrapper = tk.Frame(parent, bg=self.colors["bg"])
        wrapper.pack(fill="x", pady=10, padx=20)

        inner = tk.Frame(wrapper, bg=self.colors["bg"])

        def toggle_visibility(*args):
            if tts_var and tts_var.get():
                inner.pack_forget()
            else:
                inner.pack(fill="x")

        inner.pack(fill="x")

        if tts_var:
            toggle_visibility()
            tts_var.trace_add("write", toggle_visibility)

        # Pre-load default sound from settings
        if not self.sound_path:
            self.sound_path = self.alarm_manager.settings.get("default_sound", "")

        frame = tk.Frame(inner, bg=self.colors["bg"])
        frame.pack(fill="x")
        tk.Label(
            frame,
            text="SOUND",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")

        sframe = tk.Frame(frame, bg=self.colors["card"], padx=15, pady=10)
        sframe.pack(fill="x", pady=8)

        self.sound_label = tk.Label(
            sframe,
            text=display_name,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 11),
        )
        self.sound_label.pack(side="left")

        tk.Button(
            sframe,
            text="Browse",
            bg=self.colors["primary"],
            fg=self.colors["bg"],
            font=("Segoe UI", 9, "bold"),
            bd=0,
            padx=10,
            cursor="hand2",
            command=self.browse_sound,
        ).pack(side="right")

    def browse_sound(self):
        path = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.ogg")])
        if path:
            self.sound_path = path
            self.sound_label.config(text=os.path.basename(path))

    def add_alarm(self):
        try:
            hour = int(self.hour_var.get())
            minute = int(self.min_var.get())
            time_str = f"{hour:02d}:{minute:02d}"
        except ValueError:
            messagebox.showerror("Invalid Time", "Please enter valid numbers")
            return
        repeat = [d for d, v in self.repeat_vars.items() if v.get()]
        label = self.label_var.get().strip() or "Alarm"
        self.alarm_manager.add_alarm(
            time=time_str,
            label=label,
            repeat=repeat,
            fade_in=self.fade_var.get(),
            volume=self.volume_var.get(),
            vibrate=self.vibrate_var.get(),
            sound=self.sound_path,
            use_tts=self.use_tts_var.get(),
        )
        self.refresh_alarm_cards()
        self.notebook.select(0)

    # ===================== Settings Dialog =====================
    # ===================== Settings Dialog =====================
    def open_settings_dialog(self):
        if self._settings_dialog and self._settings_dialog.winfo_exists():
            self._settings_dialog.lift()
            self._settings_dialog.focus_force()
            return

        dialog = tk.Toplevel(self.root)
        self._settings_dialog = dialog
        dialog.title("⚙ Settings")

        # Set Window Icon
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        ico_path = os.path.join(assets_dir, "DawnGuardIco.ico")
        if os.path.exists(ico_path):
            try:
                dialog.iconbitmap(ico_path)
            except Exception:
                pass

        self.center_window(dialog, 420, 720)
        dialog.configure(bg=self.colors["bg"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        try:
            dialog.grab_set()
        except Exception:
            pass

        s = self.alarm_manager.settings

        outer = tk.Frame(dialog, bg=self.colors["scrollbar_trough"], bd=0)
        outer.pack(side="left", fill="both", expand=True)

        trough_strip = tk.Frame(outer, bg=self.colors["scrollbar_trough"], width=16)
        trough_strip.pack(side="right", fill="y")
        trough_strip.pack_propagate(False)

        canvas = tk.Canvas(outer, bg=self.colors["bg"], highlightthickness=0, bd=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = self._create_visible_scrollbar(
            trough_strip, orient="vertical", command=canvas.yview
        )
        scrollbar.pack(side="right", fill="y", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)

        container = tk.Frame(canvas, bg=self.colors["bg"])
        canvas.create_window((0, 0), window=container, anchor="nw")
        container.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(canvas.find_withtag("all")[0], width=e.width),
        )

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 if event.delta > 0 else 1), "units")

        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)
        container.bind(
            "<Map>", lambda e: self._bind_mousewheel_recursive(container, on_mousewheel)
        )

        # ---- PERSONALIZATION ----
        self._settings_section_label(container, "PERSONALIZATION")

        name_frame = tk.Frame(container, bg=self.colors["card"], padx=15, pady=12)
        name_frame.pack(fill="x", padx=20, pady=(0, 12))
        tk.Label(
            name_frame,
            text="Your Name",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            name_frame,
            text='Used in voice alerts: "Attention, Douglas..."',
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 6))
        settings_name_var = tk.StringVar(value=s.get("user_name", ""))
        name_entry = tk.Entry(
            name_frame,
            textvariable=settings_name_var,
            font=("Segoe UI", 12),
            bg=self.colors["bg"],
            fg=self.colors["text"],
            bd=0,
            insertbackground="white",
        )
        name_entry.pack(fill="x", ipady=4)
        tk.Frame(name_frame, height=1, bg=self.colors["primary"]).pack(
            fill="x", pady=(4, 0)
        )

        # ---- DEFAULT ALARM SOUND (created early so VOICE section can reference it) ----
        self._settings_section_label(container, "DEFAULT ALARM SOUND")

        sound_frame = tk.Frame(container, bg=self.colors["card"], padx=15, pady=12)
        sound_frame.pack(fill="x", padx=20, pady=(0, 12))
        tk.Label(
            sound_frame,
            text="Used when 'Voice alert' is off  •  ▶ to preview",
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 6))

        sounds_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "AlarmSounds"
        )
        found_paths = []
        if os.path.isdir(sounds_dir):
            for f in sorted(os.listdir(sounds_dir)):
                if f.lower().endswith((".mp3", ".wav", ".ogg")):
                    found_paths.append(os.path.join(sounds_dir, f))

        saved_sound = s.get("default_sound", "")

        sound_selector = SoundSelector(
            sound_frame,
            bg=self.colors["card"],
            fg=self.colors["text"],
            accent=self.colors["primary"],
            text_muted=self.colors["text_muted"],
            item_bg=self.colors["card"],
            item_hover=self.colors["card_hover"],
            font=("Segoe UI", 10),
        )
        sound_selector.pack(fill="x", pady=(0, 4))

        def on_sound_change(new_path):
            self.alarm_manager.settings["default_sound"] = new_path
            from config import save_settings

            save_settings(self.alarm_manager.settings)

        def open_online_browser():
            def on_online_selected(path):
                new_found = []
                if os.path.isdir(sounds_dir):
                    for f in sorted(os.listdir(sounds_dir)):
                        if f.lower().endswith((".mp3", ".wav", ".ogg")):
                            new_found.append(os.path.join(sounds_dir, f))

                sound_selector.load_sounds(new_found)
                sound_selector.set_by_path(path)
                on_sound_change(path)

            # CHANGE self.root TO dialog HERE:
            OnlineSoundBrowser(dialog, self.colors, sounds_dir, on_online_selected)

        sound_selector._browse_callback = lambda p: (
            sound_selector.load_sounds(found_paths + [p]),
            sound_selector.set_by_path(p),
            on_sound_change(p),
        )
        sound_selector.set_online_browse_callback(open_online_browser)
        sound_selector.set_on_change(on_sound_change)

        if found_paths:
            sound_selector.load_sounds(found_paths)
            sound_selector.set_by_path(saved_sound)
        else:
            sound_selector.load_sounds([])
            tk.Label(
                sound_frame,
                text=f"Place .mp3/.wav/.ogg files in:\n{sounds_dir}",
                bg=self.colors["card"],
                fg=self.colors["danger"],
                font=("Segoe UI", 9),
                justify="left",
            ).pack(anchor="w")

        # ---- VOICE (TTS) ----
        self._settings_section_label(container, "VOICE (TTS)")

        voice_frame = tk.Frame(container, bg=self.colors["card"], padx=15, pady=12)
        voice_frame.pack(fill="x", padx=20, pady=(0, 12))

        # 1) Voice selector
        tk.Label(
            voice_frame,
            text="Voice",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(0, 2))

        voices = self.alarm_manager.get_tts_voices()
        voice_display_names = []
        voice_ids = []
        current_idx = 0
        current_id = s.get("voice_id", "")

        if voices:
            for i, (vid, vname) in enumerate(voices):
                # Show language info more clearly
                display = vname if len(vname) <= 50 else vname[:47] + "..."
                voice_display_names.append(display)
                voice_ids.append(vid)
                if vid == current_id:
                    current_idx = i

            if current_id == "":
                for i, (vid, vname) in enumerate(voices):
                    if "Zira" in vname:
                        current_idx = i
                        break

            voice_combo = ttk.Combobox(
                voice_frame,
                values=voice_display_names,
                state="readonly",
                font=("Segoe UI", 10),
                style="Voice.TCombobox",
            )
            voice_combo.current(current_idx)
        else:
            voice_combo = ttk.Combobox(
                voice_frame,
                values=["No voices found"],
                state="disabled",
                font=("Segoe UI", 10),
                style="Voice.TCombobox",
            )
            voice_combo.current(0)
            voice_ids = []
            tk.Label(
                voice_frame,
                text="Install pyttsx3 for voice support",
                bg=self.colors["card"],
                fg=self.colors["danger"],
                font=("Segoe UI", 9),
            ).pack(anchor="w")

        voice_combo.pack(fill="x", pady=(0, 10))

        # 2) Speech speed slider
        rate_label = tk.Label(
            voice_frame,
            text="Speech Speed",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10),
        )
        rate_label.pack(anchor="w", pady=(4, 0))
        rate_frame = tk.Frame(voice_frame, bg=self.colors["card"])
        rate_frame.pack(fill="x", pady=(4, 0))
        tk.Label(
            rate_frame,
            text="Slow",
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 8),
        ).pack(side="left")
        tk.Label(
            rate_frame,
            text="Fast",
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 8),
        ).pack(side="right")
        settings_rate_var = tk.IntVar(value=s.get("tts_rate", 160))
        tk.Scale(
            voice_frame,
            from_=80,
            to=300,
            variable=settings_rate_var,
            orient="horizontal",
            bg=self.colors["card"],
            fg=self.colors["primary"],
            highlightthickness=0,
            troughcolor=self.colors["bg"],
            activebackground=self.colors["primary"],
            showvalue=False,
        ).pack(fill="x")

        # 3) TTS toggle (sound_selector already exists above)
        settings_tts_var = tk.BooleanVar(value=s.get("tts_enabled", True))

        tts_row = tk.Frame(voice_frame, bg=self.colors["card"])
        tts_row.pack(fill="x", pady=(10, 0))
        tk.Label(
            tts_row,
            text="Enable voice alerts",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 11),
        ).pack(side="left")
        tts_toggle = tk.Canvas(
            tts_row,
            width=32,
            height=24,
            bg=self.colors["card"],
            highlightthickness=0,
            cursor="hand2",
        )
        tts_toggle.pack(side="right")

        def on_tts_toggle():
            if settings_tts_var.get():
                name_entry.config(
                    state="normal",
                    bg=self.colors["bg"],
                    fg=self.colors["text"],
                    insertbackground="white",
                )
                voice_combo.config(state="readonly")
                rate_label.config(fg=self.colors["text"])
                sound_selector.config_state("normal")
            else:
                name_entry.config(
                    state="disabled",
                    bg=self.colors["disabled_bg"],
                    fg=self.colors["disabled_fg"],
                    insertbackground=self.colors["disabled_fg"],
                )
                voice_combo.config(state="disabled")
                rate_label.config(fg=self.colors["disabled_fg"])
                sound_selector.config_state("disabled")

        def update_tts_toggle():
            self.draw_toggle_icon(tts_toggle, settings_tts_var.get())
            on_tts_toggle()

        def on_tts_click(e):
            settings_tts_var.set(not settings_tts_var.get())
            update_tts_toggle()
            # --- Add these right below the TTS Toggle (on_tts_click) ---

        # Escalation Speed
        tk.Label(
            voice_frame,
            text="Escalation Speed (sec between loops)",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(10, 0))
        settings_esc_var = tk.IntVar(value=s.get("tts_escalation_speed", 10))
        tk.Scale(
            voice_frame,
            from_=3,
            to=20,
            variable=settings_esc_var,
            orient="horizontal",
            bg=self.colors["card"],
            fg=self.colors["primary"],
            highlightthickness=0,
            troughcolor=self.colors["bg"],
            activebackground=self.colors["primary"],
            showvalue=True,
        ).pack(fill="x")

        # Max Aggression
        tk.Label(
            voice_frame,
            text="Max Aggression Level",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(10, 0))
        settings_aggro_var = tk.StringVar(
            value=s.get("max_aggression_level", "unhinged")
        )
        aggro_row = tk.Frame(voice_frame, bg=self.colors["card"])
        aggro_row.pack(fill="x")
        for txt, val in [
            ("Polite (Loop 5)", "polite"),
            ("Firm (Loop 10)", "firm"),
            ("Unhinged (Loop 30)", "unhinged"),
        ]:
            tk.Radiobutton(
                aggro_row,
                text=txt,
                variable=settings_aggro_var,
                value=val,
                bg=self.colors["card"],
                fg=self.colors["text"],
                selectcolor=self.colors["bg"],
                activebackground=self.colors["card"],
                activeforeground=self.colors["primary"],
                font=("Segoe UI", 9),
                highlightthickness=0,
                bd=0,
            ).pack(anchor="w")

        # Dynamic Volume Checkbox
        settings_dyn_vol_var = tk.BooleanVar(value=s.get("dynamic_tts_volume", True))
        self.create_option_row(
            voice_frame,
            "Dynamic Volume (TTS louder, Sound quieter)",
            settings_dyn_vol_var,
        ).pack(fill="x", pady=(10, 0))

        # Custom Phrase Editor Button
        def open_phrase_editor():
            editor = tk.Toplevel(dialog)
            editor.title("Edit Aggressive Phrases")

            # Set Window Icon
            assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
            ico_path = os.path.join(assets_dir, "DawnGuardIco.ico")
            if os.path.exists(ico_path):
                try:
                    editor.iconbitmap(ico_path)
                except Exception:
                    pass

            self.center_window(editor, 600, 500)
            editor.configure(bg=self.colors["bg"])
            editor.transient(dialog)
            try:
                editor.grab_set()
            except:
                pass

            # Bottom Button Frame
            btn_frame = tk.Frame(editor, bg=self.colors["bg"])
            btn_frame.pack(side="bottom", fill="x", pady=15, padx=20)

            suggest_file = os.path.join(os.path.dirname(__file__), "suggest.text")
            txt_widget = tk.Text(
                editor,
                bg=self.colors["card"],
                fg=self.colors["text"],
                font=("Segoe UI", 11),
                wrap="word",
                insertbackground="white",
                padx=10,
                pady=10,
                bd=0,
            )
            txt_widget.pack(side="top", fill="both", expand=True, padx=20, pady=(20, 0))

            if os.path.exists(suggest_file):
                with open(suggest_file, "r", encoding="utf-8") as f:
                    txt_widget.insert("1.0", f.read())

            def save_phrases():
                with open(suggest_file, "w", encoding="utf-8") as f:
                    f.write(txt_widget.get("1.0", "end").strip())
                editor.destroy()

            # Save and Cancel buttons in a row
            tk.Button(
                btn_frame,
                text="Save Phrases",
                bg=self.colors["accent"],
                fg="white",
                font=("Segoe UI", 11, "bold"),
                bd=0,
                cursor="hand2",
                command=save_phrases,
            ).pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=8)

            tk.Button(
                btn_frame,
                text="Cancel",
                bg=self.colors["card"],
                fg=self.colors["text"],
                font=("Segoe UI", 11),
                bd=0,
                cursor="hand2",
                command=editor.destroy,
            ).pack(side="left", fill="x", expand=True, padx=(6, 0), ipady=8)

        tk.Button(
            voice_frame,
            text="✏️ Edit Custom Phrases",
            bg=self.colors["card_hover"],
            fg=self.colors["primary"],
            font=("Segoe UI", 9),
            bd=0,
            cursor="hand2",
            command=open_phrase_editor,
        ).pack(fill="x", pady=(10, 0), ipady=4)

        tts_toggle.bind("<Button-1>", on_tts_click)
        self.draw_toggle_icon(tts_toggle, settings_tts_var.get())

        # Set initial disabled states
        if not settings_tts_var.get():
            name_entry.config(
                state="disabled",
                bg=self.colors["disabled_bg"],
                fg=self.colors["disabled_fg"],
                insertbackground=self.colors["disabled_fg"],
            )
            voice_combo.config(state="disabled")
            rate_label.config(fg=self.colors["disabled_fg"])
            sound_selector.config_state("disabled")

        # ---- DEFAULTS FOR NEW ALARMS ----
        self._settings_section_label(container, "DEFAULTS FOR NEW ALARMS")

        defaults_frame = tk.Frame(container, bg=self.colors["card"], padx=15, pady=12)
        defaults_frame.pack(fill="x", padx=20, pady=(0, 12))

        # --- Add these to the defaults_frame ---

        # Snooze Penalty
        settings_snooze_pen_var = tk.BooleanVar(value=s.get("snooze_penalty", True))
        self.create_option_row(
            defaults_frame,
            "Snooze Penalty (Skip polite phase)",
            settings_snooze_pen_var,
        ).pack(fill="x", pady=(0, 10))

        # Pre-Alarm Warning
        pre_frame = tk.Frame(defaults_frame, bg=self.colors["card"])
        pre_frame.pack(fill="x", pady=(0, 10))
        settings_pre_var = tk.BooleanVar(value=s.get("pre_alarm_enabled", False))
        tk.Label(
            pre_frame,
            text="Pre-Alarm Warning",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 11),
        ).pack(side="left")
        pre_toggle = tk.Canvas(
            pre_frame,
            width=32,
            height=24,
            bg=self.colors["card"],
            highlightthickness=0,
            cursor="hand2",
        )
        pre_toggle.pack(side="right")

        def update_pre():
            self.draw_toggle_icon(pre_toggle, settings_pre_var.get())

        def click_pre(e):
            settings_pre_var.set(not settings_pre_var.get())
            update_pre()

        pre_toggle.bind("<Button-1>", click_pre)
        update_pre()

        pre_time_row = tk.Frame(defaults_frame, bg=self.colors["card"])
        pre_time_row.pack(fill="x", pady=(0, 10))
        tk.Label(
            pre_time_row,
            text="Warning Time (min before)",
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 10),
        ).pack(side="left")
        settings_pre_time_var = tk.IntVar(value=s.get("pre_alarm_time", 1))
        tk.Spinbox(
            pre_time_row,
            from_=1,
            to=10,
            textvariable=settings_pre_time_var,
            width=4,
            font=("Segoe UI", 12, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["primary"],
            buttonbackground=self.colors["card"],
            bd=0,
            highlightthickness=0,
            justify="center",
        ).pack(side="right")

        # Auto-Stop Timer
        auto_row = tk.Frame(defaults_frame, bg=self.colors["card"])
        auto_row.pack(fill="x")
        tk.Label(
            auto_row,
            text="Auto-Stop After (min)",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10),
        ).pack(side="left")
        settings_auto_stop_var = tk.IntVar(value=s.get("auto_stop_minutes", 15))
        tk.Spinbox(
            auto_row,
            from_=1,
            to=60,
            textvariable=settings_auto_stop_var,
            width=4,
            font=("Segoe UI", 12, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["primary"],
            buttonbackground=self.colors["card"],
            bd=0,
            highlightthickness=0,
            justify="center",
        ).pack(side="right")
        tk.Label(
            auto_row,
            text="min",
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 10),
        ).pack(side="right", padx=(4, 0))

        # 24-Hour Clock Toggle
        settings_24h_var = tk.BooleanVar(value=s.get("use_24h_format", True))
        self.create_option_row(
            defaults_frame, "24-Hour Clock Format", settings_24h_var
        ).pack(fill="x", pady=(10, 0))

        tk.Label(
            defaults_frame,
            text="Default Volume",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10),
        ).pack(anchor="w")
        settings_vol_var = tk.IntVar(value=s.get("default_volume", 80))
        tk.Scale(
            defaults_frame,
            from_=0,
            to=100,
            variable=settings_vol_var,
            orient="horizontal",
            bg=self.colors["card"],
            fg=self.colors["primary"],
            highlightthickness=0,
            troughcolor=self.colors["bg"],
            activebackground=self.colors["primary"],
            showvalue=False,
        ).pack(fill="x", pady=(4, 8))

        settings_fade_var = tk.BooleanVar(value=s.get("default_fade_in", True))
        self.create_option_row(
            defaults_frame, "Fade in by default", settings_fade_var
        ).pack(fill="x", pady=(0, 10))

        snooze_row = tk.Frame(defaults_frame, bg=self.colors["card"])
        snooze_row.pack(fill="x")
        tk.Label(
            snooze_row,
            text="Snooze Duration",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10),
        ).pack(side="left")
        settings_snooze_var = tk.IntVar(value=s.get("snooze_duration", 9))
        snooze_spin = tk.Spinbox(
            snooze_row,
            from_=1,
            to=30,
            textvariable=settings_snooze_var,
            width=4,
            font=("Segoe UI", 12, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["primary"],
            buttonbackground=self.colors["card"],
            bd=0,
            highlightthickness=0,
            justify="center",
        )
        snooze_spin.pack(side="right")
        tk.Label(
            snooze_row,
            text="min",
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 10),
        ).pack(side="right", padx=(4, 0))

        # ---- DISMISS PUZZLE ----
        self._settings_section_label(container, "DISMISS PUZZLE")

        puzzle_frame = tk.Frame(container, bg=self.colors["card"], padx=15, pady=12)
        puzzle_frame.pack(fill="x", padx=20, pady=(0, 12))

        tk.Label(
            puzzle_frame,
            text="Puzzle Type",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")

        settings_puzzle_var = tk.StringVar(value=s.get("puzzle_type", "math"))
        diff_row = tk.Frame(puzzle_frame, bg=self.colors["card"])
        diff_row.pack(fill="x", pady=(4, 8))

        for label_text, val in [
            ("Math", "math"),
            ("Typing Word", "word"),
            ("Simon Says", "simon"),
        ]:
            tk.Radiobutton(
                diff_row,
                text=label_text,
                variable=settings_puzzle_var,
                value=val,
                bg=self.colors["card"],
                fg=self.colors["text"],
                selectcolor=self.colors["bg"],
                activebackground=self.colors["card"],
                activeforeground=self.colors["primary"],
                font=("Segoe UI", 10),
                highlightthickness=0,
                bd=0,
            ).pack(side="left", padx=(0, 16))

        # Math Difficulty (only applies to Math)
        self.math_diff_frame = tk.Frame(puzzle_frame, bg=self.colors["card"])
        self.math_diff_frame.pack(fill="x")
        tk.Label(
            self.math_diff_frame,
            text="Math Difficulty",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(4, 0))
        tk.Label(
            self.math_diff_frame,
            text="Easy: small numbers  •  Medium: addition  •  Hard: multiplication",
            bg=self.colors["card"],
            fg=self.colors["text_muted"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 4))

        math_diff_row = tk.Frame(self.math_diff_frame, bg=self.colors["card"])
        math_diff_row.pack(fill="x")
        settings_diff_var = tk.StringVar(value=s.get("math_difficulty", "medium"))
        for label_text, val in [
            ("Easy", "easy"),
            ("Medium", "medium"),
            ("Hard", "hard"),
        ]:
            tk.Radiobutton(
                math_diff_row,
                text=label_text,
                variable=settings_diff_var,
                value=val,
                bg=self.colors["card"],
                fg=self.colors["text"],
                selectcolor=self.colors["bg"],
                activebackground=self.colors["card"],
                activeforeground=self.colors["primary"],
                font=("Segoe UI", 10),
                highlightthickness=0,
                bd=0,
            ).pack(side="left", padx=(0, 16))

        def toggle_math_visibility(*args):
            if settings_puzzle_var.get() == "math":
                self.math_diff_frame.pack(fill="x")
            else:
                self.math_diff_frame.pack_forget()

        settings_puzzle_var.trace_add("write", toggle_math_visibility)
        toggle_math_visibility()  # Run once to set initial state

        # ---- SAVE & RESET BUTTONS (outside any loop!) ----
        tk.Button(
            container,
            text="SAVE SETTINGS",
            font=("Segoe UI", 12, "bold"),
            bg=self.colors["accent"],
            fg="white",
            bd=0,
            cursor="hand2",
            # Update the command=lambda in the SAVE SETTINGS button to include the new vars:
            command=lambda: self._save_settings(
                dialog,
                settings_name_var,
                settings_tts_var,
                settings_rate_var,
                settings_vol_var,
                settings_fade_var,
                settings_snooze_var,
                settings_diff_var,
                voice_combo,
                voice_ids,
                sound_selector,
                settings_puzzle_var,
                settings_esc_var,
                settings_aggro_var,
                settings_dyn_vol_var,
                settings_snooze_pen_var,
                settings_pre_var,
                settings_pre_time_var,
                settings_auto_stop_var,
                settings_24h_var,
            ),
        ).pack(fill="x", pady=(25, 8), padx=30, ipady=10)

        tk.Button(
            container,
            text="RESET TO DEFAULTS",
            font=("Segoe UI", 11),
            bg=self.colors["danger"],
            fg="white",
            bd=0,
            cursor="hand2",
            command=lambda: self._reset_settings(dialog),
        ).pack(fill="x", pady=(0, 60), padx=30, ipady=6)

        dialog.protocol("WM_DELETE_WINDOW", lambda: self._close_settings(dialog))

    def _settings_section_label(self, parent, text):
        tk.Label(
            parent,
            text=text,
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(fill="x", padx=20, pady=(16, 6), anchor="w")

    def _save_settings(
        self,
        dialog,
        name_var,
        tts_var,
        rate_var,
        vol_var,
        fade_var,
        snooze_var,
        diff_var,
        voice_combo,
        voice_ids,
        sound_selector,
        puzzle_var,
        esc_var,
        aggro_var,
        dyn_vol_var,
        snooze_pen_var,
        pre_var,
        pre_time_var,
        auto_stop_var,
        format_24h_var,
    ):
        from config import save_settings

        s = self.alarm_manager.settings
        s["user_name"] = name_var.get().strip()
        s["tts_enabled"] = tts_var.get()
        s["tts_rate"] = rate_var.get()

        # Save selected voice ID
        voice_id = ""
        try:
            idx = voice_combo.current()
            if 0 <= idx < len(voice_ids):
                voice_id = voice_ids[idx]
        except Exception:
            pass
        s["voice_id"] = voice_id

        # Save selected default sound path
        s["default_sound"] = sound_selector.get_path()

        s["default_volume"] = vol_var.get()
        s["default_fade_in"] = fade_var.get()
        s["snooze_duration"] = snooze_var.get()
        s["math_difficulty"] = diff_var.get()
        s["puzzle_type"] = puzzle_var.get()
        s["tts_escalation_speed"] = esc_var.get()
        s["max_aggression_level"] = aggro_var.get()
        s["dynamic_tts_volume"] = dyn_vol_var.get()
        s["snooze_penalty"] = snooze_pen_var.get()
        s["pre_alarm_enabled"] = pre_var.get()
        s["pre_alarm_time"] = pre_time_var.get()
        s["auto_stop_minutes"] = auto_stop_var.get()
        s["use_24h_format"] = format_24h_var.get()
        save_settings(s)

        self.volume_var.set(s["default_volume"])
        self.fade_var.set(s["default_fade_in"])
        self._update_header_name()

        messagebox.showinfo("Settings", "Settings saved successfully!")
        dialog.destroy()
        self._settings_dialog = None

    def _close_settings(self, dialog):
        dialog.destroy()
        self._settings_dialog = None

    def _reset_settings(self, dialog):
        if not messagebox.askyesno(
            "Reset Settings",
            "This will reset ALL settings to defaults and delete your saved preferences.\n\nAre you sure?",
        ):
            return

        from config import DEFAULT_SETTINGS, SETTINGS_FILE, save_settings

        # Reset the in-memory settings
        self.alarm_manager.settings = dict(DEFAULT_SETTINGS)

        # Delete the settings file
        if os.path.exists(SETTINGS_FILE):
            try:
                os.remove(SETTINGS_FILE)
                print("[Config] settings.json deleted.")
            except Exception as e:
                print(f"[Config] Error deleting file: {e}")

        # Save fresh defaults so the file exists with clean values
        save_settings(self.alarm_manager.settings)

        # Update UI variables to match new defaults
        s = self.alarm_manager.settings
        self.volume_var.set(s.get("default_volume", 80))
        self.fade_var.set(s.get("default_fade_in", True))

        # Update header name (will be empty since default name is "")
        self._update_header_name()

        # Close the dialog
        dialog.destroy()
        self._settings_dialog = None

        messagebox.showinfo("Reset", "All settings have been reset to defaults.")

    # ===================== Edit Dialog =====================
    def open_edit_dialog(self, alarm):
        if self._edit_dialog and self._edit_dialog.winfo_exists():
            self._edit_dialog.lift()
            self._edit_dialog.focus_force()
            return

        dialog = tk.Toplevel(self.root)
        self._edit_dialog = dialog
        dialog.title("Edit Alarm")

        # Set Window Icon
        assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
        ico_path = os.path.join(assets_dir, "DawnGuardIco.ico")
        if os.path.exists(ico_path):
            try:
                dialog.iconbitmap(ico_path)
            except Exception:
                pass

        self.center_window(dialog, 420, 720)
        dialog.configure(bg=self.colors["bg"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        try:
            dialog.grab_set()
        except Exception:
            pass
        dialog.alarm = alarm

        outer = tk.Frame(dialog, bg=self.colors["scrollbar_trough"], bd=0)
        outer.pack(side="left", fill="both", expand=True)

        trough_strip = tk.Frame(outer, bg=self.colors["scrollbar_trough"], width=16)
        trough_strip.pack(side="right", fill="y")
        trough_strip.pack_propagate(False)

        canvas = tk.Canvas(outer, bg=self.colors["bg"], highlightthickness=0, bd=0)
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = self._create_visible_scrollbar(
            trough_strip, orient="vertical", command=canvas.yview
        )
        scrollbar.pack(side="right", fill="y", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)

        container = tk.Frame(canvas, bg=self.colors["bg"])
        canvas.create_window((0, 0), window=container, anchor="nw")
        container.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(canvas.find_withtag("all")[0], width=e.width),
        )

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 if event.delta > 0 else 1), "units")

        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)
        container.bind(
            "<Map>", lambda e: self._bind_mousewheel_recursive(container, on_mousewheel)
        )

        self.edit_hour_var = tk.StringVar(value=alarm.time.split(":")[0])
        self.edit_min_var = tk.StringVar(value=alarm.time.split(":")[1])
        self.edit_label_var = tk.StringVar(value=alarm.label)
        self.edit_repeat_vars = {
            d: tk.BooleanVar(value=d in getattr(alarm, "repeat", []))
            for d in [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
        }
        self.edit_volume_var = tk.IntVar(value=getattr(alarm, "volume", 80))
        self.edit_fade_var = tk.BooleanVar(value=getattr(alarm, "fade_in", True))
        self.edit_vibrate_var = tk.BooleanVar(value=getattr(alarm, "vibrate", False))
        self.edit_sound_path = getattr(alarm, "sound", None)
        self.edit_use_tts_var = tk.BooleanVar(value=getattr(alarm, "use_tts", True))

        self.create_time_section_edit(container)
        self.create_label_section_edit(container)
        self.create_repeat_section_edit(container)
        self.create_volume_section_edit(container)
        self.create_options_section_edit(container)
        self.create_alarm_type_section(container, self.edit_use_tts_var)
        self.create_sound_section_edit(container, tts_var=self.edit_use_tts_var)

        btn_frame = tk.Frame(container, bg=self.colors["bg"])
        btn_frame.pack(fill="x", pady=(25, 60), padx=30)
        tk.Button(
            btn_frame,
            text="Save Changes",
            bg=self.colors["accent"],
            fg="white",
            font=("Segoe UI", 12, "bold"),
            bd=0,
            cursor="hand2",
            command=lambda: self.save_edited_alarm(dialog),
        ).pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=8)
        tk.Button(
            btn_frame,
            text="Cancel",
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 12),
            bd=0,
            cursor="hand2",
            command=dialog.destroy,
        ).pack(side="left", fill="x", expand=True, padx=(6, 0), ipady=8)

    def create_time_section_edit(self, parent):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=15, padx=20)
        tk.Label(
            frame,
            text="ALARM TIME",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")
        tframe = tk.Frame(frame, bg=self.colors["card"], padx=20, pady=15)
        tframe.pack(fill="x", pady=8)
        inner_t = tk.Frame(tframe, bg=self.colors["card"])
        inner_t.pack(expand=True)

        def create_styled_spinbox(parent, var, from_, to):
            sb = tk.Spinbox(
                parent,
                from_=from_,
                to=to,
                textvariable=var,
                width=3,
                font=("Segoe UI", 32, "bold"),
                bg=self.colors["card"],
                fg=self.colors["primary"],
                buttonbackground=self.colors["card"],
                bd=0,
                highlightthickness=0,
                justify="center",
                format="%02.0f",
            )
            return sb

        h_sb = create_styled_spinbox(inner_t, self.edit_hour_var, 0, 23)
        h_sb.pack(side="left")
        tk.Label(
            inner_t,
            text=":",
            font=("Segoe UI", 32, "bold"),
            bg=self.colors["card"],
            fg=self.colors["text"],
        ).pack(side="left", padx=10)
        m_sb = create_styled_spinbox(inner_t, self.edit_min_var, 0, 59)
        m_sb.pack(side="left")

        self._setup_time_validation(h_sb, m_sb, self.edit_hour_var, self.edit_min_var)

    def create_label_section_edit(self, parent):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=10, padx=20)
        tk.Label(
            frame,
            text="LABEL",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")
        eframe = tk.Frame(frame, bg=self.colors["card"], padx=15, pady=10)
        eframe.pack(fill="x", pady=8)
        tk.Entry(
            eframe,
            textvariable=self.edit_label_var,
            font=("Segoe UI", 12),
            bg=self.colors["card"],
            fg=self.colors["text"],
            bd=0,
            insertbackground="white",
        ).pack(fill="x")
        tk.Frame(eframe, height=1, bg=self.colors["primary"]).pack(
            fill="x", pady=(5, 0)
        )

    def create_repeat_section_edit(self, parent):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=10, padx=20)
        tk.Label(
            frame,
            text="REPEAT",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")
        dframe = tk.Frame(frame, bg=self.colors["bg"])
        dframe.pack(fill="x", pady=10)
        for short, full in [
            ("M", "Monday"),
            ("T", "Tuesday"),
            ("W", "Wednesday"),
            ("T", "Thursday"),
            ("F", "Friday"),
            ("S", "Saturday"),
            ("S", "Sunday"),
        ]:
            self.create_day_chip(dframe, short, full, self.edit_repeat_vars[full]).pack(
                side="left", expand=True
            )

    def create_volume_section_edit(self, parent):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=10, padx=20)
        tk.Label(
            frame,
            text="VOLUME",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")
        vframe = tk.Frame(frame, bg=self.colors["card"], padx=20, pady=15)
        vframe.pack(fill="x", pady=8)
        tk.Scale(
            vframe,
            from_=0,
            to=100,
            variable=self.edit_volume_var,
            orient="horizontal",
            bg=self.colors["card"],
            fg=self.colors["primary"],
            highlightthickness=0,
            troughcolor=self.colors["bg"],
            activebackground=self.colors["primary"],
            showvalue=False,
        ).pack(fill="x")

    def create_options_section_edit(self, parent):
        frame = tk.Frame(parent, bg=self.colors["bg"])
        frame.pack(fill="x", pady=10, padx=20)
        tk.Label(
            frame,
            text="OPTIONS",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")
        inner = tk.Frame(frame, bg=self.colors["card"], padx=15, pady=10)
        inner.pack(fill="x", pady=8)
        self.create_option_row(
            inner, "Gradual wake (fade in)", self.edit_fade_var
        ).pack(fill="x", pady=5)
        self.create_option_row(inner, "Vibrate", self.edit_vibrate_var).pack(
            fill="x", pady=5
        )

    def create_sound_section_edit(self, parent, tts_var=None):
        wrapper = tk.Frame(parent, bg=self.colors["bg"])
        wrapper.pack(fill="x", pady=10, padx=20)

        inner = tk.Frame(wrapper, bg=self.colors["bg"])

        def toggle_visibility(*args):
            if tts_var and tts_var.get():
                inner.pack_forget()
            else:
                inner.pack(fill="x")

        inner.pack(fill="x")

        if tts_var:
            toggle_visibility()
            tts_var.trace_add("write", toggle_visibility)

        frame = tk.Frame(inner, bg=self.colors["bg"])
        frame.pack(fill="x")
        tk.Label(
            frame,
            text="SOUND",
            font=("Segoe UI", 10, "bold"),
            bg=self.colors["bg"],
            fg=self.colors["text_muted"],
        ).pack(anchor="w")
        sframe = tk.Frame(frame, bg=self.colors["card"], padx=15, pady=10)
        sframe.pack(fill="x", pady=8)
        text = (
            os.path.basename(self.edit_sound_path)
            if self.edit_sound_path
            else "Default Alarm"
        )
        self.edit_sound_label = tk.Label(
            sframe,
            text=text,
            bg=self.colors["card"],
            fg=self.colors["text"],
            font=("Segoe UI", 11),
        )
        self.edit_sound_label.pack(side="left")
        tk.Button(
            sframe,
            text="Browse",
            bg=self.colors["primary"],
            fg=self.colors["bg"],
            font=("Segoe UI", 9, "bold"),
            bd=0,
            padx=10,
            cursor="hand2",
            command=self.browse_sound_edit,
        ).pack(side="right")

    def browse_sound_edit(self):
        path = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.ogg")])
        if path:
            self.edit_sound_path = path
            self.edit_sound_label.config(text=os.path.basename(path))

    def save_edited_alarm(self, dialog):
        alarm = dialog.alarm
        try:
            hour = int(self.edit_hour_var.get())
            minute = int(self.edit_min_var.get())
            time_str = f"{hour:02d}:{minute:02d}"
        except ValueError:
            messagebox.showerror("Invalid Time", "Please enter valid numbers")
            return
        alarm.time = time_str
        alarm.label = self.edit_label_var.get().strip() or "Alarm"
        alarm.repeat = [d for d, v in self.edit_repeat_vars.items() if v.get()]
        alarm.volume = self.edit_volume_var.get()
        alarm.fade_in = self.edit_fade_var.get()
        alarm.vibrate = self.edit_vibrate_var.get()
        alarm.use_tts = self.edit_use_tts_var.get()
        if hasattr(self, "edit_sound_path") and self.edit_sound_path:
            alarm.sound = self.edit_sound_path
        from alarm import save_alarms

        save_alarms(self.alarm_manager.alarms)
        self.alarm_manager.restart_alarm_worker(alarm)
        self.refresh_alarm_cards()
        messagebox.showinfo("Success", "Alarm updated successfully!")
        dialog.destroy()
        self._edit_dialog = None
