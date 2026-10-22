"""Плавающие окошки: плашка записи, «распознаю…», карточка результата.

Все окошки — frameless, поверх всего, НИКОГДА не забирают фокус: вставка
должна уйти в то приложение, где стоит курсор.
"""
from __future__ import annotations

import logging
import math
import os
import time

from PyQt6.QtCore import (
    QEasingCurve, QPointF, QRectF, QTimer, QVariantAnimation, Qt, pyqtSignal,
)
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from config import CARD_LINGER_SEC, FADE_MSEC, MAX_RECORD_SEC

# --- палитра ----------------------------------------------------------------
BG = QColor(20, 20, 25, 242)
BG_HOVER = QColor(40, 40, 50, 250)
BORDER = QColor(255, 255, 255, 28)
TEXT = QColor(245, 245, 247)
MUTED = QColor(142, 142, 152)    # #8e8e98 — второстепенный текст
ACCENT = QColor(255, 122, 89)    # коралл
ACCENT2 = QColor(255, 184, 107)  # янтарь
GREEN = QColor(74, 222, 128)
RED = QColor(255, 96, 92)

CARD_W = 336   # единая ширина ВСЕХ состояний — семья карточек
CARD_R = 16.0  # единый радиус

MARGIN_RIGHT = 16
MARGIN_BOTTOM = 88  # выше дока


def _ui_font(size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont("SF Pro Text")
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def _mono_font(size: int) -> QFont:
    f = QFont("Menlo")
    f.setPixelSize(size)
    return f


def _make_window(w: QWidget) -> None:
    w.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | Qt.WindowType.WindowStaysOnTopHint
        | Qt.WindowType.Tool
    )
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    # без этого мак прячет Tool-окна, когда приложение не активно
    w.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)


def _apply_topmost(w: QWidget) -> None:
    """Нативно поставить окно выше всех, включая полноэкранные приложения.

    ВАЖНО: вызывать только ПОСЛЕ w.show() — Qt при показе окна сбрасывает
    нативный уровень, заданный заранее (подтверждено гуглением и практикой).
    """
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return  # в offscreen нет нативных окон — там падает и не нужен
    try:
        import objc
        from AppKit import (
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
        )
        view = objc.objc_object(c_void_p=int(w.winId()))  # NSView
        nswin = view.window()                             # NSWindow
        nswin.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        nswin.setLevel_(1000)  # NSScreenSaverWindowLevel — выше фулскрина
        nswin.setOpaque_(False)
        nswin.setHasShadow_(True)
        nswin.orderFrontRegardless()  # показать, даже если приложение не активно
        if not getattr(w, "_top_logged", False):
            logging.getLogger("gigaam").info("topmost ок: %s", type(w).__name__)
            w._top_logged = True
    except Exception as e:
        logging.getLogger("gigaam").warning("topmost НЕ применился: %s", e)


def _anchor_point(widget: QWidget) -> None:
    """Поставить окошко в правый нижний угол того экрана, где курсор."""
    screen = QApplication.primaryScreen()
    cur = QCursor.pos()
    for s in QApplication.screens():
        if s.geometry().contains(cur):
            screen = s
            break
    if screen is None:
        screen = QApplication.primaryScreen()
    g = screen.availableGeometry()
    x = g.right() - widget.width() - MARGIN_RIGHT
    y = g.bottom() - widget.height() - MARGIN_BOTTOM
    widget.move(x, y)


def _fade_in(w: QWidget) -> None:
    w.setWindowOpacity(0.0)
    w.show()
    _apply_topmost(w)                                  # после показа!
    QTimer.singleShot(0, lambda: _apply_topmost(w))    # и ещё раз после sync Qt
    anim = QVariantAnimation(w)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(FADE_MSEC)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.valueChanged.connect(w.setWindowOpacity)
    anim.finished.connect(anim.deleteLater)
    anim.start()


def _fade_out_hide(w: QWidget, msec: int = FADE_MSEC) -> None:
    anim = QVariantAnimation(w)
    anim.setStartValue(w.windowOpacity())
    anim.setEndValue(0.0)
    anim.setDuration(msec)
    anim.setEasingCurve(QEasingCurve.Type.InCubic)
    anim.valueChanged.connect(w.setWindowOpacity)

    def done():
        w.hide()
        w.setWindowOpacity(1.0)

    anim.finished.connect(done)
    anim.start()
    w._fade_anim = anim  # держим ссылку, чтобы анимацию не собрал GC


# --- плашка записи · карточка -----------------------------------------------
def _paint_card(w: QWidget, p: QPainter, hovered: bool = False) -> None:
    """Единый контейнер всех состояний: тёмное стекло, радиус 16, бордер.

    Меняется только содержимое — контейнер один, поэтому за одну диктовку
    интерфейс больше не «скачет» между тремя обликами.
    """
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(_pen(QColor(255, 255, 255, 45 if hovered else BORDER.alpha())))
    p.setBrush(BG_HOVER if hovered else BG)
    p.drawPath(_rounded(w.rect(), CARD_R))


class _PulseDot(QWidget):
    """Пульсирующий кружок. Пульс — непрерывная синусоида от счётчика тиков
    (ничего от микрофона), поэтому дёргаться физически нечему."""

    def __init__(self, color: QColor, *, amber: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._color = color
        self._amber = amber  # стиль «распознавание»: размер постоянный, дышит свечение
        self._phase = 0.0
        # 24 px: свечение уходит на r+4 (до ~11.5) — в 18 px оно обрезалось
        self.setFixedSize(24, 24)

    def set_phase(self, phase: float) -> None:
        self._phase = phase
        self.update()

    def paintEvent(self, a0) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = cy = self.width() / 2.0
        c = self._color
        p.setPen(Qt.PenStyle.NoPen)
        if self._amber:
            glow = 0.55 + 0.45 * abs(math.sin(self._phase * 0.4))
            p.setBrush(QColor(c.red(), c.green(), c.blue(), int(70 * glow)))
            p.drawEllipse(QRectF(cx - 5, cy - 5, 10, 10))
            p.setBrush(c)
            p.drawEllipse(QRectF(cx - 3.2, cy - 3.2, 6.4, 6.4))
        else:
            breathe = 0.5 + 0.5 * math.sin(self._phase)
            r = 5.5 + 1.5 * math.sin(self._phase)  # период ~2.8 c
            # мягкое свечение
            p.setBrush(QColor(c.red(), c.green(), c.blue(), int(45 * breathe) + 15))
            p.drawEllipse(QRectF(cx - r - 4, cy - r - 4, (r + 4) * 2, (r + 4) * 2))
            p.setBrush(c)
            p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))


class RecordingPill(QWidget):
    """ЗАПИСЬ: та же тёмная карточка, что у результата и распознавания.

    Первая строка: красный пульсирующий кружок, таймер, справа чип «⌘R».
    Вторая строка: «Esc — отмена · ⌘R — закончить» внутри карточки — раньше
    подсказка была отдельным полупрозрачным лейблом и сквозь неё просвечивал
    контент под окнами (текст «двоился»).
    """

    def __init__(self) -> None:
        super().__init__()
        _make_window(self)
        self.setFixedWidth(CARD_W)
        self._started = time.monotonic()
        self._phase = 0.0

        self.dot = _PulseDot(RED, parent=self)

        self.timer_lbl = QLabel("0:00", self)
        self.timer_lbl.setFont(_mono_font(13))
        self.timer_lbl.setStyleSheet("color: #f5f5f7; background: transparent;")

        chip = QLabel("⌘R", self)
        chip.setFont(_mono_font(11))
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setStyleSheet(
            "color: #cfcfd6; background: rgba(255,255,255,18);"
            "border: 1px solid rgba(255,255,255,26);"
            "border-radius: 9px;")
        fm = QFontMetrics(_mono_font(11))
        chip.setFixedSize(fm.horizontalAdvance("⌘R") + 18, 20)

        self.hint_lbl = QLabel("Esc — отмена · ⌘R — закончить", self)
        self.hint_lbl.setFont(_ui_font(10))
        self.hint_lbl.setStyleSheet("color: #8e8e98; background: transparent;")

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.dot)
        row.addWidget(self.timer_lbl)
        row.addStretch(1)
        row.addWidget(chip)

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(4)
        v.addLayout(row)
        row2 = QHBoxLayout()
        row2.setSpacing(0)
        row2.addSpacing(self.dot.width() + row.spacing())  # по левому краю таймера
        row2.addWidget(self.hint_lbl)
        row2.addStretch(1)
        v.addLayout(row2)

        self.setFixedHeight(self.sizeHint().height())

        self._tick = QTimer(self)
        self._tick.setInterval(25)  # 40 fps — с запасом для медленного пульса
        self._tick.timeout.connect(self._on_tick)

    def popup(self, level_fn=None) -> None:
        self._started = time.monotonic()
        self.timer_lbl.setText("0:00")
        _anchor_point(self)
        _fade_in(self)
        self._tick.start()

    def hideEvent(self, a0) -> None:
        self._tick.stop()
        super().hideEvent(a0)

    def _on_tick(self) -> None:
        self._phase += 0.056  # 2π / (2.8 c · 40 fps)
        self.dot.set_phase(self._phase)
        m, s = divmod(int(time.monotonic() - self._started), 60)
        text = f"{m}:{s:02d}"
        if text != self.timer_lbl.text():
            self.timer_lbl.setText(text)

    def paintEvent(self, a0) -> None:
        p = QPainter(self)
        _paint_card(self, p)


def _rounded(rect, r: float):
    from PyQt6.QtGui import QPainterPath
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), r, r)
    return path


def _pen(color: QColor):
    from PyQt6.QtGui import QPen
    return QPen(color, 1)


# --- «распознаю…» · та же карточка ----------------------------------------------
class TranscribingPill(QWidget):
    """РАСПОЗНАВАНИЕ: та же тёмная карточка. Слева янтарный пульс,
    «Распознаю… [N/M]» белым, справа таймер Menlo серым — он продолжает
    счёт с начала записи, а не с нуля."""

    def __init__(self) -> None:
        super().__init__()
        _make_window(self)
        self.setFixedWidth(CARD_W)
        self._phase = 0.0
        self._started: float | None = None

        self.dot = _PulseDot(ACCENT2, amber=True, parent=self)

        self.lbl = QLabel("Распознаю…", self)
        self.lbl.setFont(_ui_font(13))
        self.lbl.setStyleSheet("color: #f5f5f7; background: transparent;")

        self.timer_lbl = QLabel("0:00", self)
        self.timer_lbl.setFont(_mono_font(13))
        self.timer_lbl.setStyleSheet("color: #8e8e98; background: transparent;")

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(8)
        row.addWidget(self.dot)
        row.addWidget(self.lbl)
        row.addStretch(1)
        row.addWidget(self.timer_lbl)

        self.setFixedHeight(self.sizeHint().height())

        self._timer = QTimer(self)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._bump)
        self._timer.start()

    def set_progress(self, done: int, total: int) -> None:
        text = "Распознаю…" if total <= 1 else f"Распознаю… {done}/{total}"
        if text != self.lbl.text():
            self.lbl.setText(text)
            self.lbl.adjustSize()

    def _bump(self) -> None:
        if not self.isVisible():
            return  # скрыта — не считаем анимацию
        self._phase += 0.7
        self.dot.set_phase(self._phase)
        if self._started is not None:
            m, s = divmod(int(time.monotonic() - self._started), 60)
            text = f"{m}:{s:02d}"
            if text != self.timer_lbl.text():
                self.timer_lbl.setText(text)

    def popup(self, since: float | None = None) -> None:
        """since — monotonic-время старта записи: таймер продолжится, а не обнулится."""
        if since is not None and 0 <= time.monotonic() - since <= MAX_RECORD_SEC:
            self._started = since
        else:
            self._started = time.monotonic()
        m, s = divmod(int(time.monotonic() - self._started), 60)
        self.timer_lbl.setText(f"{m}:{s:02d}")
        _anchor_point(self)
        _fade_in(self)

    def paintEvent(self, a0) -> None:
        p = QPainter(self)
        _paint_card(self, p)


# --- карточка результата --------------------------------------------------------
class Badge(QWidget):
    """Кружок с галочкой / восклицательным знаком."""

    def __init__(self, color: QColor, kind: str = "ok", parent=None) -> None:
        super().__init__(parent)
        self.color = color
        self.kind = kind
        self.setFixedSize(16, 16)

    def paintEvent(self, a0) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QRectF(0.5, 0.5, 15, 15))
        pen = QPen(QColor(14, 14, 18), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == "ok":
            p.drawPolyline([_pt(4.2, 8.2), _pt(6.8, 11.2), _pt(12, 5.2)])
        elif self.kind == "info":
            p.setBrush(QColor(14, 14, 18))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(7.2, 3.6, 2.4, 2.4))
            p.drawLine(_pt(8.4, 7.2), _pt(8.4, 12))
        else:
            p.drawLine(_pt(8, 4.2), _pt(8, 9.6))
            p.drawPoint(_pt(8, 12))


def _pt(x: float, y: float):
    from PyQt6.QtCore import QPointF
    return QPointF(x, y)


class ResultCard(QWidget):
    clicked = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        _make_window(self)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedWidth(336)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Открыть историю и настройки")
        self._text = ""

        # один таймер на карточку: новая карточка перезапускает его,
        # старые не «достреливают» новую (было: карточки гасли раньше срока)
        self._linger = QTimer(self)
        self._linger.setSingleShot(True)
        self._linger.timeout.connect(lambda: _fade_out_hide(self))

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(5)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.badge = Badge(GREEN, "ok", self)
        head.addWidget(self.badge)
        self.title_lbl = QLabel("Вставлено")
        self.title_lbl.setFont(_ui_font(12, QFont.Weight.DemiBold))
        self.title_lbl.setStyleSheet("color: #f5f5f7; background: transparent;")
        head.addWidget(self.title_lbl)
        head.addStretch(1)
        self.meta_lbl = QLabel()
        self.meta_lbl.setFont(_ui_font(10))
        self.meta_lbl.setStyleSheet("color: #8e8e98; background: transparent;")
        head.addWidget(self.meta_lbl)
        v.addLayout(head)

        self.body_lbl = QLabel()
        self.body_lbl.setFont(_ui_font(12))
        self.body_lbl.setWordWrap(True)
        self.body_lbl.setStyleSheet("color: #d9d9df; background: transparent;")
        v.addWidget(self.body_lbl)

    def set_content(self, title: str, sub: str, text: str, ok) -> None:
        self.title_lbl.setText(title)
        self.meta_lbl.setText(sub)
        shown = text if len(text) <= 240 else text[:240].rstrip() + "…"
        self.body_lbl.setText(shown)
        self.badge.color = GREEN if ok else (RED if ok is False else ACCENT2)
        self.badge.kind = "ok" if ok else ("warn" if ok is False else "info")
        self.badge.update()
        self.body_lbl.adjustSize()
        self.setFixedHeight(self.sizeHint().height())

    def popup(self, linger: float = CARD_LINGER_SEC) -> None:
        _anchor_point(self)
        _fade_in(self)
        self._linger.start(int(linger * 1000))

    def mouseReleaseEvent(self, a0) -> None:
        self.clicked.emit()

    def paintEvent(self, a0) -> None:
        p = QPainter(self)
        _paint_card(self, p, hovered=self.underMouse())


# --- менеджер ----------------------------------------------------------------
class OverlayManager(QWidget):
    """Владеет всеми окошками и решает, какое сейчас видно."""

    historyRequested = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.pill = RecordingPill()
        self.trans = TranscribingPill()
        self.card = ResultCard()
        self.card.clicked.connect(self.historyRequested)
        # страховка: пока хоть одно окошко видно, раз в секунду переподнимаем
        # его нативный уровень (macOS любит сбрасывать при смене Space)
        self._top_timer = QTimer(self)
        self._top_timer.setInterval(1000)
        self._top_timer.timeout.connect(self._reapply_topmost)
        self._top_timer.start()

    def _reapply_topmost(self) -> None:
        for w in (self.pill, self.trans, self.card):
            if w.isVisible():
                _apply_topmost(w)

    def _hide_others(self, keep: QWidget | None = None) -> None:
        for w in (self.pill, self.trans, self.card):
            if w is not keep and w.isVisible():
                w.hide()
                w.setWindowOpacity(1.0)

    def show_recording(self, level_fn) -> None:
        self._hide_others(self.pill)
        self.pill.popup(level_fn)

    def show_transcribing(self) -> None:
        self._hide_others(self.trans)
        # таймер продолжает счёт с начала записи, а не с нуля
        self.trans.popup(since=self.pill._started)

    def show_result(self, title: str, sub: str, text: str, ok: bool = True,
                    linger: float = CARD_LINGER_SEC) -> None:
        self._hide_others(self.card)
        self.card.set_content(title, sub, text, ok)
        self.card.popup(linger)

    def show_info(self, title: str, text: str, linger: float = 3.5) -> None:
        """Нейтральная карточка (не ошибка): «Секунду…», «Отменено» и т.п."""
        self._hide_others(self.card)
        self.card.set_content(title, "", text, ok=None)
        self.card.popup(linger)

    def show_error(self, msg: str, linger: float = 4.5) -> None:
        self._hide_others(self.card)
        self.card.set_content("Не вышло", "", msg, ok=False)
        self.card.popup(linger)

    def hide_all(self) -> None:
        self._hide_others()

    def show_loading_hint(self) -> None:
        self.show_error("Модель ещё прогревается — секунды через 10 можно говорить",
                        linger=3.0)
