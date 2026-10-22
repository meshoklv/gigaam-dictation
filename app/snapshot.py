"""Рендер состояний интерфейса в PNG (offscreen) — для проверки дизайна.

Каждое состояние кладётся на ДВЕ подложки — тёмную и светлую (светлая ловит
нечитаемый текст). Под оверлеем рисуется псевдо-контент «окон»: видно, если
что-то просвечивает сквозь карточку или текст «двоится».
Файлы: design/variants/polish_<состояние>_<подложка>.png
"""
from __future__ import annotations

import math
import os
import random
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

from overlay import RecordingPill, ResultCard, TranscribingPill

CANVAS_W, CANVAS_H = 620, 340
MARGIN_RIGHT, MARGIN_BOTTOM = 16, 20  # в жизни снизу 88 (док) — тут компактнее

BACKGROUNDS = {
    "dark": ("#232327", "#101014"),
    "light": ("#e9e6e2", "#c9c5c0"),
}


def _fake_desktop(p: QPainter, light: bool) -> None:
    """Псевдо-контент «окон» под оверлеем — полосы текста, уходящие под карточку."""
    f = QFont("Helvetica")
    f.setPixelSize(13)
    p.setFont(f)
    color = QColor(96, 96, 104) if light else QColor(88, 88, 98)
    p.setPen(QPen(color))
    for i, txt in enumerate((
            "Отчёт по поставке №1847 — сводка за сентябрь, строки длинные,",
            "чтобы точно уйти под оверлей и поймать просвечивание текста ·",
            "def close_all_windows(self): for w in self.windows: w.hide()",
    )):
        p.drawText(QPointF(24, 46 + i * 28), txt)
    p.setPen(QPen(QColor(0, 0, 0, 28) if light else QColor(255, 255, 255, 14), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(10, 10, CANVAS_W - 20, CANVAS_H - 20), 10, 10)


def _render_pair(widget, state: str, out_dir: str) -> None:
    pm = widget.grab()
    for bg_name, (top, bottom) in BACKGROUNDS.items():
        canvas = QPixmap(CANVAS_W, CANVAS_H)
        canvas.fill(Qt.GlobalColor.transparent)
        p = QPainter(canvas)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, CANVAS_W, CANVAS_H)
        g.setColorAt(0.0, QColor(top))
        g.setColorAt(1.0, QColor(bottom))
        p.fillRect(0, 0, CANVAS_W, CANVAS_H, g)
        _fake_desktop(p, bg_name == "light")
        x = CANVAS_W - pm.width() - MARGIN_RIGHT
        y = CANVAS_H - pm.height() - MARGIN_BOTTOM
        p.drawPixmap(x, y, pm)
        p.end()
        path = os.path.join(out_dir, f"polish_{state}_{bg_name}.png")
        canvas.save(path)
        print("saved", os.path.abspath(path))


def render(level_fn) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    out = os.path.join(os.path.dirname(__file__), "..", "design", "variants")
    os.makedirs(out, exist_ok=True)

    rec = RecordingPill()
    rec.popup(level_fn)
    rec._started = time.monotonic() - 7  # показать «0:07» как в жизни
    for _ in range(40):
        rec._on_tick()
    _render_pair(rec, "recording", out)

    trans = TranscribingPill()
    trans.popup(since=time.monotonic() - 9)  # таймер продолжился с записи
    trans.set_progress(2, 3)
    for _ in range(30):
        trans._bump()
    _render_pair(trans, "transcribing", out)

    card = ResultCard()
    card.set_content("Вставлено", "0:07 · 14:32",
                     "Привет! Это тестовая диктовка — проверяем, как ложится текст "
                     "с пунктуацией и большими буквами. И ещё одна строка, "
                     "чтобы увидеть перенос.", ok=True)
    card.popup()
    _render_pair(card, "result", out)

    err = ResultCard()
    err.set_content("Не вышло", "", "Не расслышал. Попробуй ещё раз.", ok=False)
    err.popup()
    _render_pair(err, "error", out)


if __name__ == "__main__":
    level_fn = lambda: 0.3 + 0.25 * math.sin(1.1) + random.random() * 0.35
    render(level_fn)
