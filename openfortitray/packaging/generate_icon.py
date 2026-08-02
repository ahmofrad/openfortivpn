"""Generate the OpenFortiTray app icon.

Run from the openfortitray/ project root:
    python packaging/generate_icon.py

Writes app_icon.png / app_icon.ico to the project root and to packaging/.
"""
from pathlib import Path
import sys

from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath
from PySide6.QtCore import Qt, QRectF
from PySide6.QtWidgets import QApplication


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


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    _app = QApplication(sys.argv)  # noqa: F841  (needed for QPixmap)

    png = draw_icon(256)
    (root / "app_icon.png").write_bytes(b"")
    png.save(str(root / "app_icon.png"))
    print(f"Saved {root / 'app_icon.png'}")

    try:
        from PIL import Image

        img = Image.open(str(root / "app_icon.png"))
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(str(root / "app_icon.ico"), format="ICO", sizes=sizes)
        print(f"Saved {root / 'app_icon.ico'}")
    except ImportError:
        print("Pillow not installed; skipping .ico (pip install pillow)")

    # Copy to packaging/ so the PyInstaller spec can find them
    pkg = root / "packaging"
    for name in ("app_icon.png", "app_icon.ico"):
        src = root / name
        if src.exists():
            (pkg / name).write_bytes(src.read_bytes())
            print(f"Copied to {pkg / name}")


if __name__ == "__main__":
    main()
