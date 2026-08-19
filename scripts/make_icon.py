"""Masaüstü kısayolu için uygulama ikonu üretir.

Harici bir görsel dosyasına bağımlı olmamak için ikon programatik olarak
çizilir (Pillow ile). Böylece depoda telif durumu belirsiz bir görsel
bulunmaz ve ikon her boyutta net görünür.

Kullanım:
    python scripts/make_icon.py
Çıktı:
    assets/restaurant.ico   (16, 32, 48, 64, 128, 256 piksel)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "restaurant.ico"

# Uygulamanın marka renkleri (static/css/app.css ile aynı)
BRAND = (31, 111, 235)  # #1f6feb
ACCENT = (240, 136, 62)  # #f0883e
WHITE = (255, 255, 255)


def rounded_gradient(size: int) -> Image.Image:
    """Köşeleri yuvarlatılmış, çapraz degrade zemin."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(gradient)

    for y in range(size):
        for_ratio = y / max(size - 1, 1)
        # Çapraz his vermek için satır bazında karıştır
        color = tuple(int(BRAND[i] + (ACCENT[i] - BRAND[i]) * for_ratio) for i in range(3))
        draw.line([(0, y), (size, y)], fill=color + (255,))

    # Yuvarlak köşe maskesi
    mask = Image.new("L", (size, size), 0)
    radius = max(int(size * 0.22), 2)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    image.paste(gradient, (0, 0), mask)
    return image


def draw_plate_and_cutlery(image: Image.Image, size: int) -> None:
    """Tabak, çatal ve bıçak siluetini çizer."""
    draw = ImageDraw.Draw(image)
    unit = size / 100.0

    def u(value: float) -> float:
        return value * unit

    # --- Tabak (iki halka) ---
    outer = [u(30), u(24), u(70), u(64)]
    draw.ellipse(outer, outline=WHITE + (255,), width=max(int(u(5)), 1))
    inner_pad = u(7)
    draw.ellipse(
        [outer[0] + inner_pad, outer[1] + inner_pad, outer[2] - inner_pad, outer[3] - inner_pad],
        outline=WHITE + (170,),
        width=max(int(u(2.5)), 1),
    )

    # --- Çatal (sol) ---
    tine_top, tine_bottom = u(20), u(38)
    for offset in (0, 5, 10):
        x = u(12) + offset * unit
        draw.line([(x, tine_top), (x, tine_bottom)], fill=WHITE + (255,), width=max(int(u(3)), 1))
    # Diş birleşimi ve sap
    draw.line(
        [(u(12), tine_bottom), (u(22), tine_bottom)], fill=WHITE + (255,), width=max(int(u(3)), 1)
    )
    draw.line([(u(17), tine_bottom), (u(17), u(78))], fill=WHITE + (255,), width=max(int(u(4)), 1))

    # --- Bıçak (sağ) ---
    draw.polygon(
        [(u(80), u(20)), (u(87), u(28)), (u(84), u(46)), (u(80), u(46))],
        fill=WHITE + (255,),
    )
    draw.line([(u(82), u(46)), (u(82), u(78))], fill=WHITE + (255,), width=max(int(u(4)), 1))


def build() -> Path:
    sizes = [256, 128, 64, 48, 32, 16]
    frames = []
    for size in sizes:
        # Kenar yumuşatma için 4 kat büyük çizip küçült
        scale = 4 if size >= 32 else 8
        canvas = rounded_gradient(size * scale)
        draw_plate_and_cutlery(canvas, size * scale)
        frames.append(canvas.resize((size, size), Image.LANCZOS))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(OUTPUT, format="ICO", sizes=[(s, s) for s in sizes])
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"Ikon olusturuldu: {path}  ({path.stat().st_size} bayt)")
