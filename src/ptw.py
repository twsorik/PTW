"""PTW — простой видеоплеер с выбором аудиодорожек (одна / другая / обе сразу).

Движок — libmpv (libmpv-2.dll), интерфейс — tkinter.
"""
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if getattr(sys, "frozen", False):  # собранный PTW.exe
    RES_DIR = sys._MEIPASS
else:
    RES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
os.add_dll_directory(RES_DIR)
os.environ["PATH"] = RES_DIR + os.pathsep + os.environ.get("PATH", "")

import mpv  # noqa: E402  (после настройки пути к libmpv-2.dll)

import updater  # noqa: E402
from version import __version__  # noqa: E402

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

APP_NAME = "PTW"
SETTINGS_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME, "settings.json")

VIDEO_EXT = "*.mp4 *.mkv *.mov *.avi *.webm *.ts *.m4v *.flv *.wmv"

BG = "#16171b"
BAR = "#212228"
FG = "#e6e6e6"
DIM = "#8a8d96"
ACCENT = "#4f8cff"
BTN = "#2c2e36"
BTN_HOVER = "#3a3d47"

SEEK_STEP = 5
VOLUME_STEP = 5
MAX_VOLUME = 150  # выше 100% — усиление, удобно для тихого микрофона
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def fmt_time(sec):
    if sec is None:
        return "0:00"
    sec = int(sec)
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class FlatButton(tk.Label):
    """Плоская кнопка, которая не забирает фокус клавиатуры."""

    def __init__(self, master, text, command, width=None, **kw):
        super().__init__(master, text=text, bg=BTN, fg=FG, padx=10, pady=4,
                         font=("Segoe UI", 10), cursor="hand2", **kw)
        if width:
            self.configure(width=width)
        self.command = command
        self.active = False
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self._paint(hover=True))
        self.bind("<Leave>", lambda e: self._paint())

    def set_active(self, active):
        self.active = active
        self._paint()

    def _paint(self, hover=False):
        if self.active:
            self.configure(bg=ACCENT)
        else:
            self.configure(bg=BTN_HOVER if hover else BTN)


class SeekBar(tk.Canvas):
    """Полоса перемотки: клик или перетаскивание — переход к позиции."""

    def __init__(self, master, on_seek, height=16, width=None):
        super().__init__(master, height=height, bg=BAR, highlightthickness=0, cursor="hand2")
        if width:
            self.configure(width=width)
        self.on_seek = on_seek
        self.fraction = 0.0
        self.dragging = False
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def _frac_at(self, x):
        w = max(self.winfo_width(), 1)
        return min(max(x / w, 0.0), 1.0)

    def _press(self, e):
        self.dragging = True
        self.fraction = self._frac_at(e.x)
        self.redraw()
        self.on_seek(self.fraction, final=False)

    def _drag(self, e):
        self.fraction = self._frac_at(e.x)
        self.redraw()
        self.on_seek(self.fraction, final=False)

    def _release(self, e):
        self.dragging = False
        self.fraction = self._frac_at(e.x)
        self.on_seek(self.fraction, final=True)

    def set_fraction(self, f):
        if not self.dragging:
            self.fraction = f
            self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        mid = h // 2
        self.create_rectangle(0, mid - 2, w, mid + 2, fill="#3a3d47", width=0)
        x = int(w * self.fraction)
        self.create_rectangle(0, mid - 2, x, mid + 2, fill=ACCENT, width=0)
        self.create_oval(x - 6, mid - 6, x + 6, mid + 6, fill=FG, width=0)


class Player:
    def __init__(self, path=None):
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        self.root.geometry("1100x680")
        self.root.minsize(560, 360)
        try:
            self.root.iconbitmap(default=os.path.join(RES_DIR, "ptw.ico"))
        except tk.TclError:
            pass

        self.settings = load_settings()
        start_volume = int(self.settings.get("volume", 80))
        self.update_window = None
        self.events = queue.Queue()  # действия из фоновых потоков -> поток tk
        self.audio_ids = []
        self.audio_mode = "both"  # 1, 2, ..., или "both"
        self.duration = None
        self.fullscreen = False
        self.bar_visible = True
        self.speed_index = SPEEDS.index(1.0)

        self._build_ui(start_volume)
        self.root.update()

        self.mpv = mpv.MPV(
            wid=str(self.video.winfo_id()),
            input_default_bindings=False,
            input_vo_keyboard=True,
            keep_open="yes",
            idle="yes",
            osc=False,
            hwdec="auto-safe",
            volume=start_volume,
            volume_max=MAX_VOLUME,
        )
        self._bind_keys()
        self.mpv.observe_property("track-list", lambda name, val: self.events.put(("tracks", val)))
        self.mpv.observe_property("pause", lambda name, val: self.events.put(("pause", val)))

        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.after(50, self._tick)

        if path:
            self.open(path)
        self.root.after(3000, lambda: self.check_updates(manual=False))

    # ---------- интерфейс ----------
    def _build_ui(self, start_volume):
        self.video = tk.Frame(self.root, bg="black")
        self.video.pack(fill="both", expand=True)

        self.hint = tk.Label(self.video, text="Ctrl+O — открыть видео" +
                             ("\nили перетащите файл в окно" if TkinterDnD else ""),
                             bg="black", fg=DIM, font=("Segoe UI", 12))
        self.hint.place(relx=0.5, rely=0.5, anchor="center")

        self.bar = tk.Frame(self.root, bg=BAR)
        self.bar.pack(fill="x", side="bottom")

        self.seek = SeekBar(self.bar, self.seek_to)
        self.seek.pack(fill="x", padx=12, pady=(8, 2))

        row = tk.Frame(self.bar, bg=BAR)
        row.pack(fill="x", padx=8, pady=(2, 8))

        FlatButton(row, "📂", self.ask_open).pack(side="left", padx=2)
        self.play_btn = FlatButton(row, "▶", self.toggle_pause, width=2)
        self.play_btn.pack(side="left", padx=2)
        FlatButton(row, "⏪", lambda: self.seek_relative(-SEEK_STEP)).pack(side="left", padx=2)
        FlatButton(row, "⏩", lambda: self.seek_relative(SEEK_STEP)).pack(side="left", padx=2)

        self.time_lbl = tk.Label(row, text="0:00 / 0:00", bg=BAR, fg=FG, font=("Segoe UI", 10))
        self.time_lbl.pack(side="left", padx=10)

        # справа налево: меню, полноэкранный, громкость, скорость, дорожки
        self.menu = tk.Menu(self.root, tearoff=0, bg=BAR, fg=FG, activebackground=ACCENT,
                            activeforeground="white", bd=0, font=("Segoe UI", 10))
        self.menu.add_command(label="Открыть видео…    Ctrl+O", command=self.ask_open)
        self.menu.add_separator()
        self.menu.add_command(label="Сделать PTW плеером по умолчанию", command=self.open_default_apps)
        self.menu.add_command(label="Проверить обновления", command=lambda: self.check_updates(manual=True))
        self.menu.add_separator()
        self.menu.add_command(label="О программе", command=self.show_about)
        self.menu_btn = FlatButton(row, "☰", self.show_menu)
        self.menu_btn.pack(side="right", padx=2)
        FlatButton(row, "⛶", self.toggle_fullscreen).pack(side="right", padx=2)

        self.vol_lbl = tk.Label(row, text=f"{start_volume}%", bg=BAR, fg=FG, width=4,
                                font=("Segoe UI", 10))
        self.vol_lbl.pack(side="right")
        self.vol_bar = SeekBar(row, lambda f, final: self.set_volume(round(f * MAX_VOLUME)),
                               height=24, width=110)
        self.vol_bar.set_fraction(start_volume / MAX_VOLUME)
        self.vol_bar.pack(side="right", padx=(4, 4))
        self.mute_btn = FlatButton(row, "🔊", self.toggle_mute)
        self.mute_btn.pack(side="right", padx=2)

        self.speed_lbl = FlatButton(row, "1×", self.cycle_speed, width=4)
        self.speed_lbl.pack(side="right", padx=(2, 12))

        self.track_box = tk.Frame(row, bg=BAR)
        self.track_box.pack(side="right", padx=8)
        self.track_buttons = {}

        self.root.bind_all("<Key>", self._tk_key)
        self.root.bind_all("<MouseWheel>", self._tk_wheel)
        self.video.bind("<Double-Button-1>", lambda e: self.toggle_fullscreen())
        self.video.bind("<Button-1>", lambda e: self.toggle_pause())
        if TkinterDnD:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)

    def _rebuild_track_buttons(self):
        for w in self.track_box.winfo_children():
            w.destroy()
        self.track_buttons = {}
        if not self.audio_ids:
            return
        tk.Label(self.track_box, text="Звук:", bg=BAR, fg=DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 4))
        for tid, title in self.audio_ids:
            b = FlatButton(self.track_box, title, lambda t=tid: self.set_audio_mode(t))
            b.pack(side="left", padx=1)
            self.track_buttons[tid] = b
        if len(self.audio_ids) > 1:
            b = FlatButton(self.track_box, "Обе", lambda: self.set_audio_mode("both"))
            b.pack(side="left", padx=1)
            self.track_buttons["both"] = b
        self._paint_track_buttons()

    def _paint_track_buttons(self):
        for key, b in self.track_buttons.items():
            b.set_active(key == self.audio_mode)

    # ---------- клавиши и мышь ----------
    def _bind_keys(self):
        """Клавиши, пока фокус в окне видео (mpv)."""
        keys = {
            "SPACE": self.toggle_pause,
            "LEFT": lambda: self.seek_relative(-SEEK_STEP),
            "RIGHT": lambda: self.seek_relative(SEEK_STEP),
            "UP": lambda: self.change_volume(VOLUME_STEP),
            "DOWN": lambda: self.change_volume(-VOLUME_STEP),
            "WHEEL_UP": lambda: self.change_volume(VOLUME_STEP),
            "WHEEL_DOWN": lambda: self.change_volume(-VOLUME_STEP),
            "MBTN_LEFT": self.toggle_pause,
            "MBTN_LEFT_DBL": self.toggle_fullscreen,
            "f": self.toggle_fullscreen,
            "F": self.toggle_fullscreen,
            "ENTER": self.toggle_fullscreen,
            "ESC": self.exit_fullscreen,
            "m": self.toggle_mute,
            "M": self.toggle_mute,
            "1": lambda: self.set_audio_mode_by_index(0),
            "2": lambda: self.set_audio_mode_by_index(1),
            "3": lambda: self.set_audio_mode("both"),
            "[": lambda: self.change_speed(-1),
            "]": lambda: self.change_speed(1),
            "BS": self.reset_speed,
            "Ctrl+o": self.ask_open,
        }
        repeating = {"LEFT", "RIGHT", "UP", "DOWN"}
        for key, fn in keys.items():
            self.mpv.on_key_press(key, repetition=key in repeating)(
                lambda fn=fn: self.events.put(("call", fn)))

    def _tk_key(self, e):
        k, ctrl = e.keysym, bool(e.state & 0x4)
        if ctrl and k.lower() in ("o", "щ"):
            self.ask_open()
            return
        table = {
            "space": self.toggle_pause,
            "Left": lambda: self.seek_relative(-SEEK_STEP),
            "Right": lambda: self.seek_relative(SEEK_STEP),
            "Up": lambda: self.change_volume(VOLUME_STEP),
            "Down": lambda: self.change_volume(-VOLUME_STEP),
            "Escape": self.exit_fullscreen,
            "Return": self.toggle_fullscreen,
            "BackSpace": self.reset_speed,
            "bracketleft": lambda: self.change_speed(-1),
            "bracketright": lambda: self.change_speed(1),
            "1": lambda: self.set_audio_mode_by_index(0),
            "2": lambda: self.set_audio_mode_by_index(1),
            "3": lambda: self.set_audio_mode("both"),
        }
        # буквы работают и в русской раскладке
        letter = {"f": self.toggle_fullscreen, "а": self.toggle_fullscreen,
                  "m": self.toggle_mute, "ь": self.toggle_mute,
                  "х": lambda: self.change_speed(-1), "ъ": lambda: self.change_speed(1)}
        fn = table.get(k) or letter.get(e.char.lower() if e.char else "")
        if fn:
            fn()
            return "break"

    def _tk_wheel(self, e):
        self.change_volume(VOLUME_STEP if e.delta > 0 else -VOLUME_STEP)

    def _on_drop(self, e):
        files = self.root.tk.splitlist(e.data)
        if files:
            self.open(files[0])

    # ---------- действия ----------
    def ask_open(self):
        path = filedialog.askopenfilename(
            title="Открыть видео",
            filetypes=[("Видео", VIDEO_EXT), ("Все файлы", "*.*")],
            initialdir=self.settings.get("last_dir") or os.path.expanduser("~\\Videos"))
        if path:
            self.open(path)

    def open(self, path):
        if not os.path.isfile(path):
            messagebox.showerror(APP_NAME, f"Файл не найден:\n{path}")
            return
        self.settings["last_dir"] = os.path.dirname(os.path.abspath(path))
        self.hint.place_forget()
        self.audio_ids = []
        self.audio_mode = "both"
        self.mpv.lavfi_complex = ""
        self.mpv.play(path)
        self.mpv.pause = False
        self.root.title(f"{os.path.basename(path)} — {APP_NAME}")

    def _on_tracks(self, tracks):
        audio = [t for t in (tracks or []) if t.get("type") == "audio"]
        ids = [t["id"] for t in audio]
        if ids == [tid for tid, _ in self.audio_ids]:
            return
        names = {}
        for n, t in enumerate(audio):
            title = t.get("title") or t.get("lang")
            if not title:
                # Запись ShadowPlay / NVIDIA: 1 — системные звуки, 2 — микрофон
                if len(audio) == 2:
                    title = ["Системные", "Микрофон"][n]
                else:
                    title = f"Дорожка {n + 1}"
            names[t["id"]] = f"{n + 1} · {title}"
        self.audio_ids = [(tid, names[tid]) for tid in ids]
        self.audio_mode = "both" if len(ids) > 1 else (ids[0] if ids else None)
        self._apply_audio_mode()
        self._rebuild_track_buttons()

    def set_audio_mode_by_index(self, i):
        if i < len(self.audio_ids):
            self.set_audio_mode(self.audio_ids[i][0])

    def set_audio_mode(self, mode):
        if mode == "both" and len(self.audio_ids) < 2:
            return
        if mode == self.audio_mode:
            return
        self.audio_mode = mode
        self._apply_audio_mode()
        self._paint_track_buttons()

    def _apply_audio_mode(self):
        if not self.audio_ids:
            return
        if self.audio_mode == "both":
            inputs = "".join(f"[aid{tid}]" for tid, _ in self.audio_ids)
            graph = f"{inputs}amix=inputs={len(self.audio_ids)}:normalize=0[ao]"
            self.mpv.lavfi_complex = graph
        else:
            self.mpv.lavfi_complex = ""
            self.mpv.aid = self.audio_mode

    def toggle_pause(self):
        if self.mpv.path is None and not self.mpv.playlist:
            self.ask_open()
            return
        self.mpv.pause = not self.mpv.pause

    def seek_relative(self, sec):
        try:
            self.mpv.seek(sec, "relative+exact")
        except SystemError:
            pass

    def seek_to(self, fraction, final):
        if not self.duration:
            return
        target = fraction * self.duration
        self.time_lbl.configure(text=f"{fmt_time(target)} / {fmt_time(self.duration)}")
        try:
            self.mpv.seek(target, "absolute+exact" if final else "absolute+keyframes")
        except SystemError:
            pass

    def set_volume(self, v):
        v = max(0, min(MAX_VOLUME, v))
        self.mpv.volume = v
        if self.mpv.mute and v > 0:
            self.mpv.mute = False
        self.vol_lbl.configure(text=f"{v}%")
        self.vol_bar.set_fraction(v / MAX_VOLUME)
        self._paint_mute()

    def change_volume(self, delta):
        self.set_volume(int(round(self.mpv.volume or 0)) + delta)

    def toggle_mute(self):
        self.mpv.mute = not self.mpv.mute
        self._paint_mute()

    def _paint_mute(self):
        self.mute_btn.configure(text="🔇" if self.mpv.mute else "🔊")

    def change_speed(self, step):
        self.speed_index = max(0, min(len(SPEEDS) - 1, self.speed_index + step))
        self._apply_speed()

    def cycle_speed(self):
        self.speed_index = (self.speed_index + 1) % len(SPEEDS)
        self._apply_speed()

    def reset_speed(self):
        self.speed_index = SPEEDS.index(1.0)
        self._apply_speed()

    def _apply_speed(self):
        s = SPEEDS[self.speed_index]
        self.mpv.speed = s
        self.speed_lbl.configure(text=f"{s:g}×")
        self.speed_lbl.set_active(s != 1.0)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)
        self._show_bar(not self.fullscreen)

    def exit_fullscreen(self):
        if self.fullscreen:
            self.toggle_fullscreen()

    def _show_bar(self, show):
        if show and not self.bar_visible:
            self.bar.pack(fill="x", side="bottom", before=self.video)
        elif not show and self.bar_visible:
            self.bar.pack_forget()
        self.bar_visible = show

    # ---------- цикл обновления ----------
    def _tick(self):
        try:
            while True:
                kind, val = self.events.get_nowait()
                if kind == "call":
                    val()
                elif kind == "tracks":
                    self._on_tracks(val)
                elif kind == "pause":
                    self.play_btn.configure(text="▶" if val else "⏸")
        except queue.Empty:
            pass

        try:
            pos = self.mpv.time_pos
            self.duration = self.mpv.duration
        except Exception:
            pos = None
        if self.duration and not self.seek.dragging:
            self.seek.set_fraction((pos or 0) / self.duration)
            self.time_lbl.configure(text=f"{fmt_time(pos)} / {fmt_time(self.duration)}")

        # в полноэкранном режиме панель появляется, когда мышь у нижнего края
        if self.fullscreen:
            y = self.root.winfo_pointery() - self.root.winfo_rooty()
            self._show_bar(y > self.root.winfo_height() - 90)

        self.root.after(50, self._tick)

    # ---------- меню ----------
    def show_menu(self):
        b = self.menu_btn
        self.menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() - self.menu.winfo_reqheight())

    def open_default_apps(self):
        messagebox.showinfo(
            APP_NAME,
            "Сейчас откроются «Приложения по умолчанию» Windows.\n\n"
            "Выберите там нужные форматы (.mp4, .mkv и т. д.) и укажите PTW.\n"
            "Ещё способ: правый клик по видео → «Открыть с помощью» → PTW → «Всегда».")
        try:
            os.startfile("ms-settings:defaultapps?registeredAppUser=PTW")
        except OSError:
            os.startfile("ms-settings:defaultapps")

    def show_about(self):
        messagebox.showinfo(
            f"О программе {APP_NAME}",
            f"{APP_NAME} {__version__}\n\n"
            "Видеоплеер с выбором аудиодорожек: можно слушать одну дорожку\n"
            "(например, только микрофон) или обе сразу.\n\n"
            "Движок воспроизведения — mpv (mpv.io).")

    # ---------- обновления ----------
    def check_updates(self, manual):
        if not updater.is_configured():
            if manual:
                messagebox.showinfo(APP_NAME, "Источник обновлений ещё не настроен.")
            return

        def work():
            try:
                info = updater.check()
            except Exception as e:  # сеть, GitHub недоступен и т. п.
                if manual:
                    self.events.put(("call", lambda: messagebox.showwarning(
                        APP_NAME, f"Не удалось проверить обновления:\n{e}")))
                return
            self.events.put(("call", lambda: self._on_update_checked(info, manual)))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, info, manual):
        if info is None:
            if manual:
                messagebox.showinfo(APP_NAME, f"У вас последняя версия ({__version__}).")
            return
        if not manual and self.settings.get("skipped_version") == info.version:
            return
        self._show_update_dialog(info)

    def _show_update_dialog(self, info):
        if self.update_window is not None:
            return
        win = self.update_window = tk.Toplevel(self.root, bg=BG)
        win.title(f"Обновление {APP_NAME}")
        win.resizable(False, False)
        win.transient(self.root)
        win.protocol("WM_DELETE_WINDOW", self._close_update_dialog)

        tk.Label(win, text=f"Доступна новая версия {APP_NAME} {info.version}",
                 bg=BG, fg=FG, font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(win, text=f"У вас установлена {__version__}", bg=BG, fg=DIM,
                 font=("Segoe UI", 10)).pack(anchor="w", padx=16)
        if info.notes.strip():
            notes = tk.Text(win, width=60, height=min(12, info.notes.count("\n") + 2), bg=BAR, fg=FG,
                            relief="flat", wrap="word", font=("Segoe UI", 10), padx=8, pady=6)
            notes.insert("1.0", info.notes.strip())
            notes.configure(state="disabled")
            notes.pack(fill="x", padx=16, pady=(10, 0))

        self.update_status = tk.Label(win, text="", bg=BG, fg=DIM, font=("Segoe UI", 10))
        self.update_status.pack(anchor="w", padx=16, pady=(10, 0))
        self.update_progress = ttk.Progressbar(win, length=420, maximum=1.0)

        btns = tk.Frame(win, bg=BG)
        btns.pack(fill="x", padx=16, pady=14)
        self.update_btns = [
            FlatButton(btns, "Обновить", lambda: self._start_update(info)),
            FlatButton(btns, "Позже", self._close_update_dialog),
            FlatButton(btns, "Пропустить версию", lambda: self._skip_version(info)),
        ]
        self.update_btns[0].set_active(True)
        for b in self.update_btns:
            b.pack(side="left", padx=(0, 6))

    def _close_update_dialog(self):
        if self.update_window is not None:
            self.update_window.destroy()
            self.update_window = None

    def _skip_version(self, info):
        self.settings["skipped_version"] = info.version
        save_settings(self.settings)
        self._close_update_dialog()

    def _start_update(self, info):
        for b in self.update_btns:
            b.pack_forget()
        self.update_status.configure(text="Загрузка обновления…")
        self.update_progress.pack(padx=16, pady=(4, 0))

        def progress(f):
            self.events.put(("call", lambda: self.update_progress.configure(value=f)))

        def work():
            try:
                path = updater.download(info, progress)
            except Exception as e:
                self.events.put(("call", lambda: self._update_failed(e)))
                return
            self.events.put(("call", lambda: self._install_update(path)))

        threading.Thread(target=work, daemon=True).start()

    def _update_failed(self, error):
        self._close_update_dialog()
        messagebox.showerror(APP_NAME, f"Не удалось скачать обновление:\n{error}")

    def _install_update(self, path):
        self.update_status.configure(text="Установка… PTW перезапустится сам.")
        self.root.update()
        updater.run_installer(path)
        self.quit()

    def quit(self):
        self.settings["volume"] = int(round(self.mpv.volume or 0))
        save_settings(self.settings)
        try:
            self.mpv.terminate()
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Player(sys.argv[1] if len(sys.argv) > 1 else None).run()
