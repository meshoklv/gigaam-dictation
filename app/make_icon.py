"""Рисует иконку приложения (микрофон на тёмном скруглённом квадрате)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


def main() -> None:
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    img = QImage(1024, 1024, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # подложка
    bg = QLinearGradient(0, 0, 0, 1024)
    bg.setColorAt(0.0, QColor("#34343e"))
    bg.setColorAt(1.0, QColor("#15151a"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(16, 16, 992, 992), 224, 224)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawPath(path)
    p.setPen(QPen(QColor(255, 255, 255, 26), 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)

    # микрофон: капсула с градиентом
    body = QLinearGradient(0, 260, 0, 640)
    body.setColorAt(0.0, QColor("#ff8a5c"))
    body.setColorAt(1.0, QColor("#ffb86b"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(body)
    p.drawRoundedRect(QRectF(512 - 92, 262, 184, 380), 92, 92)

    # дуга-держатель
    white = QColor("#f2f2f5")
    pen = QPen(white, 58)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(512 - 168, 380, 336, 336), 0, -180 * 16)

    # ножка и база
    pen = QPen(white, 58)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(512, 700), QPointF(512, 782))
    p.drawLine(QPointF(404, 800), QPointF(620, 800))
    p.end()

    out = os.path.join(os.path.dirname(__file__), "..", "build")
    os.makedirs(out, exist_ok=True)
    img.save(os.path.join(out, "icon_1024.png"))
    print("icon saved")


if __name__ == "__main__":
    import sys
    main()
