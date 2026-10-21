"""PTW — видеоплеер с выбором аудиодорожек: одна дорожка или все сразу, у каждой своя громкость.

Движок — libmpv (libmpv-2.dll), интерфейс — Qt (PySide6).
"""
import json
import os
import queue
import sys
import threading
import time

if getattr(sys, "frozen", False):  # собранный PTW.exe
    RES_DIR = sys._MEIPASS
else:
    RES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
os.add_dll_directory(RES_DIR)
os.environ["PATH"] = RES_DIR + os.pathsep + os.environ.get("PATH", "")

import mpv  # noqa: E402  (после настройки пути к libmpv-2.dll)
from PySide6.QtCore import QPoint, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QCursor, QFontMetrics, QIcon, QPainter, QPalette, QPen  # noqa: E402
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame, QGridLayout,  # noqa: E402
                               QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget,
                               QTextBrowser, QVBoxLayout, QWidget)

import ui  # noqa: E402
import updater  # noqa: E402
from ui import (ACCENT, BAR, BG, BOOST, DIM, FG, FG2, LINE, SEG_LINE, Button, DropZone,  # noqa: E402
                IconButton, IconTile, MenuItem, Overlay, PauseBadge, PlayButton, Popup, ProgressLine,
                Segmented, Slider, Toast, caption, divider, kbd, label, pill, rgba, separator)
from version import __version__  # noqa: E402

APP_NAME = "PTW"
SETTINGS_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME, "settings.json")

VIDEO_EXT = "*.mp4 *.mkv *.mov *.avi *.webm *.ts *.m4v *.flv *.wmv"

SEEK_STEP = 5
VOLUME_STEP = 5
MAX_VOLUME = 150  # выше 100% — усиление, удобно для тихого микрофона
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
FS_HIDE_AFTER = 2.5  # через сколько секунд без движения мыши прятать панель в полном экране
NARROW_WIDTH = 1040  # уже — прячем ползунок громкости и кнопку «Открыть»


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


def fmt_speed(s):
    return f"{s:g}".replace(".", ",") + "×"


def track_name(i):
    return f"{i + 1} дорожка"


class ControlBar(QWidget):
    """Панель управления. В полном экране «плавает» над видео со скруглёнными углами."""

    def __init__(self):
        super().__init__()
        self.box = QVBoxLayout(self)
        self.box.setSpacing(10)
        self.set_floating(False)

    def set_floating(self, floating):
        self.floating = floating
        self.box.setContentsMargins(*((18, 14, 18, 12) if floating else (20, 14, 20, 16)))
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.floating:
            p.setPen(QPen(QColor(SEG_LINE), 1))
            p.setBrush(rgba(BAR, 242))
            p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 18, 18)
        else:
            p.fillRect(self.rect(), QColor(BAR))
            p.fillRect(0, 0, self.width(), 1, QColor(LINE))


class UpdateDialog(QDialog):
    def __init__(self, parent, info):
        super().__init__(parent)
        self.setWindowTitle(f"Обновление {APP_NAME}")
        self.setFixedWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 22, 28, 24)
        v.setSpacing(20)

        head = QHBoxLayout()
        head.setSpacing(16)
        head.addWidget(IconTile("download", 48, 24, 14))
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label(f"Доступна версия {info.version}", 18, FG, 600, display=True))
        titles.addWidget(label(f"Сейчас установлена {__version__}", 13, DIM))
        head.addLayout(titles, 1)
        v.addLayout(head)

        if info.notes.strip():
            box = QFrame()
            box.setObjectName("notes")
            box.setStyleSheet(f"#notes {{ background: {ui.SEG_BG}; border: 1px solid {SEG_LINE};"
                              f" border-radius: 12px; }}")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(16, 14, 12, 12)
            bl.setSpacing(6)
            bl.addWidget(caption("Что нового"))
            notes = QTextBrowser()
            notes.setOpenExternalLinks(True)
            notes.setFrameShape(QFrame.NoFrame)
            notes.setStyleSheet(f"QTextBrowser {{ background: transparent; color: {FG2}; border: 0; }}")
            notes.setFont(ui.font(13))
            notes.document().setDefaultStyleSheet(f"a {{ color: {ui.ACCENT_SOFT}; }}")
            notes.setMarkdown(info.notes.strip())
            notes.setMaximumHeight(200)
            bl.addWidget(notes)
            v.addWidget(box)

        self.progress_box = QWidget()
        pl = QVBoxLayout(self.progress_box)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(8)
        row = QHBoxLayout()
        self.status = label("Загрузка обновления…", 12, DIM)
        self.percent = label("0%", 12, DIM)
        row.addWidget(self.status)
        row.addStretch()
        row.addWidget(self.percent)
        pl.addLayout(row)
        self.progress = ProgressLine()
        pl.addWidget(self.progress)
        self.progress_box.hide()
        v.addWidget(self.progress_box)

        self.buttons = QWidget()
        btns = QHBoxLayout(self.buttons)
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(8)
        self.skip_btn = Button("Пропустить версию", "ghost", height=36, px=13, pad=12, radius=8)
        self.skip_btn.text_color = None
        self.later_btn = Button("Позже", "outline")
        self.update_btn = Button("Обновить", "primary", weight=600, pad=20)
        btns.addWidget(self.skip_btn)
        btns.addStretch()
        btns.addWidget(self.later_btn)
        btns.addWidget(self.update_btn)
        v.addWidget(self.buttons)
        ui.dark_titlebar(self)

    def start_progress(self):
        self.buttons.hide()
        self.progress_box.show()

    def set_progress(self, f):
        self.progress.set_fraction(f)
        self.percent.setText(f"{round(f * 100)}%")

    def set_status(self, text):
        self.status.setText(text)


class Player(QMainWindow):
    def __init__(self, path=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 680)
        self.setMinimumSize(900, 500)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.settings = load_settings()
        start_volume = int(self.settings.get("volume", 80))
        self.track_vol = [max(0, min(MAX_VOLUME, int(v))) for v in self.settings.get("track_volumes", [])]
        self.track_mute = []
        self.update_window = None
        self.events = queue.Queue()  # действия из фоновых потоков -> поток Qt
        self.audio_ids = []
        self.audio_mode = "both"  # id дорожки или "both"
        self.graph = ""
        self.duration = None
        self.paused = True
        self.loaded = False
        self.fullscreen = False
        self.was_maximized = False
        self.fs_visible = False
        self.last_cursor = QPoint()
        self.last_activity = 0.0
        self.speed_index = SPEEDS.index(1.0)
        self.mix_rows = []

        self._build_ui(start_volume)
        self.show()
        ui.dark_titlebar(self)
        QApplication.processEvents()

        self.mpv = mpv.MPV(
            wid=str(int(self.video.winId())),
            input_default_bindings=False,
            input_vo_keyboard=True,
            keep_open="yes",
            idle="yes",
            osc=False,
            hwdec="auto-safe",
            volume=start_volume,
            volume_max=MAX_VOLUME,
            drag_and_drop="no",  # файлы принимает окно PTW, а не mpv
        )
        self._bind_keys()
        self.mpv.observe_property("track-list", lambda name, val: self.events.put(("tracks", val)))
        self.mpv.observe_property("pause", lambda name, val: self.events.put(("pause", val)))
        self._set_volume_ui(start_volume)

        self.mix_timer = QTimer(self, singleShot=True, interval=150, timeout=self._apply_audio_mode)
        self.timer = QTimer(self, interval=50, timeout=self._tick)
        self.timer.start()

        if path:
            self.open(path)
        QTimer.singleShot(3000, lambda: self.check_updates(manual=False))

    # ---------- интерфейс ----------
    def _build_ui(self, start_volume):
        self.central = QWidget()
        self.central.setAutoFillBackground(True)
        pal = self.central.palette()
        pal.setColor(QPalette.Window, QColor(BG))
        self.central.setPalette(pal)
        self.setCentralWidget(self.central)
        self.layout_main = QVBoxLayout(self.central)
        self.layout_main.setContentsMargins(0, 0, 0, 0)
        self.layout_main.setSpacing(0)

        self.stack = QStackedWidget()
        self.video = QWidget()
        self.video.setAttribute(Qt.WA_NativeWindow)
        self.video.setAttribute(Qt.WA_DontCreateNativeAncestors)
        self.video.setAutoFillBackground(True)
        vp = self.video.palette()
        vp.setColor(QPalette.Window, QColor("#000000"))
        self.video.setPalette(vp)
        self.start_page = self._build_start_page()
        self.stack.addWidget(self.start_page)
        self.stack.addWidget(self.video)
        self.layout_main.addWidget(self.stack, 1)

        self._build_bar(start_volume)
        self.layout_main.addWidget(self.bar)
        self.bar.hide()  # на стартовом экране панель не нужна

        self.speed_pop = Popup(self, 168)
        self.menu_pop = Popup(self, 300)
        self.mix_pop = Popup(self, 340)
        self.toast = Toast(self)
        self.badge = PauseBadge(self)

        # полноэкранный режим: панель и верхняя плашка в отдельных прозрачных окнах поверх видео
        self.fs_bottom = Overlay(self)
        self.fs_top = Overlay(self)
        self.fs_name = pill("")
        self.fs_track = pill("", FG2)
        self.fs_esc = pill("Esc — выйти", DIM, 12)
        self.fs_top.box.addWidget(self.fs_name)
        self.fs_top.box.addStretch()
        self.fs_top.box.addWidget(self.fs_track)
        self.fs_top.box.addWidget(self.fs_esc)

    def _build_bar(self, start_volume):
        self.bar = ControlBar()

        seek_row = QHBoxLayout()
        seek_row.setSpacing(14)
        self.cur_lbl = label("0:00", 12, FG2)
        self.cur_lbl.setMinimumWidth(44)
        self.seek = Slider(grow=True)
        self.seek.moved.connect(lambda f: self.seek_to(f, final=False))
        self.seek.released.connect(lambda f: self.seek_to(f, final=True))
        self.dur_lbl = label("0:00", 12, DIM)
        self.dur_lbl.setMinimumWidth(44)
        self.dur_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        seek_row.addWidget(self.cur_lbl)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.dur_lbl)
        self.bar.box.addLayout(seek_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)

        # слева: воспроизведение
        left = QHBoxLayout()
        left.setSpacing(4)
        self.play_btn = PlayButton()
        self.play_btn.set_playing(False)
        self.play_btn.clicked.connect(self.toggle_pause)
        left.addWidget(self.play_btn)
        left.addSpacing(6)
        back = IconButton("back5", "Назад на 5 с (←)", icon_size=22)
        back.clicked.connect(lambda: self.seek_relative(-SEEK_STEP))
        fwd = IconButton("fwd5", "Вперёд на 5 с (→)", icon_size=22)
        fwd.clicked.connect(lambda: self.seek_relative(SEEK_STEP))
        self.open_btn = IconButton("folder", "Открыть видео (Ctrl+O)")
        self.open_btn.clicked.connect(self.ask_open)
        for w in (back, fwd, self.open_btn):
            left.addWidget(w)
        left.addStretch()
        grid.addLayout(left, 0, 0)

        # центр: дорожки и их громкость
        self.tracks_box = QWidget()
        center = QHBoxLayout(self.tracks_box)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(8)
        self.seg = Segmented()
        self.seg.picked.connect(lambda k: self.set_audio_mode(k, toast=True))
        self.mix_btn = IconButton("mixer", "Громкость дорожек", size=44, radius=12)
        self.mix_btn.clicked.connect(self.show_mixer)
        center.addWidget(self.seg)
        center.addWidget(self.mix_btn)
        self.tracks_box.hide()
        grid.addWidget(self.tracks_box, 0, 1)

        # справа: скорость, громкость, меню, полный экран (всегда в правом углу)
        right = QHBoxLayout()
        right.setSpacing(4)
        right.addStretch()
        self.speed_btn = Button("1×", "outline", height=32, px=13, weight=600, pad=10, radius=8)
        self.speed_btn.setToolTip("Скорость воспроизведения ([ ])")
        self.speed_btn.clicked.connect(self.show_speed)
        right.addWidget(self.speed_btn)
        right.addWidget(divider())
        self.mute_btn = IconButton("volume", "Без звука (M)")
        self.mute_btn.clicked.connect(self.toggle_mute)
        self.vol_bar = Slider()
        self.vol_bar.setFixedWidth(104)
        self.vol_bar.moved.connect(lambda f: self.set_volume(round(f * MAX_VOLUME)))
        self.vol_bar.released.connect(lambda f: self.set_volume(round(f * MAX_VOLUME)))
        self.vol_lbl = label(f"{start_volume}%", 12, FG2)
        self.vol_lbl.setFixedWidth(44)
        self.vol_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        right.addWidget(self.mute_btn)
        right.addWidget(self.vol_bar)
        right.addWidget(self.vol_lbl)
        right.addWidget(divider())
        self.menu_btn = IconButton("more", "Меню")
        self.menu_btn.clicked.connect(self.show_menu)
        self.fs_btn = IconButton("fullscreen", "Полный экран (F)")
        self.fs_btn.clicked.connect(self.toggle_fullscreen)
        right.addWidget(self.menu_btn)
        right.addWidget(self.fs_btn)
        grid.addLayout(right, 0, 2)

        self.bar.box.addLayout(grid)

    def _build_start_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addStretch(1)

        self.zone = DropZone()
        self.zone.setFixedSize(680, 360)
        zl = QVBoxLayout(self.zone)
        zl.setAlignment(Qt.AlignCenter)
        zl.setSpacing(0)
        zl.addWidget(IconTile("video"), 0, Qt.AlignHCenter)
        zl.addSpacing(18)
        zl.addWidget(label("Перетащите видео сюда", 22, FG, 600, display=True), 0, Qt.AlignHCenter)
        zl.addSpacing(6)
        zl.addWidget(label("MP4, MKV, MOV, AVI, WEBM, TS, M4V, FLV, WMV", 13, DIM), 0, Qt.AlignHCenter)
        zl.addSpacing(24)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch()
        open_btn = Button("Открыть файл", "primary", weight=600, icon="folder")
        open_btn.clicked.connect(self.ask_open)
        row.addWidget(open_btn)
        row.addWidget(label("или Ctrl+O", 12, DIM))
        row.addStretch()
        zl.addLayout(row)
        v.addWidget(self.zone, 0, Qt.AlignHCenter)

        v.addSpacing(40)
        v.addWidget(caption("Клавиши"), 0, Qt.AlignHCenter)
        v.addSpacing(14)
        keys = QWidget()
        keys.setFixedWidth(680)
        kg = QGridLayout(keys)
        kg.setContentsMargins(0, 0, 0, 0)
        kg.setHorizontalSpacing(32)
        kg.setVerticalSpacing(10)
        shortcuts = [("Пробел", "пауза"), ("← →", "перемотка на 5 с"), ("↑ ↓", "громкость"),
                     ("1 2 3", "дорожка звука"), ("F", "полный экран"), ("[ ]", "скорость")]
        for i, (key, text) in enumerate(shortcuts):
            cell = QHBoxLayout()
            cell.setSpacing(10)
            cell.addWidget(kbd(key))
            cell.addWidget(label(text, 13, FG2))
            cell.addStretch()
            kg.addLayout(cell, i // 3, i % 3)
        v.addWidget(keys, 0, Qt.AlignHCenter)
        v.addStretch(1)

        footer = QFrame()
        footer.setObjectName("footer")
        footer.setFixedHeight(48)
        footer.setStyleSheet(f"#footer {{ border-top: 1px solid {ui.SURFACE}; }}")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 0, 20, 0)
        fl.setSpacing(4)
        fl.addWidget(label(f"{APP_NAME} {__version__}", 12, DIM))
        fl.addStretch()
        for text, fn in (("Сделать плеером по умолчанию", self.open_default_apps),
                         ("Проверить обновления", lambda: self.check_updates(manual=True))):
            b = Button(text, "ghost", height=32, px=12, pad=12, radius=8)
            b.clicked.connect(fn)
            fl.addWidget(b)
        v.addWidget(footer)
        return page

    def resizeEvent(self, e):
        super().resizeEvent(e)
        narrow = self.width() < NARROW_WIDTH
        for w in (self.vol_bar, self.vol_lbl, self.open_btn):
            w.setVisible(not narrow)
        self.zone.setFixedSize(min(680, self.width() - 96), max(240, min(360, self.height() - 330)))
        if self.fullscreen:
            self._place_overlays()

    # ---------- дорожки ----------
    def _rebuild_tracks(self):
        n = len(self.audio_ids)
        self.tracks_box.setVisible(n > 1)
        if n < 2:
            self.fs_track.hide()
            return
        items = [(tid, track_name(i), None, f"Клавиша {i + 1}" if i < 2 else "")
                 for i, tid in enumerate(self.audio_ids)]
        items.append(("both", "Все дорожки", "layers", "Клавиша 3"))
        self.seg.set_items(items)
        self._paint_tracks()

    def _paint_tracks(self):
        self.seg.set_checked(self.audio_mode)
        n = len(self.audio_ids)
        both = self.audio_mode == "both"
        custom = any(self.track_vol[i] != 100 or self.track_mute[i] for i in range(n))
        self.mix_btn.border = "#3A3F4A" if both else SEG_LINE
        self.mix_btn.color = FG if both else DIM
        self.mix_btn.dot = custom
        self.mix_btn.update()
        if n > 1:
            idx = self.audio_ids.index(self.audio_mode) if not both else None
            self.fs_track.setText("Звук: все дорожки" if both else f"Звук: {track_name(idx)}")
            self.fs_track.setVisible(True)
        for i, row in enumerate(self.mix_rows):
            vol = 0 if self.track_mute[i] else self.track_vol[i]
            row["mute"].set_icon("muted" if self.track_mute[i] else "volume")
            row["mute"].color = DIM if self.track_mute[i] else ui.ICON
            row["mute"].setToolTip(("Включить " if self.track_mute[i] else "Заглушить ")
                                   + f"{i + 1} дорожку")
            row["mute"].update()
            row["slider"].fill = BOOST if vol > 100 else ACCENT
            row["slider"].set_fraction(vol / MAX_VOLUME)
            row["slider"].update()
            row["value"].setText(f"{vol}%")
            row["value"].setStyleSheet(f"color: {BOOST if vol > 100 else FG2}; background: transparent;")

    def _on_tracks(self, tracks):
        audio = [t for t in (tracks or []) if t.get("type") == "audio"]
        ids = [t["id"] for t in audio]
        if ids == self.audio_ids:
            return
        self.audio_ids = ids
        while len(self.track_vol) < len(ids):
            self.track_vol.append(100)
        self.track_mute = [False] * len(ids)
        self.audio_mode = "both" if len(ids) > 1 else (ids[0] if ids else None)
        self.graph = ""
        self._apply_audio_mode()
        self._rebuild_tracks()

    def set_audio_mode_by_index(self, i):
        if i < len(self.audio_ids):
            self.set_audio_mode(self.audio_ids[i], toast=True)

    def set_audio_mode(self, mode, toast=False):
        if mode == "both" and len(self.audio_ids) < 2:
            return
        if mode == self.audio_mode:
            self._paint_tracks()
            return
        self.audio_mode = mode
        self._apply_audio_mode()
        self._paint_tracks()
        if toast:
            self._toast("Звук: все дорожки" if mode == "both"
                        else f"Звук: {track_name(self.audio_ids.index(mode))}")

    def _apply_audio_mode(self):
        if not self.audio_ids:
            return
        if self.audio_mode == "both":
            # каждая дорожка через свой фильтр громкости, затем смешиваем
            parts, mixed = [], ""
            for i, tid in enumerate(self.audio_ids):
                v = 0 if self.track_mute[i] else self.track_vol[i]
                parts.append(f"[aid{tid}]volume={v / 100:.2f}[a{i}]")
                mixed += f"[a{i}]"
            graph = ";".join(parts) + f";{mixed}amix=inputs={len(self.audio_ids)}:normalize=0[ao]"
            if graph != self.graph:
                self.mpv.lavfi_complex = graph
                self.graph = graph
        else:
            if self.graph:
                self.mpv.lavfi_complex = ""
                self.graph = ""
            self.mpv.aid = self.audio_mode

    def set_track_volume(self, i, v, final):
        self.track_vol[i] = max(0, min(MAX_VOLUME, v))
        self.track_mute[i] = False
        self._paint_tracks()
        if final:
            self.mix_timer.stop()
            self._apply_audio_mode()
        else:
            self.mix_timer.start()  # пока тянем ползунок — не чаще раза в 150 мс

    def toggle_track_mute(self, i):
        self.track_mute[i] = not self.track_mute[i]
        self._paint_tracks()
        self._apply_audio_mode()

    def reset_mix(self):
        for i in range(len(self.audio_ids)):
            self.track_vol[i] = 100
            self.track_mute[i] = False
        self._paint_tracks()
        self._apply_audio_mode()

    # ---------- всплывающие окна ----------
    def show_speed(self):
        pop = self.speed_pop
        if pop.just_closed():
            return
        pop.clear()
        head = caption("Скорость")
        head.setContentsMargins(10, 6, 10, 8)
        pop.body.addWidget(head)
        for i, s in enumerate(SPEEDS):
            item = MenuItem("Обычная" if s == 1 else fmt_speed(s), height=34, checked=i == self.speed_index)
            item.clicked.connect(lambda checked=False, i=i: (pop.hide(), self.set_speed_index(i)))
            pop.body.addWidget(item)
        foot = label("[ ] — шаг, Backspace — 1×", 11, DIM)
        foot.setContentsMargins(10, 8, 10, 4)
        pop.body.addWidget(foot)
        pop.show_above(self.speed_btn, "right", gap=10)

    def show_menu(self):
        pop = self.menu_pop
        if pop.just_closed():
            return
        pop.clear()
        entries = [
            ("Открыть видео…", "folder", "Ctrl+O", self.ask_open),
            None,
            ("Сделать PTW плеером по умолчанию", "star", "", self.open_default_apps),
            ("Проверить обновления", "refresh", "", lambda: self.check_updates(manual=True)),
            None,
            ("О программе", "info", __version__, self.show_about),
        ]
        for entry in entries:
            if entry is None:
                pop.body.addWidget(separator())
                continue
            text, icon, right, fn = entry
            item = MenuItem(text, icon, right)
            item.clicked.connect(lambda checked=False, fn=fn: (pop.hide(), QTimer.singleShot(0, fn)))
            pop.body.addWidget(item)
        pop.show_above(self.menu_btn, "right", gap=8)

    def show_mixer(self):
        pop = self.mix_pop
        if pop.just_closed() or len(self.audio_ids) < 2:
            return
        if self.audio_mode != "both":
            self.set_audio_mode("both", toast=True)
        pop.clear()
        inner = QVBoxLayout()
        inner.setContentsMargins(10, 6, 10, 8)
        inner.setSpacing(10)
        head = QHBoxLayout()
        head.addWidget(caption("Громкость дорожек"))
        head.addStretch()
        reset = Button("Сбросить", "ghost", height=28, px=12, pad=8, radius=6)
        reset.clicked.connect(self.reset_mix)
        head.addWidget(reset)
        inner.addLayout(head)
        self.mix_rows = []
        for i in range(len(self.audio_ids)):
            row = QHBoxLayout()
            row.setSpacing(10)
            mute = IconButton("volume", "", size=36, icon_size=18)
            mute.clicked.connect(lambda checked=False, i=i: self.toggle_track_mute(i))
            name = label(track_name(i), 13, FG)
            name.setFixedWidth(74)
            slider = Slider()
            slider.moved.connect(lambda f, i=i: self.set_track_volume(i, round(f * MAX_VOLUME), final=False))
            slider.released.connect(lambda f, i=i: self.set_track_volume(i, round(f * MAX_VOLUME), final=True))
            value = label("100%", 12, FG2)
            value.setFixedWidth(40)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for w in (mute, name):
                row.addWidget(w)
            row.addWidget(slider, 1)
            row.addWidget(value)
            inner.addLayout(row)
            self.mix_rows.append({"mute": mute, "slider": slider, "value": value})
        inner.addWidget(label("Общая громкость — справа на панели", 11, DIM))
        pop.body.addLayout(inner)
        self._paint_tracks()
        pop.show_above(self.mix_btn, "center", gap=10)

    def _popup_open(self):
        return any(p.isVisible() for p in (self.speed_pop, self.menu_pop, self.mix_pop))

    def _toast(self, text):
        area = self.video if self.loaded else self.stack
        self.toast.show_text(text, area)

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
            "3": lambda: self.set_audio_mode("both", toast=True),
            "[": lambda: self.change_speed(-1),
            "]": lambda: self.change_speed(1),
            "BS": self.reset_speed,
            "Ctrl+o": self.ask_open,
        }
        repeating = {"LEFT", "RIGHT", "UP", "DOWN"}
        for key, fn in keys.items():
            self.mpv.on_key_press(key, repetition=key in repeating)(
                lambda fn=fn: self.events.put(("call", fn)))

    def keyPressEvent(self, e):
        k, vk = e.key(), e.nativeVirtualKey()
        if e.modifiers() & Qt.ControlModifier:
            if vk == 0x4F:  # O в любой раскладке
                self.ask_open()
            return
        table = {
            Qt.Key_Space: self.toggle_pause,
            Qt.Key_Left: lambda: self.seek_relative(-SEEK_STEP),
            Qt.Key_Right: lambda: self.seek_relative(SEEK_STEP),
            Qt.Key_Up: lambda: self.change_volume(VOLUME_STEP),
            Qt.Key_Down: lambda: self.change_volume(-VOLUME_STEP),
            Qt.Key_Escape: self.exit_fullscreen,
            Qt.Key_Return: self.toggle_fullscreen,
            Qt.Key_Enter: self.toggle_fullscreen,
            Qt.Key_Backspace: self.reset_speed,
            Qt.Key_1: lambda: self.set_audio_mode_by_index(0),
            Qt.Key_2: lambda: self.set_audio_mode_by_index(1),
            Qt.Key_3: lambda: self.set_audio_mode("both", toast=True),
        }
        # буквы — по коду клавиши, чтобы работали и в русской раскладке
        by_vk = {0x46: self.toggle_fullscreen, 0x4D: self.toggle_mute,
                 0xDB: lambda: self.change_speed(-1), 0xDD: lambda: self.change_speed(1)}
        fn = table.get(k) or by_vk.get(vk)
        if fn:
            fn()
        else:
            super().keyPressEvent(e)

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        if dy:
            self.change_volume(VOLUME_STEP if dy > 0 else -VOLUME_STEP)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.zone.highlight = True
            self.zone.update()

    def dragLeaveEvent(self, e):
        self.zone.highlight = False
        self.zone.update()

    def dropEvent(self, e):
        self.zone.highlight = False
        self.zone.update()
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self.open(files[0])

    # ---------- действия ----------
    def ask_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть видео", self.settings.get("last_dir") or os.path.expanduser("~\\Videos"),
            f"Видео ({VIDEO_EXT});;Все файлы (*.*)")
        if path:
            self.open(path)

    def open(self, path):
        if not os.path.isfile(path):
            self._message(QMessageBox.Critical, APP_NAME, f"Файл не найден:\n{path}")
            return
        path = os.path.abspath(path)
        self.settings["last_dir"] = os.path.dirname(path)
        self.stack.setCurrentWidget(self.video)
        self.bar.show()
        self.loaded = True
        self.audio_ids = []
        self.audio_mode = "both"
        self.tracks_box.hide()
        self.mpv.lavfi_complex = ""
        self.graph = ""
        self.mpv.play(path)
        self.mpv.pause = False
        name = os.path.basename(path)
        self.setWindowTitle(f"{name} — {APP_NAME}")
        fm = QFontMetrics(self.fs_name.font())
        self.fs_name.setText(fm.elidedText(name, Qt.ElideMiddle, 600))

    def toggle_pause(self):
        if not self.loaded:
            self.ask_open()
            return
        self.mpv.pause = not self.mpv.pause

    def seek_relative(self, sec):
        if not self.loaded:
            return
        try:
            self.mpv.seek(sec, "relative+exact")
        except SystemError:
            pass
        self._toast(f"+ {sec} с" if sec > 0 else f"− {-sec} с")

    def seek_to(self, fraction, final):
        if not self.duration:
            return
        target = fraction * self.duration
        self.cur_lbl.setText(fmt_time(target))
        try:
            self.mpv.seek(target, "absolute+exact" if final else "absolute+keyframes")
        except SystemError:
            pass

    def set_volume(self, v, toast=False):
        v = max(0, min(MAX_VOLUME, v))
        self.mpv.volume = v
        if self.mpv.mute and v > 0:
            self.mpv.mute = False
        self._set_volume_ui(v)
        if toast:
            self._toast(f"Громкость {v}%")

    def _set_volume_ui(self, v):
        muted = bool(self.mpv.mute)
        shown = 0 if muted else v
        boost = shown > 100
        self.vol_lbl.setText(f"{shown}%")
        self.vol_lbl.setStyleSheet(f"color: {BOOST if boost else FG2}; background: transparent;")
        self.vol_bar.fill = BOOST if boost else FG
        self.vol_bar.set_fraction(shown / MAX_VOLUME)
        self.vol_bar.update()
        self.mute_btn.set_icon("muted" if muted else "volume")
        self.mute_btn.setToolTip("Включить звук (M)" if muted else "Без звука (M)")

    def change_volume(self, delta):
        self.set_volume(int(round(self.mpv.volume or 0)) + delta, toast=True)

    def toggle_mute(self):
        self.mpv.mute = not self.mpv.mute
        self._set_volume_ui(int(round(self.mpv.volume or 0)))
        self._toast("Без звука" if self.mpv.mute else "Звук включён")

    def set_speed_index(self, i, toast=True):
        self.speed_index = max(0, min(len(SPEEDS) - 1, i))
        s = SPEEDS[self.speed_index]
        self.mpv.speed = s
        self.speed_btn.setText(fmt_speed(s))
        self.speed_btn.setFixedWidth(max(52, self.speed_btn.width()))
        self.speed_btn.text_color = ACCENT if s != 1.0 else None
        self.speed_btn.update()
        if toast:
            self._toast(f"Скорость {fmt_speed(s)}")

    def change_speed(self, step):
        self.set_speed_index(self.speed_index + step)

    def reset_speed(self):
        self.set_speed_index(SPEEDS.index(1.0))

    # ---------- полный экран ----------
    def toggle_fullscreen(self):
        for p in (self.speed_pop, self.menu_pop, self.mix_pop):
            p.hide()
        if not self.loaded and not self.fullscreen:
            return
        if not self.fullscreen:
            self.fullscreen = True
            self.was_maximized = self.isMaximized()
            self.layout_main.removeWidget(self.bar)
            self.bar.setParent(self.fs_bottom)
            self.fs_bottom.box.addWidget(self.bar)
            self.bar.set_floating(True)
            self.bar.show()
            self.fs_btn.set_icon("exit_fullscreen")
            self.fs_btn.setToolTip("Выйти из полного экрана (Esc)")
            self.showFullScreen()
            self.raise_()
            self.activateWindow()
            self.last_activity = time.monotonic()
            QTimer.singleShot(50, self._place_overlays)
        else:
            self.fullscreen = False
            self._show_overlays(False)
            self.fs_bottom.box.removeWidget(self.bar)
            self.bar.setParent(self.central)
            self.layout_main.addWidget(self.bar)
            self.bar.set_floating(False)
            self.bar.show()
            self.fs_btn.set_icon("fullscreen")
            self.fs_btn.setToolTip("Полный экран (F)")
            if self.was_maximized:
                self.showMaximized()
            else:
                self.showNormal()

    def exit_fullscreen(self):
        if self.fullscreen:
            self.toggle_fullscreen()

    def _place_overlays(self):
        g = self.geometry()
        h = self.bar.sizeHint().height()
        self.fs_bottom.setGeometry(g.x() + 24, g.y() + g.height() - 24 - h, g.width() - 48, h)
        self.fs_top.setGeometry(g.x() + 24, g.y() + 24, g.width() - 48, 40)

    def _show_overlays(self, show):
        if show == self.fs_visible:
            return
        self.fs_visible = show
        for w in (self.fs_bottom, self.fs_top):
            w.setVisible(show)
        if show:
            self._place_overlays()

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
                    self.paused = bool(val)
                    self.play_btn.set_playing(not self.paused)
        except queue.Empty:
            pass

        try:
            pos = self.mpv.time_pos
            self.duration = self.mpv.duration
        except Exception:
            pos = None
        if self.duration and not self.seek.dragging:
            self.seek.set_fraction((pos or 0) / self.duration)
            self.cur_lbl.setText(fmt_time(pos))
            self.dur_lbl.setText(fmt_time(self.duration))

        # круг «пауза» по центру видео
        show_badge = self.loaded and self.paused and not self.isMinimized() and self.isVisible()
        if show_badge:
            self.badge.place(self.video)
        if show_badge != self.badge.isVisible():
            self.badge.setVisible(show_badge)

        # в полном экране панель видна, пока двигается мышь, и прячется через пару секунд
        if self.fullscreen:
            cur = QCursor.pos()
            if cur != self.last_cursor:
                self.last_cursor = cur
                self.last_activity = time.monotonic()
            over_bar = self.fs_visible and self.fs_bottom.geometry().contains(cur)
            self._show_overlays(over_bar or self.paused or self._popup_open()
                                or time.monotonic() - self.last_activity < FS_HIDE_AFTER)

    # ---------- меню ----------
    def _message(self, icon, title, text):
        box = QMessageBox(icon, title, text, QMessageBox.Ok, self)
        ui.dark_titlebar(box)
        box.exec()

    def open_default_apps(self):
        self._message(
            QMessageBox.Information, APP_NAME,
            "Сейчас откроются «Приложения по умолчанию» Windows.\n\n"
            "Выберите там нужные форматы (.mp4, .mkv и т. д.) и укажите PTW.\n"
            "Ещё способ: правый клик по видео → «Открыть с помощью» → PTW → «Всегда».")
        try:
            os.startfile("ms-settings:defaultapps?registeredAppUser=PTW")
        except OSError:
            os.startfile("ms-settings:defaultapps")

    def show_about(self):
        self._message(
            QMessageBox.Information, f"О программе {APP_NAME}",
            f"{APP_NAME} {__version__}\n\n"
            "Видеоплеер с выбором аудиодорожек: можно слушать одну дорожку\n"
            "или все сразу и настроить громкость каждой.\n\n"
            "Движок воспроизведения — mpv (mpv.io).")

    # ---------- обновления ----------
    def check_updates(self, manual):
        if not updater.is_configured():
            if manual:
                self._message(QMessageBox.Information, APP_NAME, "Источник обновлений ещё не настроен.")
            return

        def work():
            try:
                info = updater.check()
            except Exception as e:  # сеть, GitHub недоступен и т. п.
                if manual:
                    self.events.put(("call", lambda: self._message(
                        QMessageBox.Warning, APP_NAME, f"Не удалось проверить обновления:\n{e}")))
                return
            self.events.put(("call", lambda: self._on_update_checked(info, manual)))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, info, manual):
        if info is None:
            if manual:
                self._message(QMessageBox.Information, APP_NAME, f"У вас последняя версия ({__version__}).")
            return
        if not manual and self.settings.get("skipped_version") == info.version:
            return
        self._show_update_dialog(info)

    def _show_update_dialog(self, info):
        if self.update_window is not None:
            return
        dlg = self.update_window = UpdateDialog(self, info)
        dlg.update_btn.clicked.connect(lambda: self._start_update(info))
        dlg.later_btn.clicked.connect(self._close_update_dialog)
        dlg.skip_btn.clicked.connect(lambda: self._skip_version(info))
        dlg.rejected.connect(self._close_update_dialog)
        dlg.show()

    def _close_update_dialog(self):
        if self.update_window is not None:
            dlg, self.update_window = self.update_window, None
            dlg.close()
            dlg.deleteLater()

    def _skip_version(self, info):
        self.settings["skipped_version"] = info.version
        save_settings(self.settings)
        self._close_update_dialog()

    def _start_update(self, info):
        dlg = self.update_window
        dlg.start_progress()

        def progress(f):
            self.events.put(("call", lambda: self.update_window and self.update_window.set_progress(f)))

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
        self._message(QMessageBox.Critical, APP_NAME, f"Не удалось скачать обновление:\n{error}")

    def _install_update(self, path):
        if self.update_window:
            self.update_window.set_status("Установка… PTW перезапустится сам.")
        QApplication.processEvents()
        updater.run_installer(path)
        self.close()

    def closeEvent(self, e):
        self.settings["volume"] = int(round(self.mpv.volume or 0))
        self.settings["track_volumes"] = self.track_vol[:8]
        save_settings(self.settings)
        self.timer.stop()
        for w in (self.toast, self.badge, self.fs_bottom, self.fs_top):
            w.hide()
        try:
            self.mpv.terminate()
        finally:
            e.accept()
            QApplication.quit()


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in ((QPalette.Window, BAR), (QPalette.WindowText, FG), (QPalette.Base, ui.SEG_BG),
                        (QPalette.Text, FG), (QPalette.Button, ui.SURFACE), (QPalette.ButtonText, FG),
                        (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, ui.ON_ACCENT),
                        (QPalette.ToolTipBase, ui.SURFACE), (QPalette.ToolTipText, FG)):
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(ui.APP_STYLE)
    app.setFont(ui.font(13))
    app.setWindowIcon(QIcon(os.path.join(RES_DIR, "ptw.ico")))
    window = Player(sys.argv[1] if len(sys.argv) > 1 else None)  # noqa: F841
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
