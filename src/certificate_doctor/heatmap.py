from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from certificate_doctor.models import Region


def ela_maps(bgr: np.ndarray, quality: int = 90, scale: float = 15.0) -> tuple[np.ndarray, np.ndarray]:
    """Return (gray_diff amplified uint8, color heatmap BGR)."""
    ok, enc = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise RuntimeError("ELA encode failed")
    recompressed = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    if recompressed is None:
        raise RuntimeError("ELA decode failed")
    if recompressed.shape[:2] != bgr.shape[:2]:
        recompressed = cv2.resize(recompressed, (bgr.shape[1], bgr.shape[0]))

    diff = cv2.absdiff(bgr, recompressed).astype(np.float32)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    amp = np.clip(gray * scale, 0, 255).astype(np.uint8)
    heat = cv2.applyColorMap(amp, cv2.COLORMAP_INFERNO)
    return amp, heat


def overlay_heatmap(
    bgr: np.ndarray,
    heat_bgr: np.ndarray,
    alpha: float = 0.45,
    mask: np.ndarray | None = None,
) -> np.ndarray:
    if heat_bgr.shape[:2] != bgr.shape[:2]:
        heat_bgr = cv2.resize(heat_bgr, (bgr.shape[1], bgr.shape[0]))
    blend = cv2.addWeighted(bgr, 1.0 - alpha, heat_bgr, alpha, 0)
    if mask is not None:
        m = mask
        if m.ndim == 2:
            m = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
        if m.shape[:2] != bgr.shape[:2]:
            m = cv2.resize(m, (bgr.shape[1], bgr.shape[0]))
        # Keep original where mask is low
        keep = (m[:, :, 0] < 40)[:, :, None]
        blend = np.where(keep, bgr, blend)
    return blend.astype(np.uint8)


def draw_regions(bgr: np.ndarray, regions: list[Region], color: tuple[int, int, int] = (40, 90, 255)) -> np.ndarray:
    out = bgr.copy()
    for r in regions:
        x1, y1 = max(0, r.x), max(0, r.y)
        x2, y2 = min(out.shape[1] - 1, r.x + r.w), min(out.shape[0] - 1, r.y + r.h)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        if r.label:
            cv2.putText(
                out,
                r.label[:40],
                (x1, max(16, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )
    return out


def save_artifacts(
    bgr: np.ndarray,
    ela_gray: np.ndarray,
    ela_heat: np.ndarray,
    regions: list[Region],
    out_dir: str | Path,
    stem: str,
) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    heat_path = out / f"{stem}.heatmap.png"
    overlay_path = out / f"{stem}.overlay.png"

    mask = cv2.threshold(ela_gray, 40, 255, cv2.THRESH_BINARY)[1]
    overlay = overlay_heatmap(bgr, ela_heat, alpha=0.5, mask=mask)
    overlay = draw_regions(overlay, regions)

    cv2.imwrite(str(heat_path), ela_heat)
    cv2.imwrite(str(overlay_path), overlay)
    return heat_path, overlay_path
