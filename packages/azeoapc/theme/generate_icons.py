"""Generate PNG window icons for each Azeotrope APC app.

Run once to populate packages/azeoapc/theme/icons/*.png. Each icon
is a 64x64 PNG with the app's accent colour as a filled diamond on a
transparent background, plus a one-letter label:

  launcher.png   -- blue diamond, "A" (Azeotrope)
  architect.png  -- blue diamond, "B" (Builder)
  ident.png      -- purple diamond, "I" (Ident)
  runtime.png    -- orange diamond, "R" (Runtime)
  historian.png  -- teal diamond, "H" (Historian)
  manager.png    -- green diamond, "M" (Manager)

The icons are committed to the repo so the apps can load them at
startup without re-generating. This script is only needed if you
want to change the colours or letters.
"""
import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication


ICONS = [
    ("launcher",  "#0066CC", "A"),
    ("architect", "#0066CC", "B"),
    ("ident",     "#7A4FB7", "I"),
    ("runtime",   "#D9822B", "R"),
    ("historian", "#0099B0", "H"),
    ("manager",   "#2E8B57", "M"),
]

SIZE = 64
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


def generate_icon(name: str, color: str, letter: str) -> None:
    img = QImage(SIZE, SIZE, QImage.Format_ARGB32)
    img.fill(Qt.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # Diamond shape
    cx, cy = SIZE / 2.0, SIZE / 2.0
    r = SIZE * 0.42
    path = QPainterPath()
    path.moveTo(QPointF(cx, cy - r))       # top
    path.lineTo(QPointF(cx + r, cy))       # right
    path.lineTo(QPointF(cx, cy + r))       # bottom
    path.lineTo(QPointF(cx - r, cy))       # left
    path.closeSubpath()

    # Fill + border
    fill = QColor(color)
    fill.setAlpha(220)
    p.fillPath(path, fill)
    p.setPen(QPen(QColor(color), 2))
    p.drawPath(path)

    # Letter
    p.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", 22, QFont.Bold)
    p.setFont(font)
    p.drawText(QRectF(0, 0, SIZE, SIZE), Qt.AlignCenter, letter)

    p.end()

    out_path = os.path.join(OUT_DIR, f"{name}.png")
    img.save(out_path)
    print(f"  {out_path} ({SIZE}x{SIZE})")


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Generating {len(ICONS)} icons in {OUT_DIR}")
    for name, color, letter in ICONS:
        generate_icon(name, color, letter)
    print("Done")


if __name__ == "__main__":
    main()
