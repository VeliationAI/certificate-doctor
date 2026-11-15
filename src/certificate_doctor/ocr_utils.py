from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class OcrWord:
    text: str
    conf: float
    x: int
    y: int
    w: int
    h: int


def tesseract_available() -> bool:
    try:
        import pytesseract  # noqa: F401

        # Probe binary
        from pytesseract import get_tesseract_version

        get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def run_ocr(bgr: np.ndarray) -> tuple[str, list[OcrWord], dict[str, Any]]:
    """Run Tesseract if available. Returns (full_text, words, meta)."""
    meta: dict[str, Any] = {"available": False, "engine": None}
    if not tesseract_available():
        meta["note"] = "Tesseract not installed — OCR checks degrade gracefully."
        return "", [], meta

    try:
        import cv2
        import pytesseract

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        data = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)
        words: list[OcrWord] = []
        parts: list[str] = []
        n = len(data.get("text", []))
        for i in range(n):
            text = (data["text"][i] or "").strip()
            if not text:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = -1.0
            if conf < 0:
                continue
            w = OcrWord(
                text=text,
                conf=conf,
                x=int(data["left"][i]),
                y=int(data["top"][i]),
                w=int(data["width"][i]),
                h=int(data["height"][i]),
            )
            words.append(w)
            parts.append(text)
        full = " ".join(parts)
        meta.update({"available": True, "engine": "tesseract", "word_count": len(words)})
        return full, words, meta
    except Exception as exc:  # noqa: BLE001
        meta["error"] = str(exc)
        meta["note"] = "OCR failed — degrading gracefully."
        return "", [], meta
