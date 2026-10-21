"""Элементы интерфейса PTW: цвета, иконки, кнопки, ползунки, всплывающие окна.

Всё рисуется вручную через QPainter со сглаживанием — так интерфейс выглядит
одинаково на любой теме Windows.
"""
import ctypes
import time

from PySide6.QtCore import QByteArray, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QVBoxLayout, QWidget)

# ---------- цвета ----------
BG = "#0B0C0F"          # окно
BAR = "#15171C"         # панель управления
LINE = "#23262E"        # граница панели
SURFACE = "#1C1F26"     # всплывающие окна
SURFACE_LINE = "#2E323C"
SEG_BG = "#0E0F13"      # подложка переключателя дорожек
SEG_LINE = "#262A33"
DIVIDER = "#2A2E37"
FG = "#ECEDF0"
FG2 = "#C9CDD4"
ICON = "#DADDE3"
DIM = "#9AA0AB"
TRACK = "#343843"       # пустая часть ползунка
ACCENT = "#5B95FF"
ACCENT_SOFT = "#8FB4FF"
BOOST = "#F2A65A"       # громкость выше 100%
ON_ACCENT = "#0B0C0F"


def rgba(hex_color, alpha):
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


def font(px, weight=400, display=False):
    f = QFont()
    f.setFamilies(["Segoe UI Variable Display" if display else "Segoe UI Variable Text", "Segoe UI"])
    f.setPixelSize(px)
    f.setWeight(QFont.Weight(weight))
    return f


def label(text, px=13, color=FG, weight=400, display=False):
    lbl = QLabel(text)
    lbl.setFont(font(px, weight, display))
    lbl.setStyleSheet(f"color: {color}; background: transparent;")
    return lbl


def caption(text):
    """Мелкий заголовок капсом: «СКОРОСТЬ», «КЛАВИШИ»."""
    lbl = label(text.upper(), 11, DIM, 600)
    f = lbl.font()
    f.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    lbl.setFont(f)
    return lbl


def dark_titlebar(widget):
    """Тёмный заголовок окна Windows 10/11 в цвет фона."""
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), 4)  # DWMWA_USE_IMMERSIVE_DARK_MODE
        caption_color = ctypes.c_int(0x000F0C0B)                  # BG в формате 0x00BBGGRR
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), 4)
    except Exception:
        pass


# ---------- иконки (те же, что в макете; viewBox 24×24) ----------
ICONS = {
    "play": '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none"/>',
    "pause": '<rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none"/>'
             '<rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none"/>',
    "back5": '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3.5 4v4.2h4.2"/>'
             '<text x="12" y="15.6" text-anchor="middle" font-size="8.5" font-weight="600" '
             'fill="currentColor" stroke="none" font-family="Segoe UI">5</text>',
    "fwd5": '<path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1"/><path d="M20.5 4v4.2h-4.2"/>'
            '<text x="12" y="15.6" text-anchor="middle" font-size="8.5" font-weight="600" '
            'fill="currentColor" stroke="none" font-family="Segoe UI">5</text>',
    "folder": '<path d="M3 7.5A2 2 0 0 1 5 5.5h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "volume": '<path d="M4 9.5h3l5-4v13l-5-4H4z"/><path d="M16 9.5a3.5 3.5 0 0 1 0 5"/>'
              '<path d="M18.5 7a7 7 0 0 1 0 10"/>',
    "muted": '<path d="M4 9.5h3l5-4v13l-5-4H4z"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>',
    "layers": '<path d="M12 3.5l8.5 4.5-8.5 4.5L3.5 8z"/><path d="M3.5 12.5l8.5 4.5 8.5-4.5"/>',
    "mixer": '<path d="M4 7.5h9M18 7.5h2M4 16.5h3M11 16.5h9"/><circle cx="15.5" cy="7.5" r="2.3"/>'
             '<circle cx="8.5" cy="16.5" r="2.3"/>',
    "fullscreen": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "exit_fullscreen": '<path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/>',
    "more": '<circle cx="5.5" cy="12" r="1.7" fill="currentColor" stroke="none"/>'
            '<circle cx="12" cy="12" r="1.7" fill="currentColor" stroke="none"/>'
            '<circle cx="18.5" cy="12" r="1.7" fill="currentColor" stroke="none"/>',
    "star": '<path d="M12 3.5l2.5 5.2 5.7.8-4.1 4 1 5.6-5.1-2.7-5.1 2.7 1-5.6-4.1-4 5.7-.8z"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 4v4.5h-4.5"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5"/><path d="M12 7.6v.1"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "video": '<rect x="3" y="5" width="18" height="14" rx="2.5"/>'
             '<path d="M10 9.5v5l4.2-2.5z" fill="currentColor"/>',
    "download": '<path d="M12 4v11"/><path d="M7.5 10.5L12 15l4.5-4.5"/><path d="M5 19.5h14"/>',
}
STROKE = {"check": 2.2, "folder": 1.7, "back5": 1.7, "fwd5": 1.7, "star": 1.7, "refresh": 1.7,
          "info": 1.7, "video": 1.6}
_icon_cache = {}


def icon_pixmap(name, color, size, dpr=1.0):
    key = (name, color, size, dpr)
    pm = _icon_cache.get(key)
    if pm is None:
        body = ICONS[name].replace("currentColor", color)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
               f'stroke-width="{STROKE.get(name, 1.8)}" stroke-linecap="round" stroke-linejoin="round">'
               f'{body}</svg>')
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        pm = QPixmap(round(size * dpr), round(size * dpr))
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p)
        p.end()
        pm.setDevicePixelRatio(dpr)
        _icon_cache[key] = pm
    return pm


def draw_icon(p, widget, name, color, size, center):
    pm = icon_pixmap(name, color, size, widget.devicePixelRatioF())
    p.drawPixmap(round(center.x() - size / 2), round(center.y() - size / 2), pm)


class _Button(QAbstractButton):
    """Основа кнопок: без фокуса клавиатуры (пробел — это пауза), курсор-рука, подсветка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)

    @property
    def hot(self):
        return self.underMouse() or self.isDown()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class IconButton(_Button):
    def __init__(self, icon, tip="", size=40, icon_size=20, radius=10, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.icon_name = icon
        self.icon_size = icon_size
        self.radius = radius
        self.color = ICON
        self.border = None
        self.dot = False
        self.setToolTip(tip)

    def set_icon(self, name):
        if name != self.icon_name:
            self.icon_name = name
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(self.border), 1) if self.border else Qt.NoPen)
        p.setBrush(rgba("#FFFFFF", 20) if self.hot else Qt.NoBrush)
        if self.border or self.hot:
            p.drawRoundedRect(r, self.radius, self.radius)
        draw_icon(p, self, self.icon_name, "#FFFFFF" if self.hot else self.color, self.icon_size, r.center())
        if self.dot:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawEllipse(QRectF(self.width() - 14, 7, 7, 7))


class PlayButton(_Button):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 44)
        self.playing = False

    def set_playing(self, playing):
        self.playing = playing
        self.setToolTip("Пауза (пробел)" if playing else "Воспроизвести (пробел)")
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#E4E7EC" if self.hot else "#FFFFFF"))
        p.drawEllipse(QRectF(self.rect()))
        draw_icon(p, self, "pause" if self.playing else "play", ON_ACCENT, 18, QRectF(self.rect()).center())


class Button(_Button):
    """Кнопка с текстом. kind: primary — акцентная, outline — с рамкой, ghost — без фона."""

    def __init__(self, text, kind="ghost", height=40, px=14, weight=500, pad=18, radius=10,
                 icon=None, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.kind = kind
        self.radius = radius
        self.pad = pad
        self.icon_name = icon
        self.text_color = None
        self.setFont(font(px, weight))
        self.setFixedHeight(height)
        self._resize()

    def setText(self, text):
        super().setText(text)
        if hasattr(self, "pad"):
            self._resize()

    def _resize(self):
        w = QFontMetrics(self.font()).horizontalAdvance(self.text()) + self.pad * 2
        if self.icon_name:
            w += 28
        self.setFixedWidth(max(w, self.height()))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.kind == "primary":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#6FA3FF" if self.hot else ACCENT))
            color = ON_ACCENT
        elif self.kind == "outline":
            p.setPen(QPen(QColor(SURFACE_LINE), 1))
            p.setBrush(rgba("#FFFFFF", 16) if self.hot else Qt.NoBrush)
            color = "#FFFFFF" if self.hot else ICON
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(rgba("#FFFFFF", 16) if self.hot else Qt.NoBrush)
            color = "#FFFFFF" if self.hot else FG2
        if self.text_color:
            color = self.text_color
        p.drawRoundedRect(r, self.radius, self.radius)
        p.setPen(QColor(color))
        p.setFont(self.font())
        if self.icon_name:
            tw = QFontMetrics(self.font()).horizontalAdvance(self.text())
            x = (self.width() - tw - 28) / 2
            draw_icon(p, self, self.icon_name, color, 18, QPoint(round(x + 9), self.height() // 2))
            p.drawText(QRectF(x + 28, 0, tw + 2, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        else:
            p.drawText(r, Qt.AlignCenter, self.text())


class SegButton(_Button):
    def __init__(self, text, icon=None, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.icon_name = icon
        self.setFont(font(13, 500))
        w = QFontMetrics(self.font()).horizontalAdvance(text) + 28 + (26 if icon else 0)
        self.setFixedSize(w, 36)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(QRectF(self.rect()), 9, 9)
            color = ON_ACCENT
        else:
            color = "#FFFFFF" if self.hot else FG2
        p.setPen(QColor(color))
        p.setFont(self.font())
        x = 14
        if self.icon_name:
            draw_icon(p, self, self.icon_name, color, 18, QPoint(x + 9, 18))
            x += 26
        p.drawText(QRectF(x, 0, self.width() - x, 36), Qt.AlignVCenter | Qt.AlignLeft, self.text())


class Segmented(QWidget):
    """Переключатель дорожек: «1 дорожка | 2 дорожка | Все дорожки»."""
    picked = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(5, 5, 5, 5)
        self.box.setSpacing(2)
        self.buttons = {}

    def set_items(self, items):
        """items: [(ключ, текст, иконка или None, подсказка)]"""
        for b in self.buttons.values():
            b.deleteLater()
        self.buttons = {}
        for key, text, icon, tip in items:
            b = SegButton(text, icon)
            b.setToolTip(tip)
            b.clicked.connect(lambda checked=False, k=key: self.picked.emit(k))
            self.box.addWidget(b)
            self.buttons[key] = b

    def set_checked(self, key):
        for k, b in self.buttons.items():
            b.setChecked(k == key)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(SEG_LINE), 1))
        p.setBrush(QColor(SEG_BG))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)


class Slider(QWidget):
    """Тонкий ползунок: перемотка, громкость. Значение — доля 0…1."""
    moved = Signal(float)
    released = Signal(float)

    def __init__(self, grow=False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        self.grow = grow          # полоса перемотки утолщается под мышью
        self.fraction = 0.0
        self.fill = ACCENT
        self.dragging = False

    def set_fraction(self, f):
        if not self.dragging:
            f = min(max(f, 0.0), 1.0)
            if abs(f - self.fraction) > 1e-4:
                self.fraction = f
                self.update()

    def _frac_at(self, x):
        w = max(self.width() - 14, 1)
        return min(max((x - 7) / w, 0.0), 1.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.dragging = True
            self.fraction = self._frac_at(e.position().x())
            self.update()
            self.moved.emit(self.fraction)

    def mouseMoveEvent(self, e):
        if self.dragging:
            self.fraction = self._frac_at(e.position().x())
            self.update()
            self.moved.emit(self.fraction)

    def mouseReleaseEvent(self, e):
        if self.dragging:
            self.dragging = False
            self.fraction = self._frac_at(e.position().x())
            self.update()
            self.released.emit(self.fraction)

    def enterEvent(self, e):
        self.update()

    def leaveEvent(self, e):
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        thick = 6 if self.grow and (self.underMouse() or self.dragging) else 4
        mid = self.height() / 2
        left, width = 7, self.width() - 14
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(TRACK))
        p.drawRoundedRect(QRectF(left, mid - thick / 2, width, thick), thick / 2, thick / 2)
        x = left + width * self.fraction
        p.setBrush(QColor(self.fill))
        p.drawRoundedRect(QRectF(left, mid - thick / 2, x - left, thick), thick / 2, thick / 2)
        p.setBrush(rgba("#000000", 90))
        p.drawEllipse(QRectF(x - 7.5, mid - 6.5, 15, 15))
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x - 7, mid - 7, 14, 14))


class ProgressLine(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self.fraction = 0.0

    def set_fraction(self, f):
        self.fraction = f
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(DIVIDER))
        p.drawRoundedRect(QRectF(self.rect()), 2, 2)
        p.setBrush(QColor(ACCENT))
        p.drawRoundedRect(QRectF(0, 0, self.width() * self.fraction, 4), 2, 2)


def divider():
    d = QFrame()
    d.setFixedSize(17, 22)
    d.setStyleSheet(f"background: transparent; border: 0; border-left: 1px solid {DIVIDER}; margin-left: 8px;")
    return d


def separator():
    d = QFrame()
    d.setFixedHeight(13)
    d.setStyleSheet(f"background: transparent; border: 0; border-top: 1px solid {DIVIDER}; margin: 6px 4px 0 4px;")
    return d


# ---------- всплывающие окна ----------
class Popup(QWidget):
    """Всплывающее окно над кнопкой: тёмная карточка со скруглением и тенью."""
    SHADOW = 22

    def __init__(self, parent, width):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.closed_at = 0.0
        outer = QVBoxLayout(self)
        m = self.SHADOW
        outer.setContentsMargins(m, m, m, m)
        self.panel = QFrame()
        self.panel.setObjectName("panel")
        self.panel.setFixedWidth(width)
        self.panel.setStyleSheet(f"#panel {{ background: {SURFACE}; border: 1px solid {SURFACE_LINE};"
                                 f" border-radius: 12px; }}")
        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 12)
        shadow.setColor(rgba("#000000", 150))
        self.panel.setGraphicsEffect(shadow)
        outer.addWidget(self.panel)
        self.body = QVBoxLayout(self.panel)
        self.body.setContentsMargins(6, 6, 6, 6)
        self.body.setSpacing(0)

    def clear(self):
        while self.body.count():
            item = self.body.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _delete_layout(item.layout())

    def just_closed(self):
        """Клик по кнопке, которая открыла окно, сначала закрывает его — не открываем снова."""
        return time.monotonic() - self.closed_at < 0.25

    def hideEvent(self, e):
        self.closed_at = time.monotonic()
        super().hideEvent(e)

    def show_above(self, anchor, align="right", gap=6):
        self.adjustSize()
        m = self.SHADOW
        a = anchor.mapToGlobal(QPoint(0, 0))
        if align == "right":
            x = a.x() + anchor.width() - self.width() + m
        else:
            x = a.x() + anchor.width() // 2 - self.width() // 2
        y = a.y() - self.height() + m - gap
        screen = (anchor.screen() or QApplication.primaryScreen()).availableGeometry()
        x = max(screen.left() - m, min(x, screen.right() - self.width() + m))
        y = max(screen.top() - m, y)
        self.move(x, y)
        self.show()


def _delete_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _delete_layout(item.layout())
    layout.deleteLater()


class MenuItem(_Button):
    def __init__(self, text, icon=None, right="", height=38, checked=False, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.icon_name = icon
        self.right = right
        self.checked = checked
        self.setFixedHeight(height)
        self.setFont(font(13, 600 if checked else 400))

    def sizeHint(self):
        return QSize(100, self.height())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.hot:
            p.setPen(Qt.NoPen)
            p.setBrush(rgba("#FFFFFF", 16))
            p.drawRoundedRect(QRectF(self.rect()), 8, 8)
        color = ACCENT if self.checked else FG
        x = 12
        if self.icon_name:
            draw_icon(p, self, self.icon_name, color, 18, QPoint(x + 9, self.height() // 2))
            x += 30
        p.setFont(self.font())
        p.setPen(QColor(color))
        p.drawText(QRectF(x, 0, self.width() - x - 12, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
        if self.right:
            p.setFont(font(12))
            p.setPen(QColor(DIM))
            p.drawText(QRectF(0, 0, self.width() - 12, self.height()), Qt.AlignVCenter | Qt.AlignRight, self.right)
        if self.checked:
            draw_icon(p, self, "check", ACCENT, 16, QPoint(self.width() - 20, self.height() // 2))


class Toast(QWidget):
    """Плашка поверх видео: «Звук: все дорожки», «Скорость 1,5×»."""

    def __init__(self, parent):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowTransparentForInput
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.text = ""
        self.setFont(font(13, 500))
        self.timer = QTimer(self, singleShot=True, interval=1600, timeout=self.hide)

    def show_text(self, text, area):
        """area — виджет видео, над верхним краем которого появляется плашка."""
        self.text = text
        w = QFontMetrics(self.font()).horizontalAdvance(text) + 50
        self.setFixedSize(w, 40)
        top = area.mapToGlobal(QPoint(area.width() // 2, 20))
        self.move(top.x() - w // 2, top.y())
        self.update()
        self.show()
        self.raise_()
        self.timer.start()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(rgba(BG, 225))
        p.drawRoundedRect(QRectF(self.rect()), 20, 20)
        p.setBrush(QColor(ACCENT))
        p.drawEllipse(QRectF(16, 16, 8, 8))
        p.setPen(QColor(FG))
        p.setFont(self.font())
        p.drawText(QRectF(34, 0, self.width() - 34, 40), Qt.AlignVCenter | Qt.AlignLeft, self.text)


class PauseBadge(QWidget):
    """Круг с треугольником по центру видео, пока стоит пауза. Клики проходят насквозь в mpv."""

    def __init__(self, parent):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowTransparentForInput
                         | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(76, 76)

    def place(self, area):
        c = area.mapToGlobal(QPoint(area.width() // 2, area.height() // 2))
        pos = QPoint(c.x() - 38, c.y() - 38)
        if pos != self.pos():
            self.move(pos)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(rgba(BG, 180))
        p.drawEllipse(QRectF(self.rect()))
        draw_icon(p, self, "play", "#FFFFFF", 30, QPoint(39, 38))


class Overlay(QWidget):
    """Прозрачное окно поверх видео в полноэкранном режиме (панель управления, верхняя плашка)."""

    def __init__(self, parent):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(8)


def pill(text, color=FG, px=13, weight=500):
    """Плашка на тёмной подложке для верхней строки полноэкранного режима."""
    lbl = QLabel(text)
    lbl.setFont(font(px, weight))
    lbl.setFixedHeight(40)
    lbl.setStyleSheet(f"color: {color}; background: rgba(11, 12, 15, 217); border-radius: 12px; padding: 0 16px;")
    return lbl


class DropZone(QWidget):
    """Пунктирная рамка «Перетащите видео сюда» на стартовом экране."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlight = False

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(ACCENT if self.highlight else TRACK), 1.5)
        pen.setStyle(Qt.CustomDashLine)
        pen.setDashPattern([4, 3])
        p.setPen(pen)
        p.setBrush(QColor("#13171F" if self.highlight else "#101216"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 20, 20)


class IconTile(QWidget):
    """Иконка на мягкой акцентной подложке (стартовый экран, окно обновления)."""

    def __init__(self, icon, size=64, icon_size=30, radius=18, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.icon_name, self.icon_size, self.radius = icon, icon_size, radius

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(rgba(ACCENT, 31))
        p.drawRoundedRect(QRectF(self.rect()), self.radius, self.radius)
        draw_icon(p, self, self.icon_name, ACCENT_SOFT, self.icon_size, QRectF(self.rect()).center())


def kbd(text):
    lbl = QLabel(text)
    lbl.setFont(font(12, 600))
    lbl.setFixedHeight(24)
    lbl.setStyleSheet(f"color: {FG}; background: {SURFACE}; border: 1px solid {SURFACE_LINE};"
                      f" border-radius: 6px; padding: 0 7px;")
    return lbl


APP_STYLE = f"""
QToolTip {{ background: {SURFACE}; color: {FG}; border: 1px solid {SURFACE_LINE}; padding: 5px 8px;
            border-radius: 6px; font-size: 12px; }}
QMessageBox, QDialog {{ background: {BAR}; }}
QMessageBox QLabel {{ color: {FG}; font-size: 13px; }}
QMessageBox QPushButton {{ background: {ACCENT}; color: {ON_ACCENT}; border: 0; border-radius: 8px;
                          padding: 8px 18px; font-size: 13px; font-weight: 600; min-width: 72px; }}
QMessageBox QPushButton:hover {{ background: #6FA3FF; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {TRACK}; border-radius: 3px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
"""
