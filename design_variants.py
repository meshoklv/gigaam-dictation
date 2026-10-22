"""Три минималистичных варианта плашки записи — рендер в PNG для выбора дизайна.

А · «Тихий»     — крошечная капсула: пульсирующая точка + таймер, больше ничего.
Б · «Чернила»   — без фона: точка + живая волна-линия + таймер прямо на экране.
В · «Кольцо»    — стеклянный круг с микром и кольцом-пульсом + таймер рядом.
"""
import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QApplication, QWidget

DPR = 2.0

BG_A = QColor(18, 18, 22, 236)
BORDER = QColor(255, 255, 255, 22)
RED = QColor(255, 96, 92)
ACCENT = QColor(255, 138, 92)
TEXT = QColor(245, 245, 247)
MUTED = QColor(160, 160, 170)


def mono(size):
    f = QFont("Menlo")
    f.setPixelSize(size)
    return f


def ui(size, weight=QFont.Weight.Normal):
    f = QFont("Helvetica Neue")
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def _translucent(w: QWidget) -> None:
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    w.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)


class MinimalPill(QWidget):
    """А · Тихий: капсула 128×32 — точка и таймер."""

    def __init__(self):
        super().__init__()
        _translucent(self)
        self.setFixedSize(128, 32)
        self._t = 1.1  # фаза пульса

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 16, 16)
        p.setPen(QPen(BORDER, 1))
        p.setBrush(BG_A)
        p.drawPath(path)

        glow = 0.55 + 0.45 * abs(math.sin(self._t))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(RED.red(), RED.green(), RED.blue(), int(70 * glow)))
        p.drawEllipse(QRectF(14 - 5.5, 16 - 5.5, 11, 11))
        p.setBrush(RED)
        p.drawEllipse(QRectF(14 - 3.2, 16 - 3.2, 6.4, 6.4))

        p.setPen(QPen(TEXT))
        p.setFont(mono(12))
        p.drawText(QRectF(30, 0, self.width() - 38, self.height()),
                   Qt.AlignmentFlag.AlignVCenter, "0:07")


class InkLine(QWidget):
    """Б · Чернила: без фона — точка, волна-линия, таймер."""

    def __init__(self):
        super().__init__()
        _translucent(self)
        self.setFixedSize(196, 36)
        self._t = 0.0
        self._level = 0.45

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        glow = 0.55 + 0.45 * abs(math.sin(1.1))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(RED.red(), RED.green(), RED.blue(), int(70 * glow)))
        p.drawEllipse(QRectF(6 - 5, 18 - 5, 10, 10))
        p.setBrush(RED)
        p.drawEllipse(QRectF(6 - 3, 18 - 3, 6, 6))

        # волна — одна плавная линия: амплитуда медленно дышит, без зубьев
        pen = QPen(ACCENT, 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        path = QPainterPath()
        cy = 18.0
        x0, width = 22, 116
        for i in range(0, width + 1):
            x = x0 + i
            env = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(i * 0.045 + self._t))
            amp = 2 + self._level * 11 * env
            y = cy + math.sin(i * 0.15 + self._t * 2.0) * amp
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        p.drawPath(path)

        p.setPen(QPen(TEXT))
        p.setFont(mono(12))
        p.drawText(QRectF(148, 0, 44, self.height()),
                   Qt.AlignmentFlag.AlignVCenter, "0:07")


class RingPill(QWidget):
    """В · Кольцо: круг с микром, кольцо-пульс, таймер рядом."""

    def __init__(self):
        super().__init__()
        _translucent(self)
        self.setFixedSize(150, 48)
        self._t = 2.0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = 24, 24, 21

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG_A)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # кольцо: базовое + дуговой пульс
        base = QPen(QColor(255, 255, 255, 30), 2.0)
        p.setPen(base)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - r + 1, cy - r + 1, (r - 1) * 2, (r - 1) * 2))
        arc_pen = QPen(ACCENT, 2.6)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(arc_pen)
        span = 90 + 60 * abs(math.sin(self._t))
        p.drawArc(QRectF(cx - r + 1, cy - r + 1, (r - 1) * 2, (r - 1) * 2),
                  90 * 16, -int(span) * 16)

        # микро-глиф
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(TEXT)
        p.drawRoundedRect(QRectF(cx - 3.2, cy - 8, 6.4, 11), 3.2, 3.2)
        pen = QPen(TEXT, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(cx - 6.5, cy - 4.5, 13, 12), 0, -180 * 16)
        p.drawLine(QPointF(cx, cy + 7.5), QPointF(cx, cy + 10))

        p.setPen(QPen(TEXT))
        p.setFont(mono(12))
        p.drawText(QRectF(54, 0, 52, self.height()),
                   Qt.AlignmentFlag.AlignVCenter, "0:07")
        p.setPen(QPen(MUTED))
        p.setFont(ui(10, QFont.Weight.DemiBold))
        p.drawText(QRectF(104, 0, self.width() - 108, self.height()),
                   Qt.AlignmentFlag.AlignVCenter, "⌘R")


def on_bg(widget: QWidget, w: int, h: int, px: int, py: int, light: bool = False) -> QPixmap:
    pm = QPixmap(int(w * DPR), int(h * DPR))
    pm.setDevicePixelRatio(DPR)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, w, h)
    if light:
        g.setColorAt(0, QColor("#e9e6e2"))
        g.setColorAt(1, QColor("#c9c5c0"))
    else:
        g.setColorAt(0, QColor("#232327"))
        g.setColorAt(1, QColor("#101014"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(0, 0, w, h), 14, 14)
    p.end()
    widget.render(pm, QPoint(px, py))
    return pm


def main():
    app = QApplication(sys.argv)
    out = os.path.join(os.path.dirname(__file__), "design", "variants")
    os.makedirs(out, exist_ok=True)

    variants = [
        ("А · «Тихий» — капсула: точка + таймер, больше ничего", MinimalPill(), (300, 130), (86, 49)),
        ("Б · «Чернила» — без фона: волна-линия на экране", InkLine(), (300, 130), (52, 47)),
        ("В · «Кольцо» — микро в круге, кольцо-пульс", RingPill(), (300, 130), (75, 41)),
    ]
    for name, wgt, size, pos in variants:
        pm = on_bg(wgt, *size, *pos)
        pm.save(os.path.join(out, f"v_{name[0]}.png"))

    # общий лист сравнения
    W, H = 560, 500
    sheet = QPixmap(int(W * DPR), int(H * DPR))
    sheet.setDevicePixelRatio(DPR)
    sheet.fill(QColor("#141418"))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#f5f5f7")))
    p.setFont(ui(16, QFont.Weight.DemiBold))
    p.drawText(QRectF(0, 26, W, 24), Qt.AlignmentFlag.AlignHCenter, "Плашка записи — 3 минимализма")
    y = 78
    for name, wgt, size, pos in variants:
        p.setPen(QPen(QColor("#9a9aa4")))
        p.setFont(ui(12, QFont.Weight.DemiBold))
        p.drawText(QRectF(36, y, W - 72, 20), Qt.AlignmentFlag.AlignLeft, name)
        row = on_bg(wgt, 488, 108, (488 - size[0]) // 2 + 20, (108 - size[1]) // 2 + 4)
        p.drawPixmap(36, y + 26, row)
        y += 140
    p.end()
    sheet.save(os.path.join(out, "compare.png"))
    print("saved", out)


if __name__ == "__main__":
    main()
