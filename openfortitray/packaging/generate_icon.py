"""Generate the OpenFortiTray app icon."""
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath, QIcon
from PySide6.QtCore import Qt, QRectF


def draw_icon(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)

    margin = size * 0.05
    shield_h = size - 2 * margin
    shield_w = size - 2 * margin
    cx = size / 2

    # Shield path
    path = QPainterPath()
    top = margin + shield_h * 0.05
    bottom = margin + shield_h * 0.95
    half_w = shield_w * 0.42
    mid_y = margin + shield_h * 0.72

    path.moveTo(cx, top)
    path.lineTo(cx + half_w, top + shield_h * 0.08)
    path.lineTo(cx + half_w, mid_y)
    path.quadTo(cx + half_w, bottom, cx, bottom)
    path.quadTo(cx - half_w, bottom, cx - half_w, mid_y)
    path.lineTo(cx - half_w, top + shield_h * 0.08)
    path.closeSubpath()

    p.setBrush(QColor("#1a3a5c"))
    p.setPen(QPen(QColor("#2d5a8e"), size * 0.02))
    p.drawPath(path)

    # Inner highlight
    margin2 = size * 0.12
    path2 = QPainterPath()
    top2 = margin2 + shield_h * 0.05
    bottom2 = margin2 + shield_h * 0.85
    half_w2 = (shield_w - 2 * (margin2 - margin)) * 0.35

    path2.moveTo(cx, top2)
    path2.lineTo(cx + half_w2, top2 + shield_h * 0.08)
    path2.lineTo(cx + half_w2, margin2 + shield_h * 0.55)
    path2.quadTo(cx + half_w2, bottom2, cx, bottom2)
    path2.quadTo(cx - half_w2, bottom2, cx - half_w2, margin2 + shield_h * 0.55)
    path2.lineTo(cx - half_w2, top2 + shield_h * 0.08)
    path2.closeSubpath()

    p.setBrush(QColor("#2d6a9e"))
    p.setPen(Qt.NoPen)
    p.drawPath(path2)

    # Lock body
    lock_cx = cx
    lock_cy = size * 0.48
    lock_w = size * 0.18
    lock_h = size * 0.14

    p.setBrush(QColor("#4ec9b0"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(
        QRectF(lock_cx - lock_w / 2, lock_cy - lock_h / 4, lock_w, lock_h),
        size * 0.02, size * 0.02,
    )

    # Lock shackle
    p.setPen(QPen(QColor("#4ec9b0"), size * 0.03))
    p.setBrush(Qt.NoBrush)
    p.drawArc(
        QRectF(lock_cx - lock_w * 0.35, lock_cy - lock_h * 0.65,
               lock_w * 0.7, lock_h * 0.7),
        0, 180 * 16,
    )

    # Keyhole
    p.setBrush(QColor("#1a3a5c"))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(lock_cx - size * 0.015, lock_cy, size * 0.03, size * 0.03))

    p.end()
    return pixmap


if __name__ == "__main__":
    import sys

    app_pixmap = draw_icon(256)
    app_pixmap.save("app_icon.png")
    print("Saved app_icon.png (256x256)")

    for sz in (16, 32, 64, 128, 256):
        pm = draw_icon(sz)
        pm.save(f"app_icon_{sz}.png")
        print(f"Saved app_icon_{sz}.png")

    icon = QIcon(app_pixmap)
    icon.save("app_icon.ico")
    print("Saved app_icon.ico")
