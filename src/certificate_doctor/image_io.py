from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, PngImagePlugin


SUPPORTED_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
SUPPORTED_PDF = {".pdf"}


def load_bgr(path: str | Path) -> tuple[np.ndarray, dict]:
    """Load image or first PDF page as BGR uint8. Returns (image, meta)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    meta: dict = {"source": str(path), "suffix": suffix}

    if suffix in SUPPORTED_PDF:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        if len(pdf) < 1:
            raise ValueError("PDF has no pages.")
        page = pdf[0]
        bitmap = page.render(scale=2.0)
        pil = bitmap.to_pil().convert("RGB")
        meta["pages"] = len(pdf)
        meta["from_pdf"] = True
        bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        return bgr, meta

    if suffix not in SUPPORTED_IMAGE:
        raise ValueError(
            f"Unsupported file type '{suffix}'. Use image ({', '.join(sorted(SUPPORTED_IMAGE))}) or PDF."
        )

    pil = Image.open(path)
    pil = ImageOps.exif_transpose(pil)
    meta["mode"] = pil.mode
    meta["format"] = pil.format
    if pil.mode not in {"RGB", "L"}:
        pil = pil.convert("RGB")
    elif pil.mode == "L":
        pil = pil.convert("RGB")
    bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return bgr, meta


def load_pil(path: str | Path) -> Image.Image:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_PDF:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        page = pdf[0]
        return page.render(scale=2.0).to_pil().convert("RGB")
    img = Image.open(path)
    return ImageOps.exif_transpose(img).convert("RGB")


def bgr_to_pil(bgr: np.ndarray) -> Image.Image:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def encode_jpeg_bytes(bgr: np.ndarray, quality: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("Failed to encode JPEG")
    return buf.tobytes()


def decode_jpeg_bytes(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("Failed to decode JPEG")
    return img


def read_png_text(path: str | Path) -> dict[str, str]:
    path = Path(path)
    if path.suffix.lower() != ".png":
        return {}
    try:
        with Image.open(path) as im:
            return {k: str(v) for k, v in (im.info or {}).items() if isinstance(v, str)}
    except Exception:  # noqa: BLE001
        return {}


def write_png_with_text(path: str | Path, image: Image.Image, text: dict[str, str]) -> None:
    meta = PngImagePlugin.PngInfo()
    for k, v in text.items():
        meta.add_text(k, v)
    image.save(path, format="PNG", pnginfo=meta)


def bytes_from_upload(data: bytes, suffix: str) -> tuple[np.ndarray, dict]:
    """Decode uploaded bytes into BGR."""
    suffix = suffix.lower()
    if suffix in SUPPORTED_PDF:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(io.BytesIO(data))
        page = pdf[0]
        pil = page.render(scale=2.0).to_pil().convert("RGB")
        bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        return bgr, {"from_pdf": True, "pages": len(pdf), "suffix": suffix}

    arr = np.frombuffer(data, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        # Pillow fallback
        pil = Image.open(io.BytesIO(data))
        pil = ImageOps.exif_transpose(pil).convert("RGB")
        bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    return bgr, {"suffix": suffix}
