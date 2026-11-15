#!/usr/bin/env python3
"""Generate synthetic genuine + tampered marksheet images (no real PII)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
sys.path.insert(0, str(ROOT / "src"))

from certificate_doctor.checks.logic import LOGIC_KEY  # noqa: E402


W, H = 900, 1200


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/times.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    ]
    if bold:
        candidates = [
            "C:/Windows/Fonts/georgiab.ttf",
            "C:/Windows/Fonts/timesbd.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        ] + candidates
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_seal(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int = 54) -> None:
    """Asymmetric seal — avoids periodic self-similar blocks."""
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(160, 40, 40), width=3)
    draw.ellipse((cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10), outline=(160, 40, 40), width=2)
    draw.polygon(
        [(cx, cy - r + 18), (cx + 16, cy + 8), (cx - 20, cy + 4)],
        outline=(160, 40, 40),
    )
    draw.text((cx - 22, cy + 12), "NSU", fill=(160, 40, 40), font=_font(16, bold=True))


def build_marksheet(
    *,
    marks: list[tuple[str, int]],
    printed_total: int,
    printed_pct: float,
    roll: str = "NSU-2024-1042",
    student: str = "Alex Rivera",
    title_note: str = "Statement of Marks — Academic Year 2024",
) -> Image.Image:
    img = Image.new("RGB", (W, H), (248, 246, 240))
    draw = ImageDraw.Draw(img)

    draw.rectangle((36, 36, W - 36, H - 36), outline=(28, 48, 62), width=3)

    title = _font(34, bold=True)
    h2 = _font(20, bold=True)
    body = _font(18)
    small = _font(14)

    draw.text((W // 2, 78), "NORTHSTAR UNIVERSITY", fill=(18, 36, 48), font=title, anchor="mt")
    draw.text((W // 2, 118), title_note, fill=(70, 90, 100), font=body, anchor="mt")
    draw.line((80, 150, W - 80, 150), fill=(28, 48, 62), width=1)

    draw.text((80, 180), f"Student: {student}", fill=(20, 30, 40), font=h2)
    draw.text((80, 214), f"Roll No: {roll}", fill=(20, 30, 40), font=body)
    draw.text((80, 246), "Programme: B.Sc. Forensic Computing", fill=(20, 30, 40), font=body)
    draw.text((80, 278), "Issue Date: 2024-06-18", fill=(20, 30, 40), font=body)

    y0 = 340
    draw.rectangle((80, y0, W - 80, y0 + 42), fill=(28, 48, 62))
    draw.text((100, y0 + 10), "Subject", fill=(248, 246, 240), font=h2)
    draw.text((W - 200, y0 + 10), "Marks", fill=(248, 246, 240), font=h2)

    y = y0 + 42
    for i, (subj, mark) in enumerate(marks):
        bg = (236, 232, 224) if i % 2 == 0 else (248, 246, 240)
        draw.rectangle((80, y, W - 80, y + 48), fill=bg, outline=(200, 196, 188))
        draw.text((100, y + 12), subj, fill=(20, 30, 40), font=body)
        draw.text((W - 160, y + 12), f"{mark:3d}", fill=(20, 30, 40), font=h2)
        y += 48

    y += 20
    draw.text((100, y), f"Total: {printed_total}", fill=(20, 30, 40), font=h2)
    draw.text((100, y + 36), f"Percentage: {printed_pct:.1f}%", fill=(20, 30, 40), font=h2)
    draw.text((100, y + 72), "Result: PASS", fill=(20, 100, 70), font=h2)

    _draw_seal(draw, W - 160, H - 180, r=58)
    draw.text((80, H - 120), "Controller of Examinations", fill=(70, 90, 100), font=small)
    draw.text((80, H - 96), "Synthetic demo document — not a real credential", fill=(140, 120, 100), font=small)

    return img


def _save_jpeg(
    img: Image.Image,
    path: Path,
    *,
    software: str | None,
    quality: int,
    logic: dict,
) -> None:
    exif = img.getexif()
    if software:
        exif[0x0131] = software
    exif[0x0132] = "2024:06:18 10:00:00"
    payload = f"{LOGIC_KEY}:{json.dumps(logic)}"
    exif[0x9286] = "ASCII\x00\x00\x00" + payload
    exif[0x010E] = payload
    img.convert("RGB").save(path, format="JPEG", quality=quality, exif=exif, optimize=True)


def make_genuine() -> Path:
    marks = [
        ("Mathematics", 85),
        ("Physics", 90),
        ("Chemistry", 78),
        ("English", 88),
        ("Computer Science", 92),
    ]
    total = sum(m for _, m in marks)
    pct = round(100.0 * total / (len(marks) * 100), 1)
    img = build_marksheet(marks=marks, printed_total=total, printed_pct=pct)
    logic = {
        "marks": [m for _, m in marks],
        "printed_total": total,
        "printed_pct": pct,
        "roll": "NSU-2024-1042",
        "max_total": len(marks) * 100,
    }
    path = SAMPLES / "genuine_marksheet.jpg"
    _save_jpeg(img, path, software=None, quality=95, logic=logic)
    return path


def make_tampered(genuine_path: Path) -> Path:
    """Classic forge: open genuine JPEG, paste digit + clone seal, re-save."""
    base = Image.open(genuine_path).convert("RGB")

    # Large low-texture paint + crushed JPEG — ELA lights this up after edge suppression
    cell = (W - 240, 340 + 42 + 48 * 4 - 6, W - 70, 340 + 42 + 48 * 5 + 10)
    cw, ch = cell[2] - cell[0], cell[3] - cell[1]
    patch = Image.new("RGB", (cw, ch), (210, 205, 195))
    pd = ImageDraw.Draw(patch)
    # Soft filled blob (not sharp text edges) so edge-suppression keeps the residual
    pd.rectangle((4, 4, cw - 5, ch - 5), fill=(225, 218, 205))
    pd.text((36, 10), "99", fill=(40, 35, 30), font=_font(36, bold=True))
    arr = np.array(patch).astype(np.int16)
    rng = np.random.default_rng(7)
    # Blocky chroma-ish noise that survives as compression inconsistency
    noise = rng.integers(-40, 41, size=arr.shape)
    for by in range(0, ch, 8):
        for bx in range(0, cw, 8):
            noise[by : by + 8, bx : bx + 8] = rng.integers(-35, 36)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    patch = Image.fromarray(arr)
    buf = io.BytesIO()
    patch.save(buf, format="JPEG", quality=5)
    buf.seek(0)
    dirty = Image.open(buf).convert("RGB")
    # Upscale with nearest to create block artifacts, then crush again
    dirty = dirty.resize((cw // 2, ch // 2), Image.Resampling.BILINEAR)
    dirty = dirty.resize((cw, ch), Image.Resampling.NEAREST)
    buf2 = io.BytesIO()
    dirty.save(buf2, format="JPEG", quality=10)
    buf2.seek(0)
    dirty = Image.open(buf2).convert("RGB")
    base.paste(dirty, (cell[0], cell[1]))

    # Copy-move: clone a large distinctive seal block (multiple matching tiles)
    seal_box = (W - 250, H - 280, W - 80, H - 90)
    seal = base.crop(seal_box)
    base.paste(seal, (80, H - 280))
    # Second partial clone slightly offset to create multi-block shift agreement
    seal2 = base.crop((W - 220, H - 250, W - 100, H - 120))
    base.paste(seal2, (110, H - 250))

    forged_marks = [85, 90, 78, 88, 99]
    old_total = 433
    old_pct = 86.6
    logic = {
        "marks": forged_marks,
        "printed_total": old_total,
        "printed_pct": old_pct,
        "roll": "NSU-2024-1042",
        "max_total": 500,
    }
    path = SAMPLES / "tampered_marksheet.jpg"
    _save_jpeg(base, path, software="Adobe Photoshop 2024", quality=95, logic=logic)
    return path


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    for old in SAMPLES.glob("*_marksheet.png"):
        old.unlink(missing_ok=True)
    g = make_genuine()
    t = make_tampered(g)
    print(f"Wrote {g}")
    print(f"Wrote {t}")


if __name__ == "__main__":
    main()
